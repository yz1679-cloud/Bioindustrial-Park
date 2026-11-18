"""Isolated dry-ash sensitivity; never rewrites baseline YAML or standard exports.

Run with the project's Python environment::

    python -m biorefineries.ATT.analyses.ash_content_sensitivity

Each ash/REE configuration uses a fresh interpreter. S2 and S3 use the
existing accounting routines on that configuration's simulated S1 process.
Only files named ``ash_content_sensitivity*`` under ATT/results are written.
"""
import argparse
from collections import defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / 'results'
PREFIX = 'ash_content_sensitivity'
BASELINE_ASH = .3207
UCLA_ASH = .167


def dry_composition(ash_fraction):
    """Preserve organic component ratios; set the total dry mineral fraction."""
    from biorefineries.ATT.utils import load_assumptions
    if not math.isfinite(ash_fraction) or not 0 <= ash_fraction < 1:
        raise ValueError('Ash must be a dry mass fraction in [0, 1)')
    att = load_assumptions('att.yaml')['att']
    key = att['feed_preparation']['presscake_feedstock_type']
    base = load_assumptions('feedstock.yaml')['feedstock_type'][key]['dry_composition']
    organic = sum(v for k, v in base.items() if k != 'Ash')
    return {k: ash_fraction if k == 'Ash' else v * (1-ash_fraction) / organic
            for k, v in base.items()}


def run_case(ash_fraction, ree_enabled=True):
    """Return a JSON-compatible result from a fresh, isolated Python process.

    Worker diagnostics are saved separately from baseline exports. Failure
    raises with the original traceback; callers must not treat it as a run.
    """
    runtime = RESULTS / f'{PREFIX}_runtime'
    runtime.mkdir(parents=True, exist_ok=True)
    # Short cache paths avoid Numba's >260-character temporary names on Windows.
    env = dict(os.environ, MPLCONFIGDIR=str(RESULTS / '.mpl'),
               NUMBA_CACHE_DIR=str(RESULTS / '.nb'), PYTHONDONTWRITEBYTECODE='1',
               PYTHONIOENCODING='utf-8')
    cmd = [sys.executable, '-m', 'biorefineries.ATT.analyses.ash_content_sensitivity',
           '--worker', '--ash', str(ash_fraction)]
    if not ree_enabled:
        cmd.append('--no-ree')
    completed = subprocess.run(cmd, cwd=ROOT, env=env, text=True, encoding='utf-8',
                               errors='replace', capture_output=True, timeout=600)
    name = f'ash_{ash_fraction:g}_ree_{"on" if ree_enabled else "off"}.log'
    (runtime / name).write_text(completed.stdout + '\n' + completed.stderr, encoding='utf-8')
    marker = 'ATT_ASH_RESULT='
    lines = [s[len(marker):] for s in completed.stdout.splitlines() if s.startswith(marker)]
    if completed.returncode or not lines:
        raise RuntimeError(f'Case ash={ash_fraction:g}, REE={ree_enabled} failed:\n{completed.stderr[-10000:]}')
    return json.loads(lines[-1])


def _atoms(streams):
    totals = defaultdict(float)
    for stream in streams:
        for chemical in stream.chemicals:
            amount = float(stream.imol[chemical.ID])
            for element, n in chemical.atoms.items():
                totals[element] += amount * n
    return totals


def _balances(system):
    """Independent sums at every unit and the external process boundary."""
    rows = []
    groups = [(u.ID, u.ins[:1] if u.ID == 'U2' else u.ins, u.outs) for u in system.units]
    groups.append(('OVERALL', system.feeds, system.products))
    for name, ins, outs in groups:
        a, b = sum(float(s.F_mass) for s in ins), sum(float(s.F_mass) for s in outs)
        rows.append(dict(unit=name, quantity='mass_kgph', inlet=a, outlet=b,
                         relative_error=(b-a)/max(1., abs(a))))
        left, right = _atoms(ins), _atoms(outs)
        for element in sorted(set(left) | set(right)):
            a, b = left[element], right[element]
            rows.append(dict(unit=name, quantity=f'{element}_kmol_atoms_ph', inlet=a, outlet=b,
                             relative_error=(b-a)/max(1., abs(a))))
    return rows


def _energy(system):
    net = defaultdict(float)
    for hu in system.heat_utilities:
        if hu.agent:
            net[hu.agent.ID] += float(hu.duty)/3600
    before = defaultdict(float)
    for u in system.units:
        if u.ID == 'HXN':
            continue
        for hu in u.heat_utilities:
            if hu.agent:
                before[hu.agent.ID] += float(hu.duty)/3600
    heating = sum(max(0., q) for q in net.values())
    gross = sum(max(0., q) for q in before.values())
    return dict(heating_before_HXN_kW=gross, external_heating_kW=heating,
                external_cooling_kW=-sum(min(0., q) for q in net.values()),
                internal_heat_recovery_utility_equivalent_kW=gross-heating,
                process_electricity_kW=float(system.power_utility.rate)), [
                    dict(agent=k, before_HXN_kW=before[k], external_kW=v) for k, v in net.items()]


def _economics(system, evaluated, scenario, labor=None):
    from biorefineries.ATT.analyses import tea, inventory as inv
    t = evaluated['tea']
    items = [r for r in tea._opex_table(system, evaluated) if r['category'] not in ('capital', 'total')]
    revenue = -sum(r['USD_per_yr'] for r in items if r['category'] in ('REE sales', 'CaCO3 sales'))
    # Includes disposal booked as negative sales by BioSTEAM. Coproduct
    # revenue is explicitly split out; H2 revenue is never deducted here.
    net = sum(r['USD_per_yr'] for r in items)
    gross = net + revenue
    utility = sum(r['USD_per_yr'] for r in items if r['category'] == 'utilities'
                  or (r['category'] == 'extra VOC' and
                      ('gas' in r['item'].lower() or 'WHR' in r['item'] or 'Electricity' in r['item'])))
    chemicals = sum(r['USD_per_yr'] for r in items if
                    (r['category'] == 'materials' and not r['item'].startswith(('Process water', 'Sargassum')))
                    or r['item'].startswith('Purge neutralization'))
    h2 = float(inv._streams(system)['h2_product'].imass['H2']) * system.operating_hours
    wet = float(inv._streams(system)['att_sargassum_feed'].F_mass) * system.operating_hours/1000
    # Land-based labor is not separately estimated. Report the same assumed
    # share used by marine_tea.s1_reference, explicitly labeled in the report.
    if labor is None:
        from biorefineries.ATT.analyses import marine_tea
        labor = marine_tea.load_tea_config()['s1_labor_share_of_foc'] * t.FOC
    row = dict(scenario=scenario, FCI_USD=float(t.FCI), TCI_USD=float(t.TCI),
               gross_OPEX_USD_per_year=gross, net_OPEX_USD_per_year=net,
               chemical_cost_USD_per_year=chemicals, utility_cost_USD_per_year=utility,
               labor_USD_per_year=float(labor), other_fixed_USD_per_year=float(t.FOC-labor),
               coproduct_revenue_USD_per_year=revenue,
               net_treatment_USD_per_t_wet=net/wet, net_treatment_USD_per_kg_H2=net/h2,
               MSP_USD_per_kg_H2=float(evaluated['msp']))
    return row, [dict(scenario=scenario, **r) for r in items]


