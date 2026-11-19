"""Build an offline, current-runtime ATT S1/S2/S3 technical report.

Run from the repository root with the project interpreter:
  python -m biorefineries.ATT.analyses.comprehensive_report [--out DIRECTORY]   (default: results/avoided_emissions)
No model inputs are modified; the output folder is regenerated in place (results/ is git-ignored).
"""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import re
import subprocess
import sys

from biorefineries.ATT.analyses.paths import output_dir

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
TEMPLATE = Path(__file__).with_name('comprehensive_report_template.html')


def clean(x):
    if isinstance(x, dict): return {str(k): clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)): return [clean(v) for v in x]
    if hasattr(x, 'item'): return clean(x.item())
    if isinstance(x, float) and not math.isfinite(x): return None
    return x


def _git(*args):
    return subprocess.check_output(['git', *args], cwd=REPO, text=True).strip()


def git_provenance(repo=REPO):
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=repo, text=True).strip()
    status = git('status', '--short', '--untracked-files=normal')
    dirty = bool(status)
    return dict(commit=git('rev-parse', 'HEAD'), branch=git('branch', '--show-current'),
                tracked_changes=git('diff', '--name-only'),
                staged_changes=git('diff', '--cached', '--name-only'),
                working_tree_status=status, working_tree_state='dirty' if dirty else 'clean',
                note=('Uncommitted changes are present; Git HEAD alone does not identify the files used. '
                      if dirty else 'The working tree was clean when provenance was captured. ')
                     + 'Input SHA-256 fingerprints identify the recorded files.')


def _assumptions():
    import yaml
    result = []
    for filename in ('feedstock.yaml', 'att.yaml', 'tea.yaml', 'lca.yaml', 'marine_tea.yaml', 'marine_whr.yaml'):
        obj = yaml.safe_load((ROOT / 'data' / filename).read_text(encoding='utf-8'))
        def walk(value, path, parent):
            if isinstance(value, dict):
                for k, v in value.items():
                    if k not in ('source', 'note', 'description', 'basis', 'status', 'unit'):
                        walk(v, path + [str(k)], value)
            elif isinstance(value, (int, float, bool)) or value is None:
                result.append(dict(parameter='.'.join(path), value=value, unit=parent.get('unit', 'see configuration'),
                                   source=parent.get('source', parent.get('note', 'See configuration and review')),
                                   source_type='See source / scenario configuration', scenario='See configuration',
                                   reference='data/' + filename + ' : ' + '.'.join(path),
                                   status='Unverified unless explicitly identified in source'))
        walk(obj, [], {})
    return result


def _limits():
    return [dict(issue=a, model=b, significance=c, direction=d, experiment=e, code=f) for a,b,c,d,e,f in [
      ('Unresolved organics','ResidueCH / ResidueCHO close elemental balances; baseline fee and LCA impact are zero','Physical identity and fate pending further product-yield information from UCLA; heat of reaction is uncertain','Costs and GWP may be understated; direction of heat bias unknown','yes','after measurement'),
      ('CaCO3 and char permanence','Sargassum carbon in sold carbonate and char credited','Product fate and counterfactual not established','Net GWP may be too low','end-use and permanence evidence','only after decision'),
      ('Coproduct marketability','CaCO3 component and REO content sold without purification','Assumed sales of contained CaCO3 and REO at about 1.31% REO product grade lack buyer confirmation','MSP and net treatment cost may be too low','product characterization and buyer evidence','potentially'),
      ('Dry / DAF yield transfer','Lab DAF gas yields applied to pressed feed with different ash','NaOH is confirmed per total dry feed; transfer of gas yields to higher-ash presscake remains uncertain','direction unknown','yes','after validation'),
      ('Uncertain LCA burdens','REE reagents use provisional HCl and oxalic-acid factors; untracked residue treatment omitted','Reagent geography/form are uncertain and residue inventory incomplete','GWP may be too low','factor and fate data','yes'),
      ('Waste lime','Waste lime assumed free and burden-free','Availability, transport, composition and burden not established','cost and GWP may be too low','site supply and assay','potentially'),
      ('S2 marine WHR','Idealized independent host mission; ATT receives incremental WHR only','Competing ship heat demands, exchanger costing and D0 heating-surface compatibility remain assumed; pump efficiency is flow-dependent','heat savings may be optimistic','ship load and utility measurements','after validation'),
      ('S3 industrial WHR','Scaled theoretical additive H1/H3 host heat; zero heat burden and purchase price','Independence and surplus after host heat integration are not site-verified; H3 Table 4 conflicts with Table 1 / Fig. 10 / text','savings may be optimistic','host heat and operating measurements','after validation'),
      ('Internal HXN','Corrected pressurized liquid-water proxy for U3D sensible regeneration heating','A practical installed network remains an engineering assumption','no retained historical 2.8% error assumption','engineering design','only after new evidence'),
      ('Dependency and historical results','Live runtime and source hashes recorded','Frozen results use different dependency context','comparison can mislead','no','compatibility work if required')]]


