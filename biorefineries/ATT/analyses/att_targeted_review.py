"""Six-case residue-disposal and reagent-LCA comparison, with unchanged chemistry.

The original zero-fee / zero-reagent-factor accounting remains reproducible.
Disposal is an explicitly assumed added VOC, not an assertion of residue phase.
"""
import argparse
import csv
from pathlib import Path


def evaluate(disposal_usd_per_kg=0.04):
    import math
    import biosteam as bst
    from biorefineries.ATT.analyses import tea, scenarios, inventory, lca, marine_tea
    from biorefineries.ATT.analyses.breakdown import build_att_breakdown
    from biorefineries.ATT.analyses.att_s3_industrial import run as run_s3
    if not math.isfinite(disposal_usd_per_kg) or disposal_usd_per_kg < 0:
        raise ValueError('disposal fee must be finite and nonnegative')
    rows=[]
    for enabled in (True, False):
        system=scenarios.create(scenarios.ATT_S1, ree_recovery=enabled)
        base=build_att_breakdown('att_s1',sys=system)
        streams=inventory._streams(system)
        hours=float(system.operating_hours)
        h2=float(streams['h2_product'].imass['H2'])
        wet=float(streams['att_sargassum_feed'].F_mass)
        residue=float(streams['att_residue_untracked'].F_mass)
        assert streams['att_residue_untracked'] in system.products
        assert 'att_residue_untracked' not in tea._T['prices']['solid_waste_streams']
        assert float(streams['att_residue_untracked'].price)==0
        fee=residue*hours*disposal_usd_per_kg
        hcl=(float(streams['fresh_hcl'].imass['HCl'])/.31 if enabled else 0.)
        ox=(float(streams['fresh_oxalic_acid'].imass['OxalicAcid']) if enabled else 0.)
        factors=lca._factors()
        hcl_gwp=hcl*factors['HCl_31']/h2
        ox_gwp=ox*factors['oxalic_acid']/h2
        ref=marine_tea.s1_reference(system)
        _, marine_hours, load=marine_tea.operating_mode()
        marine,whr=marine_tea.evaluate_case(system,ref,'S2',sources=('jacket','scavenge','exhaust'),hours=marine_hours,load=load)
        cfg=marine_tea.load_tea_config()
        share=float(cfg['s1_labor_share_of_foc'])
        foc=float(tea._FIN['foc_frac_of_fci'])
        steam=sum(a['assigned_kW']*a['usd_per_kWh'] for a in whr['assignments'] if 'steam' in a['sink_utility'])
        gas=sum(a['assigned_kW']*a['usd_per_kWh'] for a in whr['assignments'] if 'natural_gas' in a['sink_utility'])
        marine_voc=[('Marine WHR: purchased LP steam displaced',-steam*marine_hours),
                    ('Marine WHR: U2 furnace natural gas displaced (feed preheat)',-gas*marine_hours),
                    ('Marine WHR: pump electricity',whr['pump_kW']*bst.PowerUtility.price*marine_hours)]
        s3=run_s3(enable_ree_recovery=enabled)
        industrial_voc=[('Industrial WHR: avoided heat',-s3['avoided_cost_usd_per_year']),
                        ('Industrial WHR: auxiliary electricity',s3['auxiliary_electricity_cost_usd_per_year']),
                        ('Industrial WHR: heat purchase',s3['heat_purchase_cost_usd_per_year'])]
        cfg_s1=dict(operating_hours=hours)
        cfg_s2=dict(operating_hours=marine_hours,fci_factor=float(cfg['capex_multiplier']),
                    extra_capital=list(whr['equipment']),extra_voc=marine_voc,
                    foc_frac_of_fci=foc*(1-share),foc_fixed=float(cfg['labor_multiplier'])*share*foc*ref['FCI_USD'])
        cfg_s3=dict(operating_hours=hours,extra_capital=[('Industrial WHR installed screening allowance',s3['incremental_capex_usd'],'existing 500 USD/kW screen')],extra_voc=industrial_voc)
        cases=[('S1',cfg_s1,base['summary']['MSP_USD_per_kg_H2'],base['summary']['GWP_kgCO2e_per_kg_H2'],base['summary']['AOC_MUSD_per_yr']*1e6,base['summary']['FCI_MUSD']*1e6),
               ('S2',cfg_s2,marine['MSP_USD_per_kg_H2'],marine['GWP_kgCO2e_per_kg_H2'],marine['AOC_net_USD_per_yr'],marine['FCI_USD']),
               ('S3',cfg_s3,s3['s3_MSP_usd_per_kg_H2'],s3['s3_GWP_kg_per_kg_H2'],s3['s3_net_AOC_usd_per_year'],s3['s3_FCI_usd'])]
        credit=base['summary']['GWP_stored_carbon_credit_in_net_kgCO2e_per_kg_H2']
        years=tea._FIN['duration'][1]-tea._FIN['duration'][0]
        rate=float(tea._FIN['IRR'])
        crf=rate/(1-(1+rate)**(-years)) if rate else 1/years
        for scenario,kw,reference_msp,net,net_aoc,fci in cases:
            case_hours=kw['operating_hours']
            charge=residue*case_hours*disposal_usd_per_kg
            original=tea.evaluate_att_tea(system,**kw)['msp']
            if not math.isclose(original,reference_msp,rel_tol=1e-8,abs_tol=1e-8):
                raise ValueError(f'{scenario} reconstructed DCF differs from reference: {original} vs {reference_msp}')
            with_fee=dict(kw)
            with_fee['extra_voc']=list(kw.get('extra_voc',()))+[('Untracked residue disposal sensitivity',charge)]
            changed=tea.evaluate_att_tea(system,**with_fee)['msp']
            prior=net-hcl_gwp-ox_gwp
            rows.append(dict(scenario=scenario,ree_enabled=enabled,hours_per_year=case_hours,
                residue_kg_per_h=residue,wet_tonnes_per_year=wet*case_hours/1000,
                fee_usd_per_kg=disposal_usd_per_kg,fee_usd_per_year=charge,
                treatment_cost_original_usd_per_t_wet=(net_aoc+fci*crf)/(wet*case_hours/1000),
                treatment_cost_fee_usd_per_t_wet=(net_aoc+fci*crf+charge)/(wet*case_hours/1000),
                treatment_cost_delta_usd_per_t_wet=charge/(wet*case_hours/1000),
                msp_original_usd_per_kg_H2=original,msp_fee_usd_per_kg_H2=changed,
                msp_delta_usd_per_kg_H2=changed-original,
                hcl_31_solution_kg_per_h=hcl,oxalic_acid_kg_per_h=ox,
                hcl_gwp_per_kg_H2=hcl_gwp,oxalic_gwp_per_kg_H2=ox_gwp,
                gross_gwp_original_per_kg_H2=prior-credit,net_gwp_original_per_kg_H2=prior,
                gross_gwp_updated_per_kg_H2=net-credit,net_gwp_updated_per_kg_H2=net,
                gross_gwp_updated_per_t_wet=(net-credit)*h2*1000/wet,
                net_gwp_updated_per_t_wet=net*h2*1000/wet,
                reagent_factor_status='provisional; acid form/geography and GWP methods require verification'))
    return rows