def _check_physics(balances, drift, checks, hxn_audit, sanity):
    """Withhold economics when independent physical feasibility checks fail."""
    issues = [f'{r["unit"]} {r["quantity"]}: relative residual {r["relative_error"]:.6g}'
              for r in balances if not math.isfinite(r['relative_error']) or abs(r['relative_error']) > 1e-8]
    if not math.isfinite(drift) or drift >= 1e-6:
        issues.append(f'Steady-state species change {drift:.6g}')
    issues.extend(f'{r["check"]}: {r["value"]}' for r in checks if str(r['status']).startswith('FAIL'))
    issues.extend(f'Stream {r["stream"]}: {r["status"]}' for r in sanity if r['status'] != 'OK')
    for key in ('max_lifecycle_error_kW', 'max_exchanger_error_kW'):
        if not math.isfinite(hxn_audit[key]) or hxn_audit[key] > 1e-5:
            issues.append(f'HXN {key}: {hxn_audit[key]}')
    if issues:
        raise RuntimeError('Physical validation failed; TEA/LCA withheld. '+ '; '.join(issues))


def _treatment_costs(row, process):
    """Use the existing treatment_report convention, including FCI annuity.

    This reporting-only conversion can also refresh a saved simulation's
    functional units without running or changing any process model.
    """
    from biorefineries.ATT.analyses.functional_unit import normalize_case
    from biorefineries.ATT.utils import load_assumptions
    financial = load_assumptions('tea.yaml')['financial']
    rate = float(financial['IRR'])
    years = financial['duration'][1]-financial['duration'][0]
    crf = rate/(1-(1+rate)**-years) if rate else 1/years
    h2_year = process['H2_kgph']*process['operating_hours']
    wet_year = process['wet_feed_kgph']*process['operating_hours']/1000
    normalized = normalize_case(wet_kgph=process['wet_feed_kgph'], dry_kgph=process['dry_feed_kgph'],
        h2_kgph=process['H2_kgph'], hours=process['operating_hours'], flows_kgph={},
        operating_cost_usd_year=row['gross_OPEX_USD_per_year'],
        coproduct_revenue_usd_year=row['coproduct_revenue_USD_per_year'],
        capital_charge_usd_year=row['FCI_USD']*crf,
        gross_gwp_per_kg_h2=row['gross_GWP_before_storage_kgCO2e_per_year']/h2_year,
        credit_gwp_per_kg_h2=row['storage_credit_kgCO2e_per_year']/h2_year,
        msp_per_kg_h2=row['MSP_USD_per_kg_H2'])
    row.update(annual_capital_charge_USD=normalized['annual']['capital_charge_usd'],
               annual_net_treatment_USD=normalized['annual']['net_treatment_cost_usd'],
               net_operating_USD_per_t_wet=row['net_OPEX_USD_per_year']/wet_year,
               net_operating_USD_per_kg_H2=row['net_OPEX_USD_per_year']/h2_year,
               net_treatment_USD_per_t_wet=normalized['per_tonne_wet']['net_treatment_cost_usd'],
               net_treatment_USD_per_kg_H2=normalized['per_kg_h2']['net_treatment_cost_usd'])