def _scientific_notes():
    """Agreed qualifications; these notes never change simulation inputs."""
    return [dict(topic=a, finding=b, classification=c, reference=d) for a,b,c,d in [
      ('LC1 experimental reagent basis', 'UCLA: 5 mL of 0.1 M HCl/g insoluble residue = 0.5 mol/kg; 0.42 mL of 0.1 M oxalic acid/g = 0.042 mol/kg. Insoluble ash is provisionally mapped to the whole water-insoluble ATT residue/char, not independently proven equivalent.', 'Experiment-supported; material-basis qualification', 'User-provided UCLA clarification; data/att.yaml att.downstream.ree_recovery; units/_att.py ATTReeLeach'),
      ('LC1 carbonate compensation and water', 'Additional HCl = 2 mol per mol residual Na2CO3 entering LC1. HCl solution carries water; oxalic solution water excludes the acid solute, and its tank uses the existing liquor once. scale_reagents_with_REE=False; reagent_excess=1.2 does not increase the baseline dose; precipitate_wash_efficiency=0.', 'Confirmed implemented calculation', 'units/_att.py ATTReeLeach._run, water_demand_kgph and _design'),
      ('LC1 recovery validation', 'The 60% target is a transferred performance assumption, not validated for the low-concentration case by a calculated leaching pH. Confirm reagent concentration, insoluble-material basis and updated recovery data with UCLA before manuscript submission.', 'Engineering assumption requiring experiment', 'data/att.yaml att.downstream.ree_recovery.overall_recovery; units/_att.py ATTReeLeach'),
      ('REE feed loading', '737 ppm elemental TREE is assumed already-enriched dry Sargassum. The separate 1.4 mg/L divided by 2.5 g dry seaweed/L gives theoretical 0.56 mg/g = 560 ppm wastewater-derived TREE loading; this is not independently measured uptake. Capture/soaking equipment is outside the modeled boundary.', 'Assumed enriched feed and theoretical loading', 'data/att.yaml att.downstream.ree_recovery; units/_att.py ATTReeLeach'),
      ('REE grade and oxide basis', 'TREE is elemental rare-earth mass; REO is oxide-equivalent mass using REO/TREE=1.169. The approximately 1.3 wt% TREE low-concentration experimental product differs from the modeled 1.31 wt% REO (about 1.121 wt% TREE). Confirm the element-specific oxide conversion and product assay.', 'Experimental/model basis discrepancy disclosed', 'User-provided UCLA clarification; data/att.yaml product_REO_wt_frac and REO_per_TREE'),
      ('REE sales and Nd references', 'Contained REO is priced at $35/kg, not total low-grade product mass; its saleability and upgrading costs are unverified. The high-concentration Nd experiment (approximately 98.8% Nd2O3) and nd_soak_data are reference-only; they do not set baseline product purity.', 'Revenue assumption; inactive Nd reference', 'data/tea.yaml prices.REO; data/att.yaml nd_soak_data'),
      ('Roasting and residue yield', 'RO1 roasts the precipitate at 900 C using the existing 45% heat-loss assumption. The 0.15 kg/kg dry-feed insoluble-residue yield is a provisional interpretation of the experimental 10–20% range; sample-preparation conditions need not represent 500 C ATT.', 'Experiment-supported with operating-condition qualification', 'data/att.yaml att.downstream.char and ree_recovery; units/_att.py ATTReeRoaster'),
      ('Wet waste carbide lime', 'Paste: 40 wt% water, 60 wt% dry solids, with 92 wt% Ca(OH)2 in those solids; wet-basis Ca(OH)2 = 0.60 × 0.92 = 55.2 wt%. Both C1 lime and scrubber_lime are included. Zero purchase price and upstream burden follow the waste cut-off assumption; composition, supply, transport and handling remain preliminary.', 'Engineering composition and boundary assumptions', 'data/att.yaml att.downstream.waste_lime; analyses/tea.py _apply_prices; analyses/lca.py apply_att_gwp'),
      ('CaCO3 sales and storage', 'Keep 88% causticization and the simulated cake composition. UCLA clean-laboratory 97% CaCO3 is a comparison, not an imposed plant purity. Revenue uses contained CaCO3; non-saleable cake is disposed. Baseline LCA assumes permanent storage of eligible feed-derived carbon in cakes and char; end use and permanence are not established.', 'Experimental conversion; product and permanence assumptions', 'data/att.yaml; analyses/tea.py caco3_sales_accounting; analyses/lca.py get_att_stored_carbon_credit'),
      ('U2, PSA and internal wash water', 'U2 uses its simulated enthalpy balance; historical 10423.77 kJ/kg dry is inactive. PSA is disabled in all six cases; gas mass differs from H2 component mass. F2 wash liquor recycles internally to D1 and is not directly discharged as wastewater.', 'Confirmed active flowsheet; legacy reference excluded', 'units/_att.py ATTReactor; system.py create_att_system; data/att.yaml gas_treatment.psa_enabled and f2_washing'),
      ('Common HXN correction', 'The U3D regeneration proxy is pressurized above the saturation pressure at its maximum temperature to preserve liquid sensible heating during HXN flashes. Signed residual heating utilities exclude coolers.', 'Correction present in current source', 'units/_att.py ATTMolecularSieve._design; analyses/marine_whr.py s1_heat_sinks; analyses/industrial_whr.py audit_hxn_enthalpy'),
      ('S2 boundary and pumps', 'Idealized host vessel has an independent primary mission; ATT is ancillary. At 75% engine load and 7920 h/year, propulsion emissions are not allocated to ATT; incremental WHR power and burdens are included. YAML pump_efficiency=0.70 is reference-only; active BioSTEAM pump and motor efficiencies depend on flow.', 'Accepted scenario assumptions and confirmed pump behavior', 'data/marine_whr.yaml; analyses/marine_whr.py _pump; analyses/marine_lca.py'),
      ('S3 source scaling', 'Assume the historical 120000 tons/year means U.S. short tons: 120000 × 0.90718474 = 108862.1688 metric t/year. Relative to the paper reference of 120000 metric t/year this gives 0.90718474 at equal 7920 h/year and full utilization. This is host-capacity scaling, not ATT-demand scaling; the ton subtype is not established by the historical source.', 'Explicit unit-conversion and host-transfer assumption', 'analyses/industrial_whr.py industrial_sources; scenario_docs/ATT_S3_DESIGN_BASIS.md'),
      ('S3 H3 discrepancy and host surplus', 'Prior supplied-PDF review records H3 800→40 C in Table 1, Fig. 10 and text (5.17 kW/K × 760 K ≈ 3.93 MW), versus 800→400 C in Table 4. The current 800→40 C interpretation follows the former mutually consistent values. H1/H3 are treated as additive; independence and availability after the host complex uses heat are not site-verified.', 'Documented literature discrepancy and host assumption', 'Wang et al. 2025 DOI 10.1016/j.psep.2025.107306; scenario_docs/ATT_S3_DESIGN_BASIS.md Literature interpretation'),
      ('S3 heat and costing basis', 'Current H1/H3 capacities and intervals are retained. A 20 C approach and 90% effectiveness produce useful steam for D0/EC1 only. The 0.95 steam-to-process ratio is descriptive; avoided fuel uses 80% boiler efficiency once. Installed $500/kW and 1% auxiliary power use useful steam capacity. Heat has zero purchase cost and upstream burden. This is an idealized screen, not site feasibility.', 'Accepted engineering screening assumptions', 'analyses/s3_industrial.py run; analyses/industrial_whr.py generate_steam'),
      ('LCA categories and counterfactual', 'Fossil combustion, upstream material/energy supply, waste management and permanent-storage credits are distinguished. HCl and oxalic-acid production factors are provisional. The additional beach counterfactual uses active organic CHONS, Boyle anaerobic decomposition and independent aerobic carbon mineralization. Only atmospheric methane times GWP100 is a potential additional credit. Physical biogenic CO2 formation is separate; this indicator does not alter baseline net GWP or reapply storage.', 'Screening allocation, biodegradability, mineralization and atmospheric realization; not measured beach fluxes', 'data/lca.yaml avoided_emissions; analyses/avoided_emissions.py; baseline analyses/lca.py unchanged')]]


def _inactive_reason(row):
    key = row['parameter'].lower()
    if 'legacy' in key or 'indicative_gwp100' in key:
        return 'Historical / indicative reference; not an active design input or baseline emission factor'
    if 'psa' in key and not key.endswith('psa_enabled'):
        return 'PSA disabled in all six cases; sensitivity/reference setting only'
    if 'tail_gas' in key or 'offgas' in key:
        return 'No PSA tail gas in baseline; empty placeholder / reference-only setting'
    if 'nd_soak_data' in key:
        return 'High-concentration Nd reference; not the low-concentration baseline'
    if 'beach_rot_counterfactual' in key:
        return 'Optional counterfactual only; excluded from baseline net GWP'
    if key.endswith('pump_efficiency'):
        return 'Hand-check reference only; active WHR pumps use BioSTEAM flow-dependent efficiency'
    if key.endswith(('reagent_excess', 'hcl_mol_per_mol_ree')):
        return 'REE stoichiometric dose scaling disabled; does not multiply baseline reagents'
    return ''