def h3_screen(case):
    """Conditional gas-to-boiling-water area; not a host design or cost estimate."""
    import math
    source=next(x for x in case['sources'] if x['source']=='H3')
    duty=next(x for x in case['source_details'] if x['source']=='H3')
    q=float(duty['extracted_kW'])
    capacity=float(source['available_kW'])
    if capacity <= 0 or not 0 < q <= capacity:
        raise ValueError('H3 requires positive extraction not exceeding source availability')
    tin=float(source['T_in_C'])
    tout=tin-(tin-float(source['T_out_C']))*q/capacity
    steam=float(case['steam_agent']['temperature_C'])
    high=tin-steam
    low=tout-steam
    if low <= 0 or high <= 0:
        raise ValueError('positive temperature approach required')
    lmtd=high if abs(high-low)<1e-12 else (high-low)/math.log(high/low)
    return dict(extracted_kW=q, delivered_steam_kW=float(duty['steam_kW']),
                hot_in_C=tin,hot_out_C=tout,steam_C=steam,hot_approach_K=high,
                cold_approach_K=low,lmtd_K=lmtd,
                area_at_U_50_W_m2_K_m2=q*1000/(50*lmtd),
                area_at_U_15_W_m2_K_m2=q*1000/(15*lmtd),
                sizing_basis='conditional gas/boiling-water exchanger; assumes hot-side extraction as transferred heat; 10% loss not separately modeled in area')