def _worker(ash, ree):
    import warnings
    import numpy as np
    import biosteam as bst
    import thermosteam as tmo
    from biorefineries.ATT.analyses import scenarios, inventory as inv, tea, lca
    from biorefineries.ATT.analyses import marine_tea, marine_whr, marine_lca, s3_industrial
    from biorefineries.ATT.utils import load_assumptions
    warnings.filterwarnings('default')
    composition = dry_composition(ash)
    # Baseline runs exercise the unmodified YAML path, so an accidental
    # baseline input change cannot be masked by the sensitivity override.
    system = scenarios.create(ree_recovery=ree,
                              feedstock_dry_composition=None if ash == BASELINE_ASH else composition)
    streams, units = inv._streams(system), inv._units(system)
    # Check species, not just aggregate tear masses (cancellation could hide
    # a composition drift). An extra full run includes every nested recycle.
    before = {k: np.array(s.mol, dtype=float).copy() for k, s in streams.items()}
    system.simulate()
    drift = max(float(np.max(abs(np.asarray(s.mol)-before[k])/np.maximum(1., abs(before[k]))))
                for k, s in streams.items())
    u2, feed, dried, product = units['U2'], streams['att_sargassum_feed'], units['D0'].outs[0], streams['h2_product']
    dry = inv._dry_feed_kgph(system)
    gas = u2.outs[0]
    m = dict(dry_feed_kgph=dry, DAF_kgph=u2._daf_sargassum_kgph,
             wet_feed_kgph=float(feed.F_mass), feed_moisture_fraction=float(feed.imass['Water'])/feed.F_mass,
             dried_feed_moisture_fraction=float(dried.imass['Water'])/dried.F_mass,
             ash_fraction_measured=sum(float(feed.imass[k]) for k in ('Ash', 'NaCl', 'KCl', 'REO'))/dry,
             operating_hours=float(system.operating_hours), gross_NaOH_kgph=float(u2.ins[0].imass['NaOH']),
             fresh_NaOH_kgph=float(streams['fresh_naoh_solid'].imass['NaOH']),
             recycled_NaOH_kgph=float(streams['naoh_recycle'].imass['NaOH']),
             CaOH2_kgph=sum(float(streams[k].imass['CaOH2']) for k in ('lime', 'scrubber_lime')),
             CaCO3_kgph=sum(float(s.imass['CaCO3']) for s in system.products),
             Na2CO3_formed_kgph=float(u2.outs[1].imass['Na2CO3']-u2.ins[0].imass['Na2CO3']),
             Na2CO3_dissolution_kgph=float(units['D1'].outs[0].imass['Na2CO3']),
             char_kgph=float(streams['att_char'].F_mass),
             char_dry_kgph=float(streams['att_char'].F_mass-streams['att_char'].imass['Water']),
             untracked_organics_kgph=float(streams['att_residue_untracked'].F_mass),
             salt_cake_kgph=float(streams['salt_cake'].F_mass), purge_kgph=float(streams['liquor_purge'].F_mass),
             compressed_product_gas_kgph=float(product.F_mass),
             H2_mol_fraction=float(product.imol['H2'])/product.F_mol,
             H2_mass_fraction=float(product.imass['H2'])/product.F_mass,
             raw_dry_gas_kgph=sum(float(gas.imass[k]) for k in ('H2', 'CH4', 'CO', 'CO2')),
             raw_wet_gas_kgph=float(gas.F_mass),
             U2_heating_kW=float(u2._heat_duty_kJph)/3600,
             U3K_power_kW=float(units['U3K'].power_utility.rate),
             recycle_max_relative_change=drift,
             residual_H_per_C=float(u2._residual_product_formula['H']),
             residual_O_per_C=float(u2._residual_product_formula['O']),
             H2_recovery_fraction=float(product.imass['H2'])/float(gas.imass['H2']))
    for ID in ('H2', 'CH4', 'CO', 'CO2'):
        m[f'{ID}_kgph'] = float(gas.imass[ID])
        m[f'{ID}_t_per_year'] = m[f'{ID}_kgph'] * system.operating_hours/1000
        m[f'{ID}_mmol_per_g_dry'] = u2.reported_gas_yield_mmol_per_g_daf[ID]*(1-ash)
        m[f'product_{ID}_mol_fraction'] = float(product.imol[ID])/product.F_mol
    for element in ('C', 'H', 'O', 'N'):
        m[f'organic_{element}_mol_per_kg_DAF'] = u2._organic_atoms_kmolph.get(element, 0.)*1000/m['DAF_kgph']
    m['fresh_water_kgph'] = sum(float(s.imass['Water']) for s in system.feeds if
                                     s.ID in ('dissolution_water', 'f1_wash_water', 'f2_wash_water',
                                              'scrubber_makeup_water', 'leach_water'))
    m['condensate_recycled_kgph'] = sum(float(streams[k].imass['Water']) for k in
        ('condensate_to_D1', 'condensate_to_wash', 'condensate_to_f1_wash', 'condensate_to_leach') if k in streams)
    m['REO_product_kgph'] = float(streams['ree_product'].imass['REO']) if ree else 0.
    m['REO_product_mass_fraction'] = (float(streams['ree_product'].imass['REO'])/streams['ree_product'].F_mass) if ree else 0.
    energy, utilities = _energy(system)
    m.update(energy)
    balances = _balances(system)
    checks = inv.get_att_process_checks(system)
    from biorefineries.ATT.analyses.industrial_whr import audit_hxn_enthalpy
    hxn = next(f for f in system.facilities if isinstance(f, bst.HeatExchangerNetwork))
    hxn_audit = audit_hxn_enthalpy(hxn)
    sanity = inv.get_att_stream_sanity_check(system)
    _check_physics(balances, drift, checks, hxn_audit, sanity)
    equipment, designs, stream_rows = [], [], []
    for u in system.units:
        equipment.append(dict(unit=u.ID, model=type(u).__name__,
                              inlet_kgph=sum(float(s.F_mass) for s in u.ins),
                              outlet_kgph=sum(float(s.F_mass) for s in u.outs),
                              heating_kW=sum(max(0., hu.duty) for hu in u.heat_utilities)/3600,
                              cooling_kW=-sum(min(0., hu.duty) for hu in u.heat_utilities)/3600,
                              electricity_kW=float(u.power_utility.rate), installed_cost_USD=float(u.installed_cost)))
        designed = [(u.ID, u), *[(f'{u.ID}.{name}', auxiliary) for name, auxiliary in
                                u.get_auxiliary_units_with_names()]]
        for label, modeled in designed:
            for key, value in modeled.design_results.items():
                if np.isscalar(value):
                    designs.append(dict(unit=label, parameter=key, value=value,
                                        units=modeled._units.get(key, '')))
    for ID, stream in streams.items():
        for chemical in stream.chemicals:
            flow = float(stream.imass[chemical.ID])
            if flow:
                stream_rows.append(dict(stream=ID, component=chemical.ID, kgph=flow,
                                        temperature_K=float(stream.T), pressure_Pa=float(stream.P)))
    evaluated = tea.evaluate_att_tea(system, **scenarios.tea_config())
    s1, opex = _economics(system, evaluated, 'S1')
    applied = lca.apply_att_gwp(system, overrides=scenarios.lca_overrides())
    contributions = lca.get_att_gwp_contributions(system, applied)
    gwp = float(system.get_net_impact(lca.KEY))/(m['H2_kgph']*system.operating_hours)
    stage = defaultdict(float)
    for r in contributions[:-1]:
        stage[r['stage']] += r['GWP_kgCO2e_per_kg_H2']
    storage = lca.get_att_stored_carbon_credit(system)
    chemical_gwp = stage['Chemical supply']
    utility_gwp = sum(stage[k] for k in ('Onsite fuel combustion', 'Natural gas supply chain', 'Purchased electricity'))
    # Existing S2 computes marine CAPEX/labor and WHR. Reuse its own exact
    # TEA hooks to expose the gross/net cost identity and detailed OPEX.
    ref = marine_tea.s1_reference(system)
    _, hours, load = marine_tea.operating_mode()
    marine, whr = marine_tea.evaluate_case(system, ref, 'S2', hours=hours, load=load)
    cfg = marine_tea.load_tea_config()
    avoided = sum(a['assigned_kW']*a['usd_per_kWh'] for a in whr['assignments'])*hours
    extra_voc = [('Marine WHR: purchased heat displaced', -avoided),
                 ('Marine WHR: pump electricity', whr['pump_kW']*bst.PowerUtility.price*hours)]
    s2_tea = tea.evaluate_att_tea(system, **scenarios.tea_config(),
        fci_factor=cfg['capex_multiplier'], operating_hours=hours, extra_capital=whr['equipment'], extra_voc=extra_voc,
        foc_frac_of_fci=tea._FIN['foc_frac_of_fci']*(1-cfg['s1_labor_share_of_foc']),
        foc_fixed=marine['labor_OPEX_USD_per_yr'])
    s2, rows = _economics(system, s2_tea, 'S2', marine['labor_OPEX_USD_per_yr'])
    opex.extend(rows)
    if abs(s2['MSP_USD_per_kg_H2']-marine['MSP_USD_per_kg_H2']) > 1e-8:
        raise RuntimeError('Marine cost decomposition does not reproduce existing S2 MSP')
    s3 = s3_industrial.run(system=system, return_tea=True)
    s3row, rows = _economics(system, s3.pop('tea_result'), 'S3', s1['labor_USD_per_year'])
    opex.extend(rows)
    scenarios_out, scenario_impacts = [], []
    for row, impact, delta, heat, power, capex in (
        (s1, gwp, 0., 0., 0., 0.),
        (s2, marine['GWP_kgCO2e_per_kg_H2'], marine['GWP_WHR_change_kgCO2e_per_kg_H2'],
         whr['utilized_kW'], whr['pump_kW'], marine['WHR_CAPEX_USD']),
        (s3row, s3['s3_GWP_kg_per_kg_H2'], s3['GWP_change_kg_per_kg_H2'],
         s3['used_average_kW'], s3['auxiliary_average_kW'], s3['incremental_capex_usd'])):
        row.update(GWP_kgCO2e_per_kg_H2=impact, net_GWP_kgCO2e_per_year=impact*m['H2_kgph']*hours,
                   gross_GWP_before_storage_kgCO2e_per_year=(impact-storage)*m['H2_kgph']*hours,
                   GWP_kgCO2e_per_t_wet=impact*m['H2_kgph']/m['wet_feed_kgph']*1000,
                   GWP_kgCO2e_per_t_dry=impact*m['H2_kgph']/dry*1000,
                   chemical_GWP_kgCO2e_per_year=chemical_gwp*m['H2_kgph']*hours,
                   utility_GWP_kgCO2e_per_year=(utility_gwp+delta)*m['H2_kgph']*hours,
                   storage_credit_kgCO2e_per_year=storage*m['H2_kgph']*hours,
                   external_WHR_kW=heat, external_heating_after_WHR_kW=m['external_heating_kW']-heat,
                   electricity_with_WHR_kW=m['process_electricity_kW']+power, WHR_CAPEX_USD=capex)
        _treatment_costs(row, m)
        scenarios_out.append(row)
        for r in contributions[:-1]:
            scenario_impacts.append(dict(scenario=row['scenario'], item=r['item'], stage=r['stage'],
                kgCO2e_per_year=r['GWP_kgCO2e_per_kg_H2']*m['H2_kgph']*hours))
        scenario_impacts.append(dict(scenario=row['scenario'], item='External WHR net utility adjustment',
                                    stage='Utilities', kgCO2e_per_year=delta*m['H2_kgph']*hours))
    att = load_assumptions('att.yaml')['att']
    return dict(ash_fraction=ash, ree_enabled=ree, dry_composition=composition,
                gas_yields_mmol_per_g_daf=u2.reported_gas_yield_mmol_per_g_daf,
                fixed_assumptions=dict(temperature_K=u2.target_temperature_K,
                    gross_naoh_kg_per_kg_dry=scenarios.ATT_S1['naoh_kg_per_kg_dry'],
                    causticization_conversion=att['downstream']['causticization_conversion'],
                    recycle_fraction=att['downstream']['whole_liquor_recycle_fraction'],
                    char_yield=att['downstream']['char']['yield_g_per_g_dry_feed']),
                versions=dict(python=sys.version, biosteam=bst.__version__, thermosteam=tmo.__version__),
                process=m, scenarios=scenarios_out, balances=balances, process_checks=checks,
                hxn_audit=hxn_audit, equipment=equipment, designs=designs, streams=stream_rows,
                utilities=utilities, opex=opex, gwp_contributions=contributions, scenario_impacts=scenario_impacts,
                carbon_fate=inv.get_att_carbon_fate(system),
                water_balance=inv.get_att_water_balance(system),
                sodium_calcium=inv.get_att_sodium_calcium_ledger(system),
                stream_sanity=sanity,
                unit_energy=inv.get_att_unit_energy_balance(system))