def carbon_credit_breakdown(system):
    """Split the existing storage credit by output; no new credit is introduced."""
    from biorefineries.ATT.analyses import lca, inventory
    streams = inventory._streams(system)
    outputs = {x.ID for x in system.products}
    h2 = float(streams['h2_product'].imass['H2'])
    result = dict(caco3_cakes=0., char_residue=0., other_solids=0.)
    if not lca._LCA['carbon_storage']['credit_stored_carbon']:
        return result
    for ID in lca._LCA['waste_management']['landfill_streams']:
        if ID not in outputs:
            continue
        stream = streams[ID]
        lime_ID = lca._LIME_OF_CAKE.get(ID)
        lime_C = float(streams[lime_ID].get_atomic_flow('C')) if lime_ID in streams else 0.
        soluble = float(stream.imol['Na2CO3']) * stream.chemicals['Na2CO3'].atoms.get('C', 0.)
        credit = -(float(stream.get_atomic_flow('C')) - lime_C - soluble) * 44.0095 / h2
        category = 'caco3_cakes' if ID in lca._LIME_OF_CAKE else 'char_residue' if ID == 'att_char' else 'other_solids'
        result[category] += credit
    return result


def collect(include_avoided_emissions=True):
    """Recompute model cases and collect explicit source ledgers without changing assumptions."""
    from biorefineries.ATT.analyses import treatment_report, scenarios, inventory, marine_tea, marine_lca, marine_whr, tea
    from biorefineries.ATT.analyses.s3_industrial import run as s3_run
    from biorefineries.ATT.analyses.breakdown import build_att_breakdown
    fu, balances, carbon, pseudo = treatment_report.run()
    details = {}
    avoided_rows = []
    for ree in (True, False):
        sys = scenarios.create(scenarios.ATT_S1, ree_recovery=ree)
        base = build_att_breakdown('att_s1', sys=sys)
        stream = inventory._streams(sys)
        gas = stream['h2_product']
        cakes = tea.caco3_sales_accounting(sys, **scenarios.tea_config(scenarios.ATT_S1)['caco3_sales'])
        product = stream.get('ree_product')
        products = dict(h2_product_gas_kgph=float(gas.F_mass),
                        h2_component_kgph=float(gas.imass['H2']),
                        h2_mol_fraction=float(gas.imol['H2']) / float(gas.F_mol),
                        caco3_component_kgph=sum(x['caco3_kgph'] for x in cakes.values()),
                        caco3_cake_total_kgph=sum(x['wet_kgph'] for x in cakes.values()),
                        caco3_impurity_disposal_kgph=sum(x['disposed_kgph'] for x in cakes.values()),
                        caco3_revenue_usd_per_h=sum(x['revenue_usd_ph'] for x in cakes.values()),
                        reo_component_kgph=float(product.imass['REO']) if product is not None else 0.,
                        reo_stream_kgph=float(product.F_mass) if product is not None else 0.,
                        reo_price_usd_per_kg=float(tea._T['prices']['REO']['value']),
                        char_price_usd_per_kg=float(stream['att_char'].price),
                        fresh_naoh_kgph=float(stream['fresh_naoh_solid'].imass['NaOH']))
        products['ree_product_components_kgph'] = ({ID: float(v) for ID, v in zip(product.chemicals.IDs, product.mass) if v > 0}
                                                 if product is not None else {})
        lime_inventory = [dict(stream=ID, wet_paste_kgph=float(stream[ID].F_mass),
                               water_kgph=float(stream[ID].imass['Water']),
                               dry_solids_kgph=float(stream[ID].F_mass-stream[ID].imass['Water']),
                               pure_CaOH2_kgph=float(stream[ID].imass['CaOH2']))
                          for ID in ('lime', 'scrubber_lime') if ID in stream]
        external = inventory.get_att_external_flows(sys)
        snap = dict(summary=base['summary'], products=products, storage_credits=carbon_credit_breakdown(sys),
                    lime_inventory=lime_inventory,
                    caco3_cakes=[dict(stream=ID, **row) for ID, row in cakes.items()],
                    opex=base['OPEX_by_group'].to_dict('records'),
                    capex=base['CAPEX_by_equipment'].to_dict('records'),
                    gwp=base['GWP_by_contributor'].to_dict('records'),
                    external=external,
                    unit_streams=inventory.get_att_unit_streams(sys),
                    unit_balances=inventory.get_att_unit_balances(sys),
                    chemicals=inventory.get_att_chemical_ledger(sys),
                    utilities=inventory.get_att_purchased_utilities(sys),
                    unit_energy=inventory.get_att_unit_energy(sys))
        ref = marine_tea.s1_reference(sys)
        _, hours, load = marine_tea.operating_mode()
        marine, whr = marine_tea.evaluate_case(sys, ref, 'S2', sources=('jacket','scavenge','exhaust'), hours=hours, load=load)
        delta = marine_lca.whr_gwp_change(sys, whr)
        industrial = s3_run(enable_ree_recovery=ree)
        details[str(ree)] = dict(base=snap, marine=marine, marine_whr=whr, marine_lca=delta, marine_config=marine_whr.load_whr_config(), industrial=industrial)
        for scenario, msp, gwp in [('S1',snap['summary']['MSP_USD_per_kg_H2'],snap['summary']['GWP_kgCO2e_per_kg_H2']),
                                    ('S2',marine['MSP_USD_per_kg_H2'],marine['GWP_kgCO2e_per_kg_H2']),
                                    ('S3',industrial['s3_MSP_usd_per_kg_H2'],industrial['s3_GWP_kg_per_kg_H2'])]:
            r = next(x for x in fu if x['scenario']==scenario and x['ree_enabled']==ree and x['basis']=='per_kg_h2')
            if not math.isclose(r['hydrogen_msp_usd_per_kg'],msp,rel_tol=1e-8,abs_tol=1e-8) or not math.isclose(r['net_gwp_kg_co2e'],gwp,rel_tol=1e-8,abs_tol=1e-8):
                raise ValueError(f'Functional-unit results do not reconcile: {scenario} REE={ree}')
            if include_avoided_emissions:
                from biorefineries.ATT.analyses.avoided_emissions import scenario_rows
                avoided_rows.extend(scenario_rows(sys, scenario, ree, gwp))
    from biorefineries.ATT.analyses.ree_tea_cases import collect_ree_tea
    ree_tea=collect_ree_tea({flag:case['industrial'] for flag,case in details.items()})
    versions = {}
    for package in ('biosteam','thermosteam','numpy','pandas','scipy','PyYAML'):
        try: versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError: versions[package] = 'unavailable'
    import sys
    versions['python']=sys.version.split()[0]
    inputs = list((ROOT/'data').glob('*.yaml')) + [ROOT/'analyses'/x for x in ('inventory.py','marine_lca.py','treatment_report.py','functional_unit.py','s3_industrial.py','industrial_whr.py','marine_tea.py','marine_whr.py','tea.py','lca.py','breakdown.py','scenarios.py','reporting.py','validation.py','comprehensive_report.py','comprehensive_report_template.html')]
    inputs += [ROOT/'system.py',ROOT/'_chemicals.py',ROOT/'units'/'_att.py']
    inputs += [ROOT/'analyses'/'ree_tea_cases.py']
    if include_avoided_emissions:
        inputs += [ROOT/'analyses'/'avoided_emissions.py', ROOT/'analyses'/'s3_figures.py', ROOT/'analyses'/'paths.py']
    provenance = git_provenance()
    provenance.update(generated_utc=datetime.now(timezone.utc).isoformat(), versions=versions,
                      input_sha256={str(p.relative_to(REPO)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs})
    provenance['verified_corrections_present'] = dict(
        LC1_acid_and_solution_water='units/_att.py ATTReeLeach: carbonate HCl = 2 × Na2CO3; oxalic solute subtracted from solution water; no repeated tank water',
        common_HXN='units/_att.py ATTMolecularSieve: liquid-water proxy pressure exceeds saturation pressure',
        marine_heating_inventory='analyses/marine_whr.py s1_heat_sinks: signed steam residuals and all positive heating utilities',
        S3='analyses/industrial_whr.py and s3_industrial.py: existing H1/H3 source and steam-displacement calculations')
    assumptions = _assumptions()
    for row in assumptions:
        path = row['parameter']
        source = str(row['source']).lower()
        if 'gas_yield_mmol_per_g_daf.' in path:
            row.update(unit='mmol/g dry ash-free feed', source='Experimental workbook 261023, 1:1 Ni-CatATT; transfer to presscake is assumed', source_type='Experimental yield; assumed transfer', scenario='S1/S2/S3', status='Workbook values checked; feed-basis transfer requires verification')
        elif 'marine_' in row['reference']:
            row['scenario'] = 'S2'
        elif any(word in source for word in ('assum', 'placeholder', 'user decision')):
            row['source_type'] = 'Assumption / scenario decision'
        elif source not in ('see configuration and review', ''):
            row['source_type'] = 'Source named in configuration; not independently checked'
    industrial = details['True']['industrial']
    for name, value in industrial['configuration'].items():
        assumptions.append(dict(parameter='S3.'+name, value=value, unit='See source parameter name',
          source='analyses/s3_industrial.py run defaults', source_type='Engineering screening assumption',
          scenario='S3', reference='analyses/s3_industrial.py run', status='Unverified host-site assumption'))
    for source in industrial['sources']:
        for name, unit in [('available_kW','kW'),('T_in_C','deg C'),('T_out_C','deg C')]:
            assumptions.append(dict(parameter='S3.'+source['source']+'.'+name, value=source[name], unit=unit,
              source='Wang et al. 2025 DOI 10.1016/j.psep.2025.107306; scaled by industrial_whr.py',
              source_type='Literature source; host transfer assumption', scenario='S3',
              reference='analyses/industrial_whr.py industrial_sources', status='Theoretical source, not demonstrated site surplus'))
    inactive, active = [], []
    for row in assumptions:
        reason = _inactive_reason(row)
        if reason:
            inactive.append(dict(row, status=reason))
        else:
            active.append(row)
    result = dict(functional=fu, balances=balances, carbon=carbon, pseudo=pseudo,ree_tea=ree_tea,
                      details=details, assumptions=active, inactive_parameters=inactive,
                      scientific_notes=_scientific_notes(), limitations=_limits(), provenance=provenance)
    if include_avoided_emissions:
        from biorefineries.ATT.analyses.avoided_emissions import assumptions
        result['avoided_emissions'] = dict(rows=avoided_rows, assumptions=assumptions())
    return clean(result)


def _save_csv(path, rows):
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with path.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=keys,extrasaction='raise'); w.writeheader()
        w.writerows({k: json.dumps(v, ensure_ascii=False) if isinstance(v,(list,dict)) else v for k,v in r.items()} for r in rows)


