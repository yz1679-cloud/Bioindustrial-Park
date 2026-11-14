"""Read-only reference extraction and controlled scratch-model sensitivities.

Run with the repository virtualenv, from any directory. Does not run or write
the comprehensive report. All output is confined to this script's directory.
"""
import os
from pathlib import Path
import sys
import hashlib
import json

OUT = Path(__file__).resolve().parent
ATT = OUT.parents[1]
REPO = ATT.parents[1]
sys.path.insert(0, str(REPO))
os.environ.setdefault('MPLCONFIGDIR', str(ATT/'outputs/runtime_cache/matplotlib'))
os.environ.setdefault('NUMBA_CACHE_DIR', str(ATT/'outputs/runtime_cache/numba'))
REFERENCE = ATT/'outputs/comprehensive_report_20261107_provenance'


def reference():
    html = (REFERENCE/'ATT_S1_S2_S3_Comprehensive_Report.html').read_text(encoding='utf8')
    return json.JSONDecoder().raw_decode(html.split('const ATT_DATA = ', 1)[1])[0]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect():
    import numpy as np
    from biorefineries.ATT.analyses import scenarios, tea, inventory, lca
    from biorefineries.ATT.analyses.breakdown import build_att_breakdown
    from biorefineries.ATT.analyses.att_s3_industrial import run as s3_run
    from biorefineries.ATT.analyses.att_comprehensive_report import carbon_credit_breakdown

    ref = reference()
    protected = {REPO/k: v for k, v in ref['provenance']['input_sha256'].items()}
    protected[REFERENCE/'ATT_S1_S2_S3_Comprehensive_Report.html'] = sha(REFERENCE/'ATT_S1_S2_S3_Comprehensive_Report.html')
    mismatches = [str(p) for p, value in protected.items() if sha(p) != value]
    if mismatches:
        raise ValueError('Reference source discrepancy: '+repr(mismatches))
    stages = {}
    for enabled, stage in [(False, 'P1'), (True, 'P2')]:
        system = scenarios.create(scenarios.ATT_S1, ree_recovery=enabled)
        summary = build_att_breakdown('att_s1', sys=system)['summary']
        streams = inventory._streams(system)
        stages[stage] = dict(msp=summary['MSP_USD_per_kg_H2'], gwp=summary['GWP_kgCO2e_per_kg_H2'])
        print(stage, stages[stage], flush=True)
        if enabled:
            continue
        prices_before = {s.ID: float(s.price) for s in (*system.feeds, *system.products)}
        baseline = tea.evaluate_att_tea(system)
        cake_ids = tuple(baseline['caco3_sales'])
        try:
            # All cakes use the existing -0.04 USD/kg disposal price when sales
            # are disabled. ATT char alone receives a temporary price override.
            result = tea.evaluate_att_tea(system, caco3_sales=None,
                price_overrides={**scenarios.tea_config()['price_overrides'], 'att_char': -0.04})
            for ID in cake_ids:
                if not np.isclose(streams[ID].price, -0.04):
                    raise ValueError('Full cake disposal not enabled: '+ID)
            lca.apply_att_gwp(system, overrides=scenarios.lca_overrides())
            h2 = float(streams['h2_product'].imass['H2'])
            gwp = system.get_net_impact(lca.KEY)/system.operating_hours/h2
            stages['P0'] = dict(msp=result['msp'], gwp=gwp,
                cake_disposal_kgph=sum(float(streams[ID].F_mass) for ID in cake_ids),
                cake_disposal_usd_per_year=sum(float(streams[ID].F_mass)*0.04*system.operating_hours for ID in cake_ids),
                char_disposal_kgph=float(streams['att_char'].F_mass),
                char_disposal_usd_per_year=float(streams['att_char'].F_mass)*0.04*system.operating_hours,
                untracked_price=float(streams['att_residue_untracked'].price),
                full_cake_prices={ID:float(streams[ID].price) for ID in cake_ids},
                char_price=float(streams['att_char'].price),
                delta_msp_from_P1=result['msp']-stages['P1']['msp'])
            print('P0', stages['P0'], flush=True)
        finally:
            tea.evaluate_att_tea(system)
            for st in (*system.feeds, *system.products):
                st.price = prices_before[st.ID]

    industrial = s3_run(enable_ree_recovery=True)
    stages['P3'] = dict(msp=industrial['s3_MSP_usd_per_kg_H2'], gwp=industrial['s3_GWP_kg_per_kg_H2'])
    # A new S3 boundary instance provides stream prices and physical activities.
    system = scenarios.create(scenarios.ATT_S1, ree_recovery=True)
    result = tea.evaluate_att_tea(system, extra_capital=[('Industrial WHR',industrial['incremental_capex_usd'],'existing S3')],
        extra_voc=[('Industrial WHR: avoided heat',-industrial['avoided_cost_usd_per_year']),
                   ('Industrial WHR: auxiliary electricity',industrial['auxiliary_electricity_cost_usd_per_year']),
                   ('Industrial WHR: heat purchase',industrial['heat_purchase_cost_usd_per_year'])])
    lca.apply_att_gwp(system, overrides=scenarios.lca_overrides())
    boundary = []
    for st in (*system.feeds, *system.products):
        boundary.append(dict(stream=st.ID, direction='input' if st in system.feeds else 'output',
            kgph=float(st.F_mass), price=float(st.price), CF=float(st.get_CF(lca.KEY)),
            components={ID:float(v) for ID,v in zip(st.chemicals.IDs,st.mass) if v},
            atomic_C_kmolph=float(st.get_atomic_flow('C'))))
    storage_by_stream = {}
    streams = inventory._streams(system)
    for ID in lca._LCA['waste_management']['landfill_streams']:
        st = streams[ID]
        lime_ID = lca._LIME_OF_CAKE.get(ID)
        lime_C = float(streams[lime_ID].get_atomic_flow('C')) if lime_ID else 0.
        soluble = float(st.imol['Na2CO3'])
        storage_by_stream[ID] = -(float(st.get_atomic_flow('C'))-lime_C-soluble)*44.0095
    activities = dict(h2so4_kgph=lca._h2so4_kgph(system), wastewater_m3ph=lca._wastewater_m3ph(system),
        landfill_kgph=lca._landfill_kgph(system), storage_kgCO2ph=storage_by_stream,
        factors=lca._factors(scenarios.lca_overrides()), power_price=float(__import__('biosteam').PowerUtility.price),
        heating_cost_usdph={agent:sum(hu.cost for hu in system.heat_utilities if hu.agent.ID==agent)
                           for agent in ['natural_gas','low_pressure_steam','cooling_water']},
        power_kW=float(system.power_utility.rate))
    refs = ref['tables']['scenario_comparison']
    for stage, scenario, enabled in [('P1','S1',False),('P2','S1',True),('P3','S3',True)]:
        r = next(r for r in refs if r['scenario']==scenario and r['ree_enabled']==enabled)
        for name, target in [('msp',r['hydrogen_msp_usd_per_kg']),('gwp',r['net_gwp_kg_co2e']/r['hydrogen_kg'])]:
            if not np.isclose(stages[stage][name],target,rtol=1e-7,atol=1e-7):
                raise ValueError(f'{stage} {name}: {stages[stage][name]} differs from {target}')
    assert np.isclose(stages['P0']['gwp'],stages['P1']['gwp'],rtol=1e-10)
    changed = [str(p) for p,v in protected.items() if sha(p)!=v]
    assert not changed, changed
    data = dict(stages=stages, industrial=industrial, boundary=boundary, activities=activities,
        provenance=dict(reference=str(REFERENCE),reference_html_sha256=sha(REFERENCE/'ATT_S1_S2_S3_Comprehensive_Report.html'),
            input_sha256=ref['provenance']['input_sha256'], all_reference_sources_match=True,
            protected_files_unchanged=True))
    (OUT/'controlled_results.json').write_text(json.dumps(data,indent=2,default=float),encoding='utf8')
    print('Verified scratch calculations and protected hashes.',flush=True)


if __name__=='__main__':
    collect()