def _hashes(paths):
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.is_file()}


def screening_case(ash):
    """Analytical gas-only calculation, independent of flowsheet feasibility."""
    daf = 5029.17*(1-ash)
    row = dict(ash_fraction=ash, dry_feed_kgph=5029.17, DAF_kgph=daf,
               status='Analytical screening only; not a BioSTEAM result')
    for gas, y, mw in (('H2', 54.15, 2.01588), ('CH4', .60, 16.04246), ('CO2', .77, 44.0095)):
        row[f'{gas}_mmol_per_g_dry'] = y*(1-ash)
        row[f'{gas}_kgph'] = daf*y/1000*mw
        row[f'{gas}_t_per_year'] = row[f'{gas}_kgph']*7920/1000
    return row


def _reproduction_rows(cases, repeated):
    rows = []
    for repeat in repeated:
        original = next((c for c in cases if c['ash_fraction'] == BASELINE_ASH and
                         c['ree_enabled'] == repeat['ree_enabled']), None)
        if original is None:
            continue
        pairs = [('process', original['process'], repeat['process'])]
        pairs.extend((a['scenario'], a, b) for a, b in zip(original['scenarios'], repeat['scenarios']))
        for label, a, b in pairs:
            for metric, before in a.items():
                if not isinstance(before, (float, int)):
                    continue
                error = (b[metric]-before)/max(1., abs(before))
                rows.append(dict(ree_enabled=repeat['ree_enabled'], scenario=label, metric=metric,
                                 before=before, after=b[metric], relative_error=error, tolerance=1e-5,
                                 status='PASS' if math.isfinite(error) and abs(error) <= 1e-5 else 'FAIL'))
    return rows