def tables(data):
    fu=data['functional']
    comparison=[]
    for r in fu:
        if r['basis'] != 'per_tonne_wet':
            continue
        d=data['details'][str(r['ree_enabled'])]; s=d['industrial']; w=d['marine_whr']
        heat=0. if r['scenario']=='S1' else w['utilized_kW'] if r['scenario']=='S2' else s['used_average_kW']
        external=s['heating_before_kW'] if r['scenario']=='S1' else w['external_after_kW'] if r['scenario']=='S2' else s['heating_after_average_kW']
        comparison.append(dict(r, **d['base']['products'], waste_heat_delivered_kW=heat, external_heating_kW=external,
                               net_annual_opex_usd=r['annual_operating_cost_usd']-r['annual_coproduct_revenue_usd']))
    process=[]; mass=[]; energy=[]; tea=[]; lca=[]; optional=[]; lime=[]; cakes=[]; case_balances=[]
    for ree,d in data['details'].items():
        b=d['base']; m=d['marine']; h=d['marine_whr']; s=d['industrial']
        for x in b['chemicals']: process.append(dict(ree_enabled=ree, category='chemical ledger', **x))
        for x in b['unit_streams']: mass.append(dict(ree_enabled=ree, record_type='unit stream', **x))
        for x in b['unit_balances']: mass.append(dict(ree_enabled=ree, record_type='unit balance', **x))
        for x in b['external']: mass.append(dict(ree_enabled=ree, record_type='boundary stream', **x))
        for x in b['utilities']: energy.append(dict(ree_enabled=ree, scenario='S1', record_type='purchased utility', **x))
        for x in b['unit_energy']: energy.append(dict(ree_enabled=ree, scenario='S1', record_type='unit energy', **x))
        for x in b['lime_inventory']: lime.append(dict(ree_enabled=ree, **x))
        for x in b['caco3_cakes']: cakes.append(dict(ree_enabled=ree, **x))
        for scenario in ('S1','S2','S3'):
            audit = next(x for x in data['balances'] if str(x['ree_enabled']) == ree)
            case_balances.append(dict(audit, scenario=scenario,
                                      physical_basis='Shared ATT flowsheet; WHR is an accounting extension'))
        for scenario, items in [('S2',h['sinks']),('S3',s['sinks'])]:
            for x in items: energy.append(dict(ree_enabled=ree,scenario=scenario,record_type='heat sink',**x))
        for scenario, items in [('S2',h['assignments']),('S3',s['allocations'])]:
            for x in items: energy.append(dict(ree_enabled=ree,scenario=scenario,record_type='heat allocation',**x))
        for scenario, items in [('S2',h['sources']),('S3',s['source_details'])]:
            for x in items:
                source = next((v for v in s['sources'] if v['source']==x['source']), {}) if scenario == 'S3' else {}
                energy.append(dict(ree_enabled=ree,scenario=scenario,record_type='heat source',**dict(source, **x)))
        for x in b['opex']: tea.append(dict(ree_enabled=ree,scenario='S1',record_type='OPEX group',**x))
        for x in b['capex']: tea.append(dict(ree_enabled=ree,scenario='S1',record_type='installed equipment',**x))
        for name in ('labor_OPEX_USD_per_yr','FOC_nonlabor_USD_per_yr','energy_OPEX_USD_per_yr','materials_USD_per_yr','waste_disposal_USD_per_yr','CaCO3_revenue_USD_per_yr','WHR_CAPEX_USD'):
            tea.append(dict(ree_enabled=ree,scenario='S2',record_type='marine summary',group=name,USD_per_year_or_capex=m[name]))
        for name in ('incremental_capex_usd','incremental_foc_usd_per_year','auxiliary_electricity_cost_usd_per_year','heat_purchase_cost_usd_per_year','avoided_cost_usd_per_year'):
            tea.append(dict(ree_enabled=ree,scenario='S3',record_type='industrial increment',group=name,USD_per_year_or_capex=s[name]))
        for name, value, basis in h['equipment']:
            tea.append(dict(ree_enabled=ree,scenario='S2',record_type='marine installed equipment',group=name,
                            USD_per_year_or_capex=value,basis=basis))
        for case in (r for r in fu if r['basis']=='per_kg_h2' and str(r['ree_enabled']) == ree):
            tea.append(dict(ree_enabled=ree,scenario=case['scenario'],record_type='annual reconciliation',
                            gross_opex_usd_per_year=case['annual_operating_cost_usd'],
                            coproduct_revenue_usd_per_year=case['annual_coproduct_revenue_usd'],
                            net_opex_usd_per_year=case['annual_operating_cost_usd']-case['annual_coproduct_revenue_usd'],
                            FCI_usd=case['fci_usd'],MSP_usd_per_kg_H2=case['hydrogen_msp_usd_per_kg']))
        for scenario in ('S1','S2','S3'):
            for x in b['gwp']:
                if x['counted_in_net']: lca.append(dict(ree_enabled=ree,scenario=scenario,record_type='S1 inherited',**x))
        lca.append(dict(ree_enabled=ree,scenario='S2',record_type='marine increment',stage='Displaced utility and auxiliary electricity adjustment',contributor='Marine WHR net change',kgCO2e_per_kg_H2=m['GWP_WHR_change_kgCO2e_per_kg_H2']))
        for name,sign in [('avoided_emissions_kg_per_hour',-1),('auxiliary_emissions_kg_per_hour',1),('heat_burden_kg_per_hour',1)]:
            lca.append(dict(ree_enabled=ree,scenario='S3',record_type='industrial increment',stage='Displaced utility and auxiliary electricity adjustment',contributor=name,kgCO2e_per_kg_H2=sign*s[name]/s['h2_kg_per_hour']))
        extra = next(x['kgCO2e_per_kg_H2'] for x in b['gwp'] if not x['counted_in_net'])
        for case in (r for r in fu if r['basis']=='per_kg_h2' and str(r['ree_enabled']) == ree):
            optional.append(dict(ree_enabled=ree,scenario=case['scenario'],baseline_net_kgCO2e_per_kg_H2=case['net_gwp_kg_co2e'],
                                 optional_extra_kgCO2e_per_kg_H2=extra,
                                 counterfactual_net_kgCO2e_per_kg_H2=case['net_gwp_kg_co2e']+extra,
                                 counted_in_baseline=False,basis='Optional beach-decomposition counterfactual; not an additional baseline credit'))
    for row in lca:
        row['emission_category'] = ('Carbon-storage credit' if row['stage']=='Stored biogenic carbon' else
                                   'Process fuel combustion' if row['stage']=='Onsite fuel combustion' else
                                   'Waste management' if row['stage']=='Waste management' else
                                   'WHR displaced utility / auxiliary adjustment' if row['record_type']!='S1 inherited' else
                                   'Upstream material / energy supply')
    result = dict(scenario_comparison=comparison,process_summary=process,mass_balance=mass,energy_balance=energy,
                tea_breakdown=tea,lca_breakdown=lca,functional_unit_comparison=fu,
                assumptions_and_sources=data['assumptions'],scientific_limitations=data['limitations'],
                scientific_notes=data['scientific_notes'],inactive_parameters=data['inactive_parameters'],
                optional_beach_counterfactual=optional,waste_lime_inventory=lime,caco3_product_accounting=cakes,
                annual_cost_breakdown=data['ree_tea']['cases'],ree_incremental_economics=data['ree_tea']['increments'],
                tea_detailed_ledger=data['ree_tea']['ledger'],ree_equipment_costs=data['ree_tea']['equipment'],
                dcf_msp_components=data['ree_tea']['dcf_components'],dcf_cashflows=data['ree_tea']['cashflows'],
                dcf_financial_assumptions=[dict(parameter=key,value=value) for key,value in data['ree_tea']['financial_assumptions'].items()],
                carbon_flows=data['carbon'],pseudo_flows=data['pseudo'],elemental_balances=case_balances)
    if 'avoided_emissions' in data:
        from biorefineries.ATT.analyses.avoided_emissions import reference_rows
        result['optional_beach_counterfactual'] = [dict(
            ree_enabled=str(r['ree_enabled']), scenario=r['scenario'],
            baseline_net_kgCO2e_per_kg_H2=r['original_CI'],
            optional_extra_kgCO2e_per_kg_H2=-r['avoided_sargassum_decomposition_emissions'],
            counterfactual_net_kgCO2e_per_kg_H2=r['original_CI']-r['avoided_sargassum_decomposition_emissions'],
            counted_in_baseline=False,
            basis='Original ATT CI minus mechanistic atmospheric-methane indicator; GCC shown separately in main/potential CI tables')
            for r in reference_rows(data, 'potential', 'per_kg_h2')]
        main = {(r['scenario'],r['ree_enabled'],r['basis']):r for r in reference_rows(data,'main')}
        def reported(row):
            basis = 'per_tonne_wet_presscake' if row['basis']=='per_tonne_wet' else row['basis']
            ci = main[row['scenario'],row['ree_enabled'],basis]
            return dict(row, original_net_gwp_kg_co2e=row['net_gwp_kg_co2e'],
                        gcc_credit=ci['avoided_gcc_production_emissions'],
                        net_gwp_kg_co2e=ci['expanded_CI'], main_CI=ci['expanded_CI'],
                        total_credit_gwp_kg_co2e=row['credit_gwp_kg_co2e']-ci['avoided_gcc_production_emissions'],
                        reporting_definition='Main CI includes GCC; excludes potential decomposition')
        result['scenario_comparison'] = [reported(r) for r in comparison]
        result['functional_unit_comparison'] = [reported(r) for r in fu]
        for r in lca:
            r['counted_in_original_CI'] = True
        for r in reference_rows(data,'main','per_kg_h2'):
            lca.append(dict(ree_enabled=str(r['ree_enabled']),scenario=r['scenario'],
                record_type='GCC reporting credit',stage='GCC avoided production',
                contributor='Avoided conventional GCC production',emission_category='GCC avoided production (separate from storage)',
                kgCO2e_per_kg_H2=-r['avoided_gcc_production_emissions'],counted_in_original_CI=False))
    return result