def equipment_inventory(case):
    """Itemize the defensible scope; cost remains unpriced without host data."""
    h3=h3_screen(case)
    e=[]
    def add(item, sizing, necessity, reason):
        e.append(dict(equipment=item,design_basis=sizing,need=necessity,purchase_cost_usd='',
                      reference_year_currency='',installed_factor='',installed_cost_usd='',
                      confidence='not costable at present',source='See ATT targeted review: VDI heat-transfer range; NETL HRSG benchmark is not directly transferable',gap=reason))
    add('H1 high-temperature interface', 'H1 source; 1664.4-800 C; '+str(next(x['extracted_kW'] for x in case['source_details'] if x['source']=='H1'))+' kW extracted', 'required', 'Hot solid/material handling, heat transfer mechanism, metallurgy and host boundary unknown')
    add('H3 recovery / evaporator', 'Conditional gas assumption, LMTD %.2f K, U 15-50 W/m2/K, area %.1f-%.1f m2' % (h3['lmtd_K'],h3['area_at_U_50_W_m2_K_m2'],h3['area_at_U_15_W_m2_K_m2']), 'required if H3 available', 'Source phase/composition, gas flow, fouling and exchanger construction unverified; no suitable cost correlation')
    add('Intermediate heat transfer loop', 'Heat-transfer medium and duty not specified', 'conditional', 'Safety and host interface design needed; may be avoided by direct generation')
    add('Steam drum / separator', 'LP steam header %.2f C, %.1f kW useful' % (case['steam_agent']['temperature_C'],case['used_average_kW']), 'conditional', 'Depends on once-through vs drum boiler; may be integrated in evaporator package')
    add('Feedwater economizer', 'No sensible feedwater heating in current saturation model', 'conditional', 'Condensate return temperature unspecified; do not add duty or double count evaporator')
    add('Feedwater / circulation pumps', 'Auxiliary power %.2f kW is system placeholder' % case['auxiliary_average_kW'], 'required', 'Head, flow and number of pumps not established')
    add('Insulated piping and valves', 'Steam and possible intermediate loop', 'required', 'Route length, pipe diameter and pressure class unknown')
    add('Controls, safety and host retrofit', 'Instrumentation, refractory, isolations and integration', 'required', 'Host layout, tie-in specification and cost allocation unknown')
    return e


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',required=True,type=Path,help='New directory; no existing outputs replaced')
    p.add_argument('--fee',type=float,default=.04,help='Assumed USD/kg residue, default 0.04')
    a=p.parse_args()
    if a.out.exists(): raise FileExistsError(a.out)
    results=evaluate(a.fee)
    from biorefineries.ATT.analyses.att_s3_industrial import run as run_s3
    industrial=run_s3(enable_ree_recovery=True)
    h3=h3_screen(industrial)
    equipment=equipment_inventory(industrial)
    a.out.mkdir(parents=True,exist_ok=False)
    with (a.out/'six_case_sensitivity.csv').open('x',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(results[0]));w.writeheader();w.writerows(results)
    for name, data in (('s3_conditional_h3_sizing.csv',[h3]),('s3_equipment_inventory.csv',equipment)):
        with (a.out/name).open('x',encoding='utf-8',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
    print('Saved',a.out.resolve())

if __name__=='__main__': main()