def _export(cases, repeated, provenance, failures):
    import pandas as pd
    for case in (*cases, *repeated):
        for row in case['scenarios']:
            _treatment_costs(row, case['process'])
    rows = []
    for case in cases:
        for scenario in case['scenarios']:
            rows.append(dict(ash_fraction=case['ash_fraction'], ree_enabled=case['ree_enabled'],
                             **case['process'], **scenario))
    frame = pd.DataFrame(rows)
    if not frame.empty:
        keys = ['scenario', 'ree_enabled']
        base = frame[frame.ash_fraction == BASELINE_ASH].set_index(keys)
        differences = {}
        for col in frame.select_dtypes(include='number').columns:
            if col == 'ash_fraction':
                continue
            reference = [base.loc[(r.scenario, r.ree_enabled), col]
                         if (r.scenario, r.ree_enabled) in base.index else float('nan') for r in frame.itertuples()]
            differences[f'{col}_baseline'] = reference
            differences[f'{col}_absolute_difference'] = frame[col]-reference
            differences[f'{col}_relative_difference_pct'] = 100*(frame[col]-reference)/pd.Series(reference).replace(0, float('nan'))
        frame = pd.concat([frame, pd.DataFrame(differences)], axis=1)
    frame.to_csv(RESULTS/f'{PREFIX}_summary.csv', index=False)
    for table in ('balances', 'process_checks', 'equipment', 'designs', 'streams', 'utilities', 'opex',
                  'gwp_contributions', 'scenario_impacts', 'carbon_fate', 'water_balance', 'sodium_calcium', 'stream_sanity', 'unit_energy'):
        records = [dict(ash_fraction=c['ash_fraction'], ree_enabled=c['ree_enabled'], **row)
                   for c in cases for row in c[table]]
        pd.DataFrame(records).to_csv(RESULTS/f'{PREFIX}_{table}.csv', index=False)
    reproduction = _reproduction_rows(cases, repeated)
    pd.DataFrame(reproduction).to_csv(RESULTS/f'{PREFIX}_reproducibility.csv', index=False)
    screening = [screening_case(ash) for ash in provenance.get('requested_ash_fractions', [BASELINE_ASH, UCLA_ASH])]
    pd.DataFrame(screening).to_csv(RESULTS/f'{PREFIX}_screening.csv', index=False)
    payload = dict(cases=cases, repeated=repeated, provenance=provenance, failures=failures, screening=screening)
    (RESULTS/f'{PREFIX}_data.json').write_text(json.dumps(payload, indent=2, default=float), encoding='utf-8')
    _report(frame, cases, reproduction, provenance, failures)
    _figures(frame, cases)