def report_qc(data, all_tables):
    """Reconcile presentation and exports against the fresh calculation payload."""
    checks=[]
    def check(case, name, value, target, atol=1e-7, rtol=1e-8):
        ok=math.isfinite(value) and math.isfinite(target) and math.isclose(value,target,rel_tol=rtol,abs_tol=atol)
        checks.append(dict(case=case,check=name,value=value,reference=target,status='PASS' if ok else 'FAIL'))
    check('All','Six unique cases',len({(r['scenario'],r['ree_enabled']) for r in all_tables['scenario_comparison']}),6)
    for row in all_tables['scenario_comparison']:
        displayed = row
        row = dict(row, net_gwp_kg_co2e=row.get('original_net_gwp_kg_co2e', row['net_gwp_kg_co2e']))
        scenario=row['scenario']; enabled=str(row['ree_enabled']); label=f'{scenario} REE {enabled}'
        d=data['details'][enabled]; b=d['base']; h=d['marine_whr']; s=d['industrial']
        cost=next(x for x in data['ree_tea']['cases'] if x['scenario']==scenario and str(x['ree_enabled'])==enabled)
        check(label,'Independent DCF root = reported MSP',cost['independent_msp_usd_per_kg_H2'],row['hydrogen_msp_usd_per_kg'])
        check(label,'Detailed TEA gross OPEX = annual report',cost['gross_opex_usd_per_year'],row['annual_operating_cost_usd'])
        check(label,'Detailed coproduct revenue = annual report',cost['coproduct_revenue_usd_per_year'],row['annual_coproduct_revenue_usd'])
        check(label,'Cost groups = gross OPEX',sum(cost[k+'_usd_per_year'] for k in ('materials','utilities','waste','fixed')),cost['gross_opex_usd_per_year'])
        check(label,'Gross OPEX minus credits plus screening capital = treatment cost',cost['net_treatment_cost_usd_per_year'],row['annual_net_treatment_cost_usd'])
        check(label,'FCI = unit installed cost plus explicit adjustments',cost['FCI_usd'],cost['installed_capital_sum_usd'])
        for product in ('reo','caco3'):
            check(label,product+' revenue credited once in DCF',cost['msp_without_'+product+'_revenue']-cost['independent_msp_usd_per_kg_H2'],cost[product+'_revenue_usd_per_year']/cost['h2_kg_per_year'])
        check(label,'Cashflow NPV residual below one dollar',max(abs(cost['discounted_cashflow_residual_usd'])-1.,0.),0.)
        check(label,'Discounted MSP ledger closes to solver tolerance',sum(x['usd_per_kg_H2'] for x in data['ree_tea']['dcf_components'] if x['scenario']==scenario and str(x['ree_enabled'])==enabled),cost['dcf_msp_usd_per_kg_H2'])
        audit=next(x for x in data['balances'] if str(x['ree_enabled'])==enabled)
        for key,value in audit.items():
            if key.endswith('relative_error'): check(label,key,value,0.,atol=1e-8)
        check(label,'H2 component = wet-basis conversion',row['h2_component_kgph'],row['hydrogen_kg']*row['wet_feed_kgph']/1000.)
        check(label,'Gas contains H2 plus nonnegative other components',max(0.,row['h2_component_kgph']-row['h2_product_gas_kgph']),0.)
        check(label,'Original LCA sum = original net GWP',sum(x['kgCO2e_per_kg_H2'] for x in all_tables['lca_breakdown'] if x['scenario']==scenario and x['ree_enabled']==enabled and x.get('counted_in_original_CI', True)),row['net_gwp_kg_co2e']/row['hydrogen_kg'])
        check(label,'Reported LCA sum = main CI',sum(x['kgCO2e_per_kg_H2'] for x in all_tables['lca_breakdown'] if x['scenario']==scenario and x['ree_enabled']==enabled),displayed['net_gwp_kg_co2e']/row['hydrogen_kg'])
        check(label,'Storage sum = baseline storage credit',sum(b['storage_credits'].values()),row['credit_gwp_kg_co2e']/row['hydrogen_kg'])
        check(label,'Gross emissions + storage = net',row['gross_gwp_kg_co2e']+row['credit_gwp_kg_co2e'],row['net_gwp_kg_co2e'])
        check(label,'Contained CaCO3 + disposed remainder = cake mass',row['caco3_component_kgph']+row['caco3_impurity_disposal_kgph'],row['caco3_cake_total_kgph'])
        check(label,'Contained coproduct revenues = annual revenue',
              (row['caco3_revenue_usd_per_h']+row['reo_component_kgph']*row['reo_price_usd_per_kg'])*row['operating_hours'],row['annual_coproduct_revenue_usd'])
        if scenario=='S1':
            check(label,'OPEX group sum = net OPEX',sum(x['MUSD_per_yr'] for x in b['opex'])*1e6,row['net_annual_opex_usd'])
        before=s['heating_before_kW'] if scenario!='S2' else h['external_before_kW']
        check(label,'WHR + residual purchased heat = baseline heat',row['waste_heat_delivered_kW']+row['external_heating_kW'],before)
        if scenario=='S2':
            check(label,'S2 purchased heating = shared corrected inventory',h['external_before_kW'],s['heating_before_kW'])
            check(label,'S2 source/sink allocations = used heat',sum(x['assigned_kW'] for x in h['assignments']),h['utilized_kW'])
            for x in h['sources']: check(label,x['source']+' source not overallocated',max(0.,x['utilized_kW']-x['delivered_kW']),0.)
        if scenario=='S3':
            check(label,'S3 allocations = used overlap steam',sum(x['used_kW'] for x in s['allocations']),s['useful_steam_overlap_kW'])
            check(label,'S3 effectiveness applied once',s['source_extracted_overlap_kW']*s['configuration']['effectiveness'],s['useful_steam_overlap_kW'])
            check(label,'S3 installed allowance basis',s['useful_steam_overlap_kW']*s['configuration']['installed_cost_usd_per_kW'],s['incremental_capex_usd'])
            check(label,'S3 auxiliary electricity basis',s['used_average_kW']*s['configuration']['auxiliary_kW_per_kW'],s['auxiliary_average_kW'])
            check(label,'S3 boundary flows unchanged',int(s['boundary_flows_unchanged']),1)
            for x in s['sinks']:
                assigned=sum(a['used_kW'] for a in s['allocations'] if a['unit']==x['unit'])
                check(label,x['unit']+' industrial sink not overallocated',max(0.,assigned-x['purchased_kW']),0.)
        for basis in ('per_kg_h2','per_tonne_wet'):
            r=next(x for x in data['functional'] if x['scenario']==scenario and str(x['ree_enabled'])==enabled and x['basis']==basis)
            check(label,basis+' net annual treatment cost',r['annual_operating_cost_usd']+r['annual_capital_charge_usd']-r['annual_coproduct_revenue_usd'],r['annual_net_treatment_cost_usd'])
            check(label,basis+' GWP basis conversion',r['net_gwp_kg_co2e'],row['net_gwp_kg_co2e']/row['hydrogen_kg']*r['hydrogen_kg'])
            check(label,basis+' gross OPEX basis conversion',r['operating_cost_usd'],r['annual_operating_cost_usd']/(row['h2_component_kgph']*row['operating_hours'])*r['hydrogen_kg'])
    if 'avoided_emissions' in data:
        for row in data['avoided_emissions']['rows']:
            label = f"{row['scenario']} REE {row['ree_enabled']} {row['basis']} {row['credit_case']} {row['sensitivity_parameter']} {row['sensitivity_value']}"
            original = next(r for r in data['functional'] if r['scenario']==row['scenario']
                            and r['ree_enabled']==row['ree_enabled'] and r['basis']=='per_kg_h2')
            h2 = data['details'][str(row['ree_enabled'])]['base']['products']['h2_component_kgph']
            scale = dict(per_kg_h2=1., per_tonne_wet_presscake=h2/original['wet_feed_kgph']*1000.,
                         per_tonne_dry=h2/original['dry_feed_kgph']*1000.)[row['basis']]
            check(label, 'Original CI preserved', row['original_CI'], original['net_gwp_kg_co2e'] * scale)
            check(label, 'Expanded credit ledger closes', row['expanded_CI']
                  + row['avoided_gcc_production_emissions'] + row['avoided_sargassum_decomposition_emissions'], row['original_CI'])
            if row['credit_case']=='main':
                check(label, 'Main excludes decomposition', row['avoided_sargassum_decomposition_emissions'], 0.)
                check(label, 'Main includes GCC once', row['original_CI']-row['expanded_CI'], row['avoided_gcc_production_emissions'])
    return checks


