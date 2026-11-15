"""Export ATT treatment-basis screening tables to a new directory.

Capital charge is FCI times the ordinary capital recovery factor, not the DCF
MSP calculation: working capital, financing, tax and startup are not modeled
in this screening charge. Hydrogen revenue is excluded from net treatment cost.
Run: python -m biorefineries.ATT.analyses.treatment_report [--out DIRECTORY]
"""
import argparse
import csv
from pathlib import Path

from biorefineries.ATT.analyses.functional_unit import normalize_case
from biorefineries.ATT.analyses.paths import output_dir


def run():
    from biorefineries.ATT.analyses import scenarios, inventory, marine_tea, tea
    from biorefineries.ATT.analyses.breakdown import build_att_breakdown
    from biorefineries.ATT.analyses.s3_industrial import run as run_s3
    rows, balances, carbon, pseudo = [], [], [], []
    rate = float(tea._FIN['IRR'])
    duration = tea._FIN['duration']
    years = duration[1] - duration[0]
    crf = rate / (1 - (1 + rate) ** -years) if rate else 1 / years
    for enabled in (True, False):
        sys = scenarios.create(scenarios.ATT_S1, ree_recovery=enabled)
        t = build_att_breakdown('att_s1', sys=sys)
        summary, groups = t['summary'], t['OPEX_by_group']
        stream = inventory._streams(sys)
        wet = float(stream['att_sargassum_feed'].F_mass)
        dry = inventory._dry_feed_kgph(sys)
        h2 = float(stream['h2_product'].imass['H2'])
        coproduct = -float(groups.loc[groups['cost_type'] == 'Coproduct revenue', 'MUSD_per_yr'].sum()) * 1e6
        outputs = {s.ID: s for s in sys.products}
        def mass(ID):
            return float(outputs[ID].F_mass) if ID in outputs else 0.
        def component(ID, name):
            return float(outputs[ID].imass[name]) if ID in outputs else 0.
        flows = dict(char_cake=mass('att_char'), caco3=component('caco3_cake', 'CaCO3') + component('scrubber_cake', 'CaCO3'),
                     reo=component('ree_product', 'REO'),
                     wastewater=sum(mass(x) for x in tea._T['prices']['wastewater_streams']),
                     salt_cake=mass('salt_cake'), untracked_residue=mass('att_residue_untracked'))
        for st in stream.values():
            for species in ('ResidueCH', 'ResidueCHO', 'Char'):
                value = float(st.imass[species])
                if value > 1e-10:
                    pseudo.append(dict(ree_enabled=enabled, stream=st.ID, species=species,
                                       formula=st.chemicals[species].formula,
                                       phase=str(st.phase), kg_per_h=value,
                                       carbon_kg_per_h=float(st.imol[species]) * 12.011,
                                       boundary='input' if st in sys.feeds else 'output' if st in sys.products else 'internal'))
        s3 = run_s3(enable_ree_recovery=enabled)
        ref = marine_tea.s1_reference(sys)
        _, marine_hours, load = marine_tea.operating_mode()
        marine, _ = marine_tea.evaluate_case(sys, ref, 'S2', sources=('jacket', 'scavenge', 'exhaust'),
                                               hours=marine_hours, load=load)
        base_gwp = summary['GWP_kgCO2e_per_kg_H2']
        storage = summary['GWP_stored_carbon_credit_in_net_kgCO2e_per_kg_H2']
        cases = [dict(scenario='S1', hours=s3['operating_hours_per_year'], fci=summary['FCI_MUSD']*1e6,
                      net_aoc=summary['AOC_MUSD_per_yr']*1e6, msp=summary['MSP_USD_per_kg_H2'], gwp=base_gwp),
                 dict(scenario='S2', hours=marine_hours, fci=marine['FCI_USD'], net_aoc=marine['AOC_net_USD_per_yr'],
                      msp=marine['MSP_USD_per_kg_H2'], gwp=marine['GWP_kgCO2e_per_kg_H2']),
                 dict(scenario='S3', hours=s3['operating_hours_per_year'], fci=s3['s3_FCI_usd'],
                      net_aoc=s3['s3_net_AOC_usd_per_year'], msp=s3['s3_MSP_usd_per_kg_H2'],
                      gwp=s3['s3_GWP_kg_per_kg_H2'])]
        for c in cases:
            revenue = coproduct * c['hours'] / s3['operating_hours_per_year']
            result = normalize_case(wet_kgph=wet, dry_kgph=dry, h2_kgph=h2, hours=c['hours'], flows_kgph=flows,
                operating_cost_usd_year=c['net_aoc'] + revenue, coproduct_revenue_usd_year=revenue,
                capital_charge_usd_year=c['fci'] * crf, gross_gwp_per_kg_h2=c['gwp']-storage,
                credit_gwp_per_kg_h2=storage, msp_per_kg_h2=c['msp'])
            for basis in ('per_kg_h2', 'per_tonne_wet'):
                rows.append(dict(scenario=c['scenario'], ree_enabled=enabled, basis=basis,
                    wet_feed_kgph=wet, dry_feed_kgph=dry, moisture_fraction=1-dry/wet,
                    operating_hours=c['hours'], fci_usd=c['fci'], fci_per_annual_wet_t=c['fci']/result['annual']['wet_presscake_t'],
                    hydrogen_msp_usd_per_kg=c['msp'], **{'annual_' + k: v for k, v in result['annual'].items()}, **result[basis]))
        audit = inventory.check_att_inventory(sys)
        balances.append(dict(ree_enabled=enabled, mass_in_kgph=audit['mass_in_kgph'],
                             mass_out_kgph=audit['mass_out_kgph'], mass_relative_error=audit['mass_relative_error'],
                             **{f'{e}_relative_error': v for e, v in audit['element_relative_error'].items()}))
        carbon.extend(dict(ree_enabled=enabled, **x) for x in inventory.get_att_carbon_fate(sys))
    return rows, balances, carbon, pseudo


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, help='output directory (default: results/treatment_report)')
    args = p.parse_args()
    args.out = args.out or output_dir('treatment_report')
    rows, balances, carbon, pseudo = run()
    args.out.mkdir(parents=True, exist_ok=True)
    for name, data in (('functional_units.csv', rows), ('elemental_balances.csv', balances), ('carbon_flows.csv', carbon), ('pseudo_flows.csv', pseudo)):
        with (args.out / name).open('w', encoding='utf-8', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(data[0]))
            w.writeheader()
            w.writerows(data)
    print('Saved', args.out.resolve())

if __name__ == '__main__':
    main()