def _report(frame, cases, reproduction, provenance, failures):
    def table(columns, subset=None):
        df = frame if subset is None else subset
        # Avoid an optional tabulate dependency.
        selected = df[columns]
        head = '| ' + ' | '.join(columns) + ' |\n| ' + ' | '.join(['---']*len(columns)) + ' |\n'
        return head + '\n'.join('| '+' | '.join(f'{v:.6g}' if isinstance(v, float) else str(v) for v in row)+' |'
                                for row in selected.itertuples(index=False, name=None))
    out = ['# ATT dry ash content sensitivity',
        '## Scope and status',
        'Research-stage sensitivity using the existing process topology, thermodynamics, TEA and LCA. '
        'Baseline YAML and original UCLA reference data are unchanged. Values are model outputs, not experimentally validated plant performance.',
        '## Composition and fixed assumptions',
        'At fixed 5,029.17 kg/h dry presscake, Ash is replaced by organic matter in proportion to each original non-ash component. '
        'All fractions sum to one. Organic C/H/O/N ratios per kg DAF are preserved because component formulas and their relative masses are unchanged. '
        'This is a synthetic ash-only sensitivity, not a measured reconstruction of the UCLA feedstock. '
        'The 16.7% ash value is user supplied; the original experimental workbook is neither modified nor reinterpreted. '
        'The optional 17.2% historical reference is only included if explicitly requested on the command line.',
        'The insoluble/NaCl/KCl ash shares remain 0.3838/0.2377/0.3785; thus absolute mineral and salt inputs decrease. '
        'REE remains fixed per kg total dry feed and is carved from insoluble ash. '
        'Moisture is 76.3% at receipt and 50% after D0, operating time 7,920 h/y, reactor temperature 500 C, '
        'gross NaOH 1 kg/kg total dry feed, causticization 88%, whole-liquor recycle 95%, purge 5%. '
        'The H2/CH4/CO/CO2 yields remain 54.15/0.60/0/0.77 mmol/g DAF. '
        'Every ash/REE configuration runs in a fresh Python interpreter; no YAML patching or shared configuration mutation is used.',
        '## Where ash enters the model',
        '`data/feedstock.yaml` supplies the dry component fractions. `system.create_att_system` constructs the wet feed, '
        'then partitions Ash into insoluble minerals, NaCl and KCl and optionally carves out REO. '
        '`units/_att.ATTReactor._run` subtracts these inorganic species from its dry feed to obtain DAF, '
        'multiplies fixed gas yields by DAF, converts NaOH to carbonate and solves the residual organic surrogate. '
        'Its energy calculation retains the configured HHV per kg DAF. RS1 imposes the configured dry-feed char yield. '
        'Downstream dissolution, causticization, filtration, evaporation and salt separation use the resulting streams and converged recycles. '
        '`analyses/tea.py` and `analyses/lca.py` use the recalculated designs, streams and utilities; '
        '`marine_tea.py` and `s3_industrial.py` supply the existing scenario-specific accounting.',
        '## Gas production',
        'The independent screening factor is (1 - 0.167)/(1 - 0.3207) = 1.2262623. '
        'Raw dry gas excludes steam; raw wet gas includes reactor product water. Compressed product includes residual CH4/CO2 and any water. '
        'The flow called h2_product is a hydrogen-rich gas, not a pure-H2 separation product (PSA remains off).']
    if not frame.empty:
        process = frame[frame.scenario == 'S1']
        out += [table(['ash_fraction','ree_enabled','DAF_kgph','H2_mmol_per_g_dry','CH4_mmol_per_g_dry',
                       'H2_kgph','H2_t_per_year','CH4_kgph','CH4_t_per_year','CO2_kgph',
                       'raw_dry_gas_kgph','raw_wet_gas_kgph','compressed_product_gas_kgph','H2_mol_fraction'], process),
            table(['ash_fraction','ree_enabled','organic_C_mol_per_kg_DAF','organic_H_mol_per_kg_DAF',
                   'organic_O_mol_per_kg_DAF','organic_N_mol_per_kg_DAF'], process),
            'Gas recovery remains 100% for H2 in this no-PSA flowsheet; gas pressure target and compressor efficiency remain fixed. '
            'The dry product mole fractions are 98.8902% H2, 1.09574% CH4 and 0.014062% CO2 (CO is zero). '
            'Raw wet reactor gas can decrease despite higher dry gas production, because the H/O closure changes reactor product water. '
            'Consequently gas cooler and condenser loads need not follow the 22.63% dry-gas increase.',
            '## Chemical recycling and residue interactions',
            table(['ash_fraction','ree_enabled','fresh_NaOH_kgph','recycled_NaOH_kgph','CaOH2_kgph',
                   'Na2CO3_formed_kgph','Na2CO3_dissolution_kgph','CaCO3_kgph','salt_cake_kgph',
                   'char_dry_kgph','untracked_organics_kgph','purge_kgph','fresh_water_kgph'], process),
            'Na2CO3 generation is tied to fixed gross NaOH conversion, not proportional to DAF. '
            'Scrubber lime follows gas CO2; C1 lime follows the converged carbonate liquor. '
            'Filtration entrainment, washing, salt removal and the REE leach return interact with NaOH makeup and purge. '
            'All liquor, purge, salt, condensate, ash and product compositions are in the component-level streams CSV. '
            'The sodium/calcium ledger, water balance and carbon-fate CSVs give independent accounting views.',
            'Fresh-water makeup excludes water arriving in the wet seaweed and chemical solutions/paste. '
            'Condensate reuse sums the water delivered to D1, F1/F2 washing and the REE leach, including the existing '
            'scrubber excess-water return to the condensate pool; detailed branch flows remain in the streams CSV.',
            'The existing RS1 assumption holds insoluble char at 15% of total dry feed, rather than at a constant fraction of DAF. '
            'Lower minerals therefore increase the organic share of this fixed solids yield. The remainder of the U2 balance surrogate '
            'leaves as untracked organics with no disposal cost or carbon credit. This is an experimentally unsupported carbon fate; '
            'it must not be interpreted as additional valuable coproduct. REE dosing, recovery and dilution assumptions are retained.',
            '## Equipment and energy',
            table(['ash_fraction','ree_enabled','FCI_USD','U2_heating_kW','U3K_power_kW',
                   'heating_before_HXN_kW','external_heating_kW','external_cooling_kW',
                   'process_electricity_kW','internal_heat_recovery_utility_equivalent_kW'], process),
            'Equipment CSVs compare each modeled unit, inlet/outlet rates, utilities and installed costs. '
            'The designs CSV lists all native design results and units, including parallel equipment counts when exposed by BioSTEAM. '
            'Auxiliary tank, filter and exchanger sizes use parent.auxiliary labels; their costs are already included in the parent and must not be added twice. '
            'A design-size change is a recalculated model capacity, not a procurement decision; equipment classes and process connections are unchanged. '
            'Fixed residence times, drying temperatures, pressure targets, filter cake moistures, conversion and separation efficiencies are retained. '
            'Some native correlations impose minimum sizes or discrete parallel counts, so costs need not vary continuously with flow. '
            'U2 furnace costing does not establish a qualified solids-reactor design; no vendor capacity or operability claim is made. '
            'D1 is a cost-free ideal mixer with no modeled dissolution vessel size or residence-time limit. '
            'The HXN cost is incremental relative to the original utility exchangers and is floored at zero; zero incremental cost does not mean no exchanger equipment. '
            'D0 water removal remains fixed, although feed heat capacity changes. Gas cooling, drying and compression respond to gas flow. '
            'D1/C1/EC1 and solids handling respond to recycle chemistry and composition. '
            'Internal recovery is reported as the reduction in external heating utility duty; it includes the existing utility efficiency conventions. '
            'Gross unit duties precede HXN cancellation; use the utilities CSV for net external loads. '
            'Per-unit energy residuals retain the existing model conventions and are exported without forcing closure.',
            '## Scenario TEA',
            table(['ash_fraction','ree_enabled','scenario','FCI_USD','gross_OPEX_USD_per_year',
                   'chemical_cost_USD_per_year','utility_cost_USD_per_year','labor_USD_per_year',
                   'other_fixed_USD_per_year','coproduct_revenue_USD_per_year',
                   'net_treatment_USD_per_t_wet','net_treatment_USD_per_kg_H2','MSP_USD_per_kg_H2']),
            'Gross OPEX includes materials, utilities, fixed costs and disposal; net OPEX subtracts coproduct revenue, excluding H2 sales. '
            'Net treatment cost follows treatment_report.py: gross OPEX plus FCI times the ordinary capital recovery factor, minus coproduct revenue, '
            'excluding H2 sales. Net operating cost is also exported separately. This screening capital charge excludes working capital, financing, '
            'tax and startup; MSP includes the existing discounted cash flow. '
            'S1/S3 labor is an illustrative allocation using the same S1 FOC share as marine accounting, not a separate staffing estimate. '
            'S2 preserves marine capital/labor multipliers and all enabled marine heat sources at configured underway hours/load. '
            'S3 uses the existing industrial steam-generation case with its default host capacity, hours, temperature constraints, '
            '90% heat-transfer effectiveness, $500/kW installed allowance and 1% auxiliary electricity. '
            'No proportional scaling of MSP or FCI is used.',
            'Equipment capital uses the configured 2020 USD CEPCI basis; feed, chemical and utility prices retain their existing mixed-year bases '
            'without escalation, as documented in tea.yaml.',
            '## Scenario LCA',
            table(['ash_fraction','ree_enabled','scenario','net_GWP_kgCO2e_per_year',
                   'GWP_kgCO2e_per_kg_H2','GWP_kgCO2e_per_t_wet','GWP_kgCO2e_per_t_dry',
                   'chemical_GWP_kgCO2e_per_year','utility_GWP_kgCO2e_per_year','storage_credit_kgCO2e_per_year']),
            'Net annual GWP includes modeled storage credits; gross_GWP_before_storage excludes only that credit. '
            'The separate avoided-beach-decay CH4 counterfactual remains outside net GWP. Waste lime retains zero supply burden and price. '
            'Utility emissions include scenario-specific heat displacement and pump power. '
            'The carbon-fate CSV distinguishes modeled stored carbon from soluble carbonate, product gases and unresolved organics.',
            '## Changes and rankings']
        on = process[process.ree_enabled]
        if set((BASELINE_ASH, UCLA_ASH)).issubset(set(on.ash_fraction)):
            a = on[on.ash_fraction == BASELINE_ASH].iloc[0]
            b = on[on.ash_fraction == UCLA_ASH].iloc[0]
            percent = lambda key: 100*(b[key]/a[key]-1)
            out += [f'For REE On, the direct 22.63% increase in DAF and dry gas contrasts with '
                    f'{percent("FCI_USD"):+.2f}% S1 FCI, {percent("gross_OPEX_USD_per_year"):+.2f}% gross OPEX, '
                    f'{percent("fresh_NaOH_kgph"):+.2f}% fresh NaOH, {percent("CaOH2_kgph"):+.2f}% lime, '
                    f'{percent("salt_cake_kgph"):+.2f}% salt cake and {percent("untracked_organics_kgph"):+.2f}% unresolved organics. '
                    f'U2 process heat changes {percent("U2_heating_kW"):+.2f}%, external heating '
                    f'{percent("external_heating_kW"):+.2f}% and internal heat recovery '
                    f'{percent("internal_heat_recovery_utility_equivalent_kW"):+.2f}%.',
                    f'S1 annual net GWP changes {percent("net_GWP_kgCO2e_per_year"):+.2f}%, while the magnitude of the '
                    f'storage credit changes {percent("storage_credit_kgCO2e_per_year"):+.2f}%. '
                    'The per-H2 GWP decrease therefore reflects both more H2 and the assumed organic-char carbon credit. '
                    'This credit depends on the fixed char-yield assumption and assumed storage permanence; it is not demonstrated by the ash data.']
        for ree in (True, False):
            df = frame[frame.ree_enabled == ree]
            for metric in ('MSP_USD_per_kg_H2','GWP_kgCO2e_per_kg_H2'):
                ranks = []
                for ash in sorted(df.ash_fraction.unique(), reverse=True):
                    sub = df[df.ash_fraction == ash].sort_values(metric)
                    ranks.append(f'{ash:.2%} ash: '+ ' < '.join(sub.scenario))
                out.append(f'REE {"On" if ree else "Off"}, {metric}: '+ '; '.join(ranks)+'.')
        out.append('The summary CSV contains the baseline, absolute difference and relative difference (%) for every numeric indicator '
                   'within the matching scenario/REE setting. Relative change is undefined (blank) when the baseline is zero. '
                   'Scientific interpretation must account for changing per-H2 denominators as well as annual burden and carbon-fate changes.')
    out += ['## Validation findings']
    for c in cases:
        maximum = max(abs(r['relative_error']) for r in c['balances'])
        bad = [r for r in c['process_checks'] if str(r['status']).startswith('FAIL')]
        out.append(f'Ash {c["ash_fraction"]:.2%}, REE {c["ree_enabled"]}: maximum independent unit/boundary mass/element residual '
                   f'{maximum:.3g}; maximum species change on repeat simulation {c["process"]["recycle_max_relative_change"]:.3g}; '
                   f'residual surrogate CH{c["process"]["residual_H_per_C"]:.4g}O{c["process"]["residual_O_per_C"]:.5g}. '
                   f'Existing process-check failures: {len(bad)}. HXN enthalpy audit: {json.dumps(c["hxn_audit"])}.')
        for r in bad:
            out.append(f'- {r["check"]}: {r["value"]} (reference/limit {r.get("expected", "")}); {r["status"]}.')
    out.append('D1 solubility is screened using the existing pure-water carbonate curve; NaOH/NaCl/KCl common-ion and activity effects '
               'are not modeled. EC1 dissolved carbonate fraction and XL1 removal fraction are fixed assumptions, not a multi-electrolyte equilibrium. '
               'An unflagged screen therefore does not prove all salts remain soluble in a real plant. '
               'The gas-yield transfer presumes the same organic chemistry and yields despite changing NaOH per kg DAF; that experimental response is unknown. '
               'The surrogate elemental closure establishes feasibility within this model, not an experimentally identified residue.')
    worst = max((abs(r['relative_error']) for r in reproduction), default=float('nan'))
    out.append(f'Baseline rerun after all sensitivities: maximum scenario-metric relative difference {worst:.3g}. '
               f'Original input/reference hashes unchanged: {provenance["inputs_unchanged"]}. '
               f'Pre-existing result hashes unchanged: {provenance["existing_results_unchanged"]}. '
               'See the provenance JSON and reproducibility CSV for evidence. Tests and command output are recorded in the tests log.')
    out += ['## Verification commands',
            '`python -m unittest biorefineries.ATT.test.test_ash_content_sensitivity -v` (dedicated gas, mass, element, '
            'steady-state, accounting and reproducibility checks).',
            '`python -m unittest discover -s test -p "test_att_*.py" -t <repository-root> -v` '
            '(the existing ATT regression suite). Logs: `ash_content_sensitivity_tests.log` and '
            '`ash_content_sensitivity_regression_tests.log`. The test logs establish the executed count and result.']
    for name in ('tests', 'regression_tests'):
        path = RESULTS/f'{PREFIX}_{name}.log'
        if path.exists():
            raw = path.read_bytes()
            log = raw.decode('utf-16' if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8', errors='replace')
            matches = re.findall(r'Ran \d+ tests? in [^\r\n]+', log)
            if matches:
                result = 'OK' if re.search(r'^OK\s*$', log, re.M) else 'NOT PASSING; inspect log'
                out.append(f'{name}: {matches[-1]}; {result}.')
    if failures:
        out += ['## Simulation failures: downstream results withheld', *[str(f) for f in failures]]
    if cases:
        out += ['## Environment', json.dumps(cases[0]['versions'])]
    (RESULTS/f'{PREFIX}_report.md').write_text('\n\n'.join(out)+'\n', encoding='utf-8')


def _figures(frame, cases):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages
    import numpy as np
    plt.rcParams.update({'font.size': 11, 'axes.spines.top': False, 'axes.spines.right': False,
                         'figure.facecolor': 'white', 'axes.titleweight': 'bold'})
    with PdfPages(RESULTS/f'{PREFIX}.pdf') as pdf:
        for ree in (True, False):
            data = [c for c in cases if c['ree_enabled'] == ree]
            if not data:
                continue
            fig, axes = plt.subplots(2, 3, figsize=(16, 9), constrained_layout=True)
            groups = [('Gas production', [('H2_kgph','H2'),('CH4_kgph','CH4')], 'kg/h'),
                      ('Chemical consumption', [('fresh_NaOH_kgph','Fresh NaOH'),('CaOH2_kgph','Ca(OH)2')], 'kg/h'),
                      ('Solids and unresolved organics', [('CaCO3_kgph','CaCO3'),('char_dry_kgph','Char dry'),
                                                        ('untracked_organics_kgph','Unresolved')], 'kg/h'),
                      ('Installed equipment capital', [('FCI_USD','FCI')], 'million USD'),
                      ('External heat and power', [('external_heating_kW','Heat'),('process_electricity_kW','Power')], 'MW'),
                      ('Gas processing power', [('U3K_power_kW','Compressor')], 'kW')]
            for ax, (title, metrics, ylabel) in zip(axes.flat, groups):
                x = np.arange(len(metrics))
                width = .8/len(data)
                for j, c in enumerate(data):
                    s1 = c['scenarios'][0]
                    scale = 1e6 if ylabel == 'million USD' else 1000 if ylabel == 'MW' else 1
                    vals = [(s1.get(key, c['process'].get(key)))/scale for key, _ in metrics]
                    bars = ax.bar(x-.4+width*(j+.5), vals, width, label=f'{c["ash_fraction"]:.2%} ash',
                                  color=['#234f78','#d37a30','#458b6d'][j%3])
                    ax.bar_label(bars, fmt='%.2f', padding=3, fontsize=8)
                ax.set_xticks(x, [label for _, label in metrics])
                ax.set(title=title, ylabel=ylabel)
                ax.margins(y=.18)
            axes.flat[0].legend(frameon=False)
            fig.suptitle(f'ATT ash sensitivity | REE {"On" if ree else "Off"}\nFixed dry feed and experimental DAF yields; provisional engineering model', fontsize=18)
            pdf.savefig(fig)
            plt.close(fig)
        if not frame.empty:
            fig, axes = plt.subplots(2, 2, figsize=(13, 9), constrained_layout=True)
            for row, ree in enumerate((True, False)):
                for col, (key, ylabel) in enumerate((('MSP_USD_per_kg_H2','H2 MSP (USD/kg H2)'),
                                                    ('GWP_kgCO2e_per_kg_H2','Net GWP (kg CO2e/kg H2)'))):
                    ax = axes[row,col]
                    sub = frame[frame.ree_enabled == ree]
                    if sub.empty:
                        ax.set_visible(False)
                        continue
                    ashes = sorted(sub.ash_fraction.unique(), reverse=True)
                    x = np.arange(3)
                    width = .8/len(ashes)
                    for j, ash in enumerate(ashes):
                        values = [float(sub[(sub.ash_fraction == ash)&(sub.scenario == s)][key].iloc[0]) for s in ('S1','S2','S3')]
                        bars = ax.bar(x-.4+width*(j+.5), values, width, label=f'{ash:.2%} ash',
                                      color=['#234f78','#d37a30','#458b6d'][j%3])
                        ax.bar_label(bars, fmt='%.3f', padding=3, fontsize=9)
                    ax.set_xticks(x, ['S1 Land','S2 Marine','S3 Industrial'])
                    ax.set(ylabel=ylabel, title=f'REE {"On" if ree else "Off"}')
                    ax.margins(y=.18)
            next((ax for ax in axes.flat if ax.get_legend_handles_labels()[0]), axes[0,0]).legend(frameon=False)
            fig.suptitle('Scenario economics and climate impact\nExisting waste-heat accounting and carbon storage credits retained', fontsize=17)
            pdf.savefig(fig)
            plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--ash', type=float, default=UCLA_ASH)
    parser.add_argument('--no-ree', action='store_true')
    parser.add_argument('--include-reference', action='store_true', help='Also evaluate historical 17.2% ash')
    args = parser.parse_args()
    if args.worker:
        print('ATT_ASH_RESULT='+json.dumps(_worker(args.ash, not args.no_ree), default=float))
        return
    RESULTS.mkdir(exist_ok=True)
    inputs = _hashes([*ROOT.glob('data/*.yaml'), *ROOT.glob('reference_data/**/*')])
    old_results = _hashes(p for p in RESULTS.rglob('*') if p.is_file() and
                         not any(part.startswith(PREFIX) or part in ('.nb', '.mpl')
                                 for part in p.relative_to(RESULTS).parts))
    cases, repeated, failures = [], [], []
    ashes = [BASELINE_ASH, UCLA_ASH] + ([.172] if args.include_reference else [])
    for ash in ashes:
        for ree in (True, False):
            print(f'Running ash={ash:.2%}, REE={ree}', flush=True)
            try:
                cases.append(run_case(ash, ree))
            except Exception:
                failures.append(dict(ash_fraction=ash, ree_enabled=ree, traceback=traceback.format_exc()))
                print(failures[-1]['traceback'], flush=True)
    for ree in (True, False):
        print(f'Repeating baseline after sensitivities, REE={ree}', flush=True)
        try:
            repeated.append(run_case(BASELINE_ASH, ree))
        except Exception:
            failures.append(dict(ash_fraction=BASELINE_ASH, ree_enabled=ree, traceback=traceback.format_exc()))
    bad_reproduction = [r for r in _reproduction_rows(cases, repeated) if r['status'] == 'FAIL']
    if bad_reproduction:
        failures.append(dict(check='Baseline reproducibility', failures=bad_reproduction))
    provenance = dict(requested_ash_fractions=ashes, input_sha256_before=inputs, existing_result_sha256_before=old_results,
                      inputs_unchanged=inputs == _hashes(ROOT/p for p in inputs),
                      existing_results_unchanged=old_results == _hashes(ROOT/p for p in old_results))
    (RESULTS/f'{PREFIX}_provenance.json').write_text(json.dumps(provenance, indent=2), encoding='utf-8')
    _export(cases, repeated, provenance, failures)
    if failures or not provenance['inputs_unchanged'] or not provenance['existing_results_unchanged']:
        raise SystemExit('Analysis has failures; see sensitivity report and data JSON')
    print('Generated sensitivity CSV, report, PDF and detailed audits under ATT/results.', flush=True)


if __name__ == '__main__':
    main()