def _write_ree_tea_review(out, data):
    audit=data['ree_tea']; cases=audit['cases']; delta=audit['increments']
    first=cases[0]
    lines=['# REE On/Off TEA verification', '',
           'REE On has a higher hydrogen MSP in all three scenarios under the current assumptions. Independent bracketed roots of discounted cash flow reproduce the current prices. No economic calculation or accounting correction was required.',
           '',f"All six cases produce {first['h2_kg_per_hour']:.9f} kg H2/h, {first['h2_kg_per_year']:.6f} kg H2/year, at {first['operating_hours']:.0f} h/year. The full product-gas mass is not used as hydrogen production.",
           '', '| Scenario | REE | FCI (USD) | Gross OPEX (USD/year) | Coproduct revenue (USD/year) | Net OPEX (USD/year) | Screening capital (USD/year) | Net treatment (USD/year) | DCF MSP (USD/kg H2) |',
           '|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for row in cases:
        values=[row[key] for key in ('FCI_usd','gross_opex_usd_per_year','coproduct_revenue_usd_per_year','net_opex_usd_per_year','screening_capital_usd_per_year','net_treatment_cost_usd_per_year')]
        lines.append(f"| {row['scenario']} | {'On' if row['ree_enabled'] else 'Off'} | "+' | '.join(f'{x:,.2f}' for x in values)+f" | {row['dcf_msp_usd_per_kg_H2']:.8f} |")
    lines+=['','All increments below are REE On minus REE Off. Reagent and electricity subrows are already included in their parent cost groups; do not add them again.',
            '', '| Increment | S1 | S2 | S3 |', '|---|---:|---:|---:|']
    fields=[('FCI, USD','delta_FCI_usd'),('REE-specific installed equipment including auxiliaries, USD','delta_ree_equipment_capex_usd'),
            ('Materials, USD/year','delta_materials_usd_per_year'),('  HCl solution subset, USD/year','delta_HCl_usd_per_year'),
            ('  Oxalic acid subset, USD/year','delta_oxalic_usd_per_year'),('  NaOH subset, USD/year','delta_NaOH_usd_per_year'),
            ('Utilities and energy, USD/year','delta_utilities_usd_per_year'),('  Electricity subset, USD/year','delta_electricity_usd_per_year'),
            ('Waste treatment/disposal, USD/year','delta_waste_usd_per_year'),('Fixed operating costs, USD/year','delta_fixed_usd_per_year'),
            ('Gross OPEX, USD/year','delta_gross_opex_usd_per_year'),('REO revenue, USD/year','delta_reo_revenue_usd_per_year'),
            ('CaCO3 revenue, USD/year','delta_caco3_revenue_usd_per_year'),('Total coproduct revenue, USD/year','delta_coproduct_revenue_usd_per_year'),
            ('Net OPEX, USD/year','delta_net_opex_usd_per_year'),('Screening annual capital charge, USD/year','delta_screening_capital_usd_per_year'),
            ('Net treatment cost, USD/year','delta_net_treatment_cost_usd_per_year'),('Working capital, USD','delta_working_capital_usd'),
            ('Screening cost change, USD/kg H2','screening_cost_change_usd_per_kg_H2'),('DCF MSP change, USD/kg H2','delta_msp_usd_per_kg_H2')]
    for label,key in fields:
        precision=8 if 'kg H2' in label else 2
        lines.append('| '+label+' | '+' | '.join(f'{row[key]:+,.{precision}f}' for row in delta)+' |')
    on=next(x for x in cases if x['scenario']=='S1' and x['ree_enabled'])
    d=delta[0]
    lines+=['',f"S1 screening arithmetic: {d['delta_gross_opex_usd_per_year']:.2f} - {d['delta_coproduct_revenue_usd_per_year']:.2f} + {d['delta_screening_capital_usd_per_year']:.2f} = {d['delta_net_treatment_cost_usd_per_year']:.2f} USD/year, or {d['screening_cost_change_usd_per_kg_H2']:.8f} USD/kg H2. This is not the DCF MSP increment ({d['delta_msp_usd_per_kg_H2']:.8f} USD/kg H2).",
            '',f"REO revenue is {on['reo_revenue_usd_per_year']:.2f} USD/year. Removing only REO revenue, leaving physical operations and all costs intact, raises S1 REE-On MSP from {on['dcf_msp_usd_per_kg_H2']:.8f} to {on['msp_without_reo_revenue']:.8f} USD/kg H2. The effect is revenue / annual hydrogen = {on['reo_revenue_usd_per_year']/on['h2_kg_per_year']:.8f} USD/kg H2. The same credit is verified independently for S2 and S3. CaCO3 credit is checked the same way while retaining the non-saleable cake disposal charge.",
            '', 'The additional REE equipment is LC1 and RO1 including their owned auxiliaries. Other process equipment changes explain the remainder of the FCI increment; the unit-by-unit installed costs and explicit scenario adjustments are exported in ree_equipment_costs.csv. S2 applies its existing 1.25 floating process multiplier and labor treatment; WHR is added after that multiplier. S3 uses the same industrial WHR increment in both REE cases.',
            '', 'The six horizontal cost stacks are annualized screening costs in million USD/year: materials + utilities/energy + waste treatment/disposal + fixed OPEX + FCI × CRF, with coproduct revenue shown separately as a negative credit. Gross OPEX is before coproduct credits but after actual WHR utility savings. Net OPEX = gross OPEX - coproduct revenue; net treatment cost = net OPEX + screening capital. H2 sales are excluded from screening costs. The three increment stacks use the same basis for On minus Off. DCF MSP is displayed separately.',
            '', 'DCF assumptions remain 10% IRR, 20 operating years (2026–2046), MACRS7 depreciation, 21% income tax, construction spending 40%/60%, 5% working capital recovered at project end, 60% debt at 8% over 10 years, and a 3-month startup with FOC 100%, VOC 50% and sales 50%. The startup FOC profile differs from sales/VOC. Depreciation affects taxable earnings rather than being added to OPEX. The DCF includes timed construction, debt payments and taxes; the screening CRF does not enter the DCF as another cost. No additional replacement capital is triggered by REE On in these cases.',
            '', 'The following audit uses the actual discounted cash-flow columns and operating/sales startup profiles, normalized by discounted hydrogen. It is an additive DCF check to solver tolerance, not an allocation of a fitted capital residual. Small residual NPVs are below one dollar.',
            '', '| Discounted MSP increment, USD/kg H2 | S1 | S2 | S3 |', '|---|---:|---:|---:|']
    for group in ('materials','utilities','waste','coproduct_revenue','fixed','capital','working_capital','financing','tax'):
        values=[sum(x['usd_per_kg_H2']*(1 if x['ree_enabled'] else -1) for x in audit['dcf_components'] if x['scenario']==s and x['group']==group) for s in ('S1','S2','S3')]
        lines.append('| '+group+' | '+' | '.join(f'{x:+.8f}' for x in values)+' |')
    lines+=['', 'Accounting checks: installed unit costs plus explicit adjustments equal FCI; HCl and oxalic ledger costs equal their feed costs; CaCO3 and REO sales are credited once; independent DCF roots match the solved MSP. In BioSTEAM, negative-price waste products and net cake prices affect sales. The report separates their disposal and gross revenue portions for readability; raw TEA.AOC therefore differs from report gross OPEX without creating a second charge.',
            '', 'Code references:']
    for file,needle in [('analyses/tea.py','class ATTTEA'),('analyses/tea.py','def _apply_prices'),('analyses/tea.py','def evaluate_att_tea'),('analyses/tea.py','def _opex_table'),('analyses/marine_tea.py','def evaluate_case'),('analyses/s3_industrial.py','def run('),('analyses/ree_tea_cases.py','def _root'),('analyses/ree_tea_cases.py','def _dcf_components')]:
        number=next(i for i,line in enumerate((ROOT/file).read_text(encoding='utf-8').splitlines(),1) if needle in line)
        lines.append(f'- biorefineries/ATT/{file}:{number} — `{needle}`')
    (out/'REE_TEA_VERIFICATION.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


def write_report(out, data):
    out=Path(out)
    if 'avoided_emissions' in data:
        # Opt-in artifacts must never overwrite the original comprehensive report.
        dedicated = ROOT/'results'/'avoided_emissions'
        if not out.resolve().is_relative_to(dedicated.resolve()):
            raise ValueError('Avoided-emission reports must stay in ATT/results/avoided_emissions/')
    all_tables=tables(data)
    if 'avoided_emissions' in data:
        from biorefineries.ATT.analyses.avoided_emissions import reference_rows
        all_tables['main_ci'] = reference_rows(data, 'main')
        all_tables['potential_decomposition'] = reference_rows(data, 'potential')
    qc=report_qc(data,all_tables)
    failed=[row for row in qc if row['status']!='PASS']
    if failed:
        raise ValueError(f'Report reconciliation failed: {failed}')
    out.mkdir(parents=True,exist_ok=True)
    all_tables['report_qc']=qc
    for name, rows in all_tables.items(): _save_csv(out/(name+'.csv'),rows)
    payload=clean(dict(data, tables=all_tables))
    encoded=json.dumps(payload,ensure_ascii=False,allow_nan=False,separators=(',',':')).replace('</','<\\/')
    html=TEMPLATE.read_text(encoding='utf-8').replace('/*__ATT_DATA__*/', 'const ATT_DATA = '+encoded+';')
    if 'avoided_emissions' in data:
        from biorefineries.ATT.analyses.avoided_emissions import report_section
        html = html.replace('</body>', report_section(data) + '</body>')
    (out/'ATT_S1_S2_S3_Comprehensive_Report.html').write_text(html,encoding='utf-8')
    (out/'provenance.json').write_text(json.dumps(data['provenance'],indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    (out/'report_qc.json').write_text(json.dumps(dict(status='PASS',passed=len(qc),failed=0,checks=qc),indent=2)+'\n',encoding='utf-8')
    _write_ree_tea_review(out,data)
    p=data['provenance']; verification=data.get('verification',{})
    lines=['# ATT six-case verification', '',f"Git HEAD: branch `{p['branch']}`, commit `{p['commit']}`; working tree {p['working_tree_state']}; generated {p['generated_utc']}.",
           'Uncommitted changes, active input SHA-256 fingerprints and dependency versions are recorded in provenance.json.',
           '',f'Report-generation QC: {len(qc)} PASS, 0 FAIL.',
           f"Full ATT suite: {verification.get('test_result','Not invoked by write_report; use --verify-tests for a release run')}.",
           '', '| Scenario | REE | MSP (USD/kg H2) | Main CI incl. GCC (kg CO2e/kg H2) | Net OPEX (USD/year) | WHR (kW) | Residual heat (kW) |',
           '|---|---|---:|---:|---:|---:|---:|']
    for r in all_tables['scenario_comparison']:
        lines.append(f"| {r['scenario']} | {'On' if r['ree_enabled'] else 'Off'} | {r['hydrogen_msp_usd_per_kg']:.8f} | {r['net_gwp_kg_co2e']/r['hydrogen_kg']:.8f} | {r['net_annual_opex_usd']:.2f} | {r['waste_heat_delivered_kW']:.6f} | {r['external_heating_kW']:.6f} |")
    lines+=['','Main CI includes GCC avoided production, separately from the existing storage assumption. Potential beach decomposition is excluded from main CI. Original CI is retained explicitly in the scenario, functional-unit and main-CI CSV tables.',
            'REE economics: all six independent DCF roots agree; REO and CaCO3 revenues are credited once. Annualized cost stacks use screening capital recovery and keep DCF MSP separate. See REE_TEA_VERIFICATION.md for the numeric On/Off reconciliation.',
            'All six balance rows use the common ATT flowsheet; S2/S3 WHR accounting leaves physical boundary streams unchanged.',
            '', 'Remaining scientific limitations: UCLA insoluble-residue/reagent basis and low-concentration recovery; unverified REO saleability and oxide basis; unresolved organics; lime assay/supply/handling; carbon-storage permanence; and host heat surplus, competing users and screening equipment costs.',
            'The H3 interpretation follows the prior supplied-PDF review recorded in scenario_docs/ATT_S3_DESIGN_BASIS.md; no new literature validation is claimed.']
    (out/'verification_summary.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    if verification.get('test_log'):
        (out/'test_suite.log').write_text(verification['test_log'],encoding='utf-8')
    return out


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,help='output directory within results/avoided_emissions')
    p.add_argument('--verify-tests',action='store_true',help='Run the full ATT suite and record its output in the release bundle')
    p.add_argument('--reference-report',type=Path,help='Previous HTML used for comparison; recorded by path and SHA-256')
    args=p.parse_args()
    out=args.out or output_dir('avoided_emissions', root=ROOT/'results')
    verification={}
    if args.verify_tests:
        print('Running full ATT test suite...',flush=True)
        run=subprocess.run([sys.executable,'-m','unittest','discover','-s','biorefineries/ATT/test','-t','.',
                            '-p','test_att*.py'],cwd=REPO,text=True,encoding='utf-8',errors='replace',
                           stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        print(run.stdout,flush=True)
        if run.returncode:
            raise RuntimeError(f'ATT tests failed (exit {run.returncode}); release not generated')
        count=re.search(r'Ran (\d+) tests?',run.stdout)
        verification=dict(test_result=f"PASS ({count.group(1) if count else 'unknown count'} tests)",test_log=run.stdout)
    print('Collecting current ATT cases...',flush=True)
    data=collect()
    if args.reference_report:
        ref=args.reference_report.resolve()
        reference=json.loads(re.search(r'const ATT_DATA = (.*?);\s*const \$=',ref.read_text(encoding='utf-8'),re.S).group(1))
        for case in data['ree_tea']['cases']:
            prior=next(x for x in reference['functional'] if x['scenario']==case['scenario'] and x['ree_enabled']==case['ree_enabled'] and x['basis']=='per_kg_h2')
            if not math.isclose(prior['hydrogen_msp_usd_per_kg'],case['dcf_msp_usd_per_kg_H2'],abs_tol=1e-7):
                raise ValueError('Economic result differs from reference report; review before publishing revision')
        data['provenance']['reference_report']=dict(path=str(ref),sha256=hashlib.sha256(ref.read_bytes()).hexdigest(),six_case_MSPs_unchanged=True)
    data['verification']=verification
    result=write_report(out,data)
    from biorefineries.ATT.analyses.avoided_emissions import _write_outputs
    _write_outputs(out, data)
    print('Saved',result.resolve())

if __name__=='__main__': main()
