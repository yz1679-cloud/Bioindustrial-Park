"""Separate environmental credits on the unchanged ATT process and baseline CI.

Run from the repository root:
    python -m biorefineries.ATT.analyses.avoided_emissions

All generated files, including the opt-in comprehensive report, stay inside
ATT/results/avoided_emissions. No stream factors or process impacts are set here.
"""
import argparse
from copy import deepcopy
import json
import math

from chemicals.elements import periodic_table

from biorefineries.ATT.analyses import inventory, lca
from biorefineries.ATT.analyses.paths import ATT_ROOT, output_dir
from biorefineries.ATT.units._att import _SARGASSUM_DRY_IDS

__all__ = ('gcc_production_emissions', 'organic_inventory', 'boyle_coefficients',
           'decomposition_emissions', 'calculate_avoided_emissions', 'scenario_rows', 'generate')

_ELEMENTS = ('C', 'H', 'O', 'N', 'S')
_INORGANIC_IDS = frozenset(('Ash', 'NaCl', 'KCl', 'REO'))
_PARAMETERS = ('anaerobic_fraction', 'anaerobic_biodegradability',
               'aerobic_mineralization', 'methane_realization')


def assumptions():
    """Return independent configuration; callers cannot mutate baseline settings."""
    return deepcopy(lca._LCA['avoided_emissions'])


def gcc_production_emissions(products, emission_factor=None):
    """Positive avoided kg CO2e on the supplied streams' mass basis (normally /h)."""
    if emission_factor is None:
        emission_factor = assumptions()['avoided_gcc_production_emissions']['emission_factor']
    return sum(float(s.imass['CaCO3']) for s in products) * float(emission_factor)


def organic_inventory(feed):
    """CHONS kmol and kg on the supplied inlet basis (normally kg/h).

    Use the process's biomass component register and native chemical MWs;
    water, ash minerals, salts and REO do not enter the empirical formula.
    Atomic masses come from the same elements library as ThermoSTEAM.
    """
    atoms = dict.fromkeys(_ELEMENTS, 0.)
    organics = 0.
    for ID in _SARGASSUM_DRY_IDS:
        if ID in _INORGANIC_IDS:
            continue
        mass = float(feed.imass[ID])
        if mass == 0.:
            continue
        chemical = feed.chemicals[ID]
        if mass < 0. or not chemical.atoms.get('C') or set(chemical.atoms)-set(_ELEMENTS):
            raise ValueError(f'Organic component {ID} must have nonnegative mass and a CHONS formula.')
        organics += mass
        kmol = mass / chemical.MW
        for e in _ELEMENTS:
            atoms[e] += kmol * chemical.atoms.get(e, 0.)
    carbon = atoms['C']
    return dict(wet_mass_kg=float(feed.F_mass),
                dry_mass_kg=float(feed.F_mass-feed.imass['Water']),
                organic_mass_kg=organics, element_kmol=atoms,
                element_mass_kg={e: n*periodic_table[e].MW for e, n in atoms.items()},
                normalized_formula={e: n/carbon if carbon else 0. for e, n in atoms.items()},
                formula_unit_kmol=carbon,
                formula_mw_kg_per_kmol=organics/carbon if carbon else 0.)


def boyle_coefficients(atoms):
    """Boyle stoichiometry; positive H2O denotes water consumed, not emitted."""
    a, b, c, d, e = (float(atoms.get(k, 0.)) for k in _ELEMENTS)
    ch4 = a/2. + b/8. - c/4. - 3.*d/8. - e/4.
    co2 = a-ch4
    if min(ch4, co2) < -1e-12:
        raise ValueError('The organic composition gives a negative Boyle gas coefficient.')
    return dict(CH4=max(0., ch4), CO2=max(0., co2),
                H2O=a-b/4.-c/2.+3.*d/4.+e/2., NH3=d, H2S=e)


def decomposition_emissions(feed, *, anaerobic_fraction=None, anaerobic_biodegradability=None,
                            aerobic_mineralization=None, methane_realization=None, ch4_gwp100=None):
    """Separate gas formation, atmospheric methane and its optional climate credit.

    Partition original organics first, then mineralize once in each pathway.
    The carbon not mineralized stays in an explicit residual ledger. Produced
    biogenic CO2 is not automatically an atmospheric flux or a climate credit.
    """
    cfg = assumptions()['avoided_sargassum_decomposition_emissions']
    overrides = dict(anaerobic_fraction=anaerobic_fraction,
                     anaerobic_biodegradability=anaerobic_biodegradability,
                     aerobic_mineralization=aerobic_mineralization, methane_realization=methane_realization)
    p = {key: float(cfg[key] if value is None else value) for key, value in overrides.items()}
    if any(not math.isfinite(v) or not 0. <= v <= 1. for v in p.values()):
        raise ValueError('Pathway, biodegradability, mineralization and realization fractions must be in [0, 1].')
    gwp = float(cfg['ch4_gwp100'] if ch4_gwp100 is None else ch4_gwp100)
    if not math.isfinite(gwp) or gwp < 0.:
        raise ValueError('Methane GWP100 must be finite and nonnegative.')
    inv = organic_inventory(feed)
    coeff = boyle_coefficients(inv['normalized_formula'])
    f, bi, mineral, realization = (p[k] for k in _PARAMETERS)
    anaerobic_units = inv['formula_unit_kmol'] * f
    gas_units = anaerobic_units * bi
    mw_ch4 = float(feed.chemicals['CH4'].MW)
    mw_co2 = float(feed.chemicals['CO2'].MW)
    carbon = inv['element_mass_kg']['C']
    ch4 = gas_units * coeff['CH4'] * mw_ch4
    co2_an = gas_units * coeff['CO2'] * mw_co2
    co2_aer = carbon * (1.-f) * mineral * mw_co2 / periodic_table['C'].MW
    atmospheric = ch4 * realization
    return dict(inventory=inv, parameters=dict(p, aerobic_fraction=1.-f, ch4_gwp100=gwp),
                boyle_coefficients=coeff,
                anaerobic_organic_mass_kg=inv['organic_mass_kg']*f,
                aerobic_organic_mass_kg=inv['organic_mass_kg']*(1.-f),
                anaerobic_carbon_kg=carbon*f, aerobic_carbon_kg=carbon*(1.-f),
                anaerobic_gas_carbon_kg=carbon*f*bi,
                aerobic_gas_carbon_kg=carbon*(1.-f)*mineral,
                unmineralized_carbon_kg=carbon*(f*(1.-bi)+(1.-f)*(1.-mineral)),
                anaerobic_ch4_kg=ch4, anaerobic_co2_kg=co2_an, aerobic_co2_kg=co2_aer,
                biogenic_co2_kg=co2_an+co2_aer,
                atmospheric_ch4_kg=atmospheric, unrealized_ch4_kg=ch4-atmospheric,
                avoided_co2e_kg=atmospheric*gwp, ch4_gwp100=gwp)


def _check_existing_credits(system, products, gcc, decomposition):
    if gcc and (lca._LCA['coproduct']['CaCO3_treatment'] == 'substitution'
                or any(s.characterization_factors.get(lca.KEY, 0.) for s in products)):
        raise ValueError('GCC displacement is already present in original CI; disable the additional GCC indicator.')
    items = system.process_impact_items.get(lca.KEY, ())
    if decomposition and any(any(word in item.name.lower() for word in ('beach', 'decompos', 'avoided ch4'))
                             for item in items):
        raise ValueError('Beach decomposition is already present in original CI; disable the additional decomposition indicator.')


def calculate_avoided_emissions(system, original_ci=None, *, include_gcc=None,
                               include_decomposition=None, ch4_gwp100=None,
                               anaerobic_fraction=None, anaerobic_biodegradability=None,
                               aerobic_mineralization=None, methane_realization=None):
    """Read actual streams; return original and expanded CI on two bases.

    ``original_ci`` may supply the existing S2/S3 CI with its WHR adjustment.
    Otherwise read the system's existing GWP100; apply the standard LCA first.
    New credits are positive reductions and are never added to System impacts.
    """
    cfg = assumptions()
    g = cfg['avoided_gcc_production_emissions']
    d = cfg['avoided_sargassum_decomposition_emissions']
    gcc = bool(g['enabled'] if include_gcc is None else include_gcc)
    dec = bool(d['enabled'] if include_decomposition is None else include_decomposition)
    streams = inventory._streams(system)
    output_ids = {s.ID for s in system.products}
    products = [streams[ID] for ID in g['product_streams'] if ID in output_ids]
    _check_existing_credits(system, products, gcc, dec)
    feed = streams['att_sargassum_feed']
    wet = float(feed.F_mass)
    water = float(feed.imass['Water'])
    h2 = float(streams['h2_product'].imass['H2'])
    if wet <= 0. or h2 <= 0.:
        raise ValueError('Positive wet presscake and H2 component flows are required for CI.')
    if original_ci is None:
        original_ci = float(system.get_net_impact(lca.KEY)) / (float(system.operating_hours) * h2)
    dry = wet-water
    rot = decomposition_emissions(feed, ch4_gwp100=ch4_gwp100,
                                 anaerobic_fraction=anaerobic_fraction,
                                 anaerobic_biodegradability=anaerobic_biodegradability,
                                 aerobic_mineralization=aerobic_mineralization,
                                 methane_realization=methane_realization)
    gcc_potential = gcc_production_emissions(products)
    gcc_credit = gcc_potential if gcc else 0.
    dec_credit = rot['avoided_co2e_kg'] if dec else 0.
    storage = lca.get_att_stored_carbon_credit(system)
    original = float(original_ci)
    per_h2 = dict(original_CI=original, existing_storage_credit=storage,
                  avoided_gcc_production_emissions=gcc_credit / h2,
                  avoided_sargassum_decomposition_emissions=dec_credit / h2,
                  expanded_CI=original - gcc_credit / h2 - dec_credit / h2,
                  main_CI=original - gcc_credit / h2,
                  potential_CI=original - gcc_credit / h2 - rot['avoided_co2e_kg'] / h2)
    return dict(per_kg_h2=per_h2,
                per_tonne_wet_presscake={k: v * h2 / wet * 1000. for k, v in per_h2.items()},
                per_tonne_dry={k: v * h2 / dry * 1000. for k, v in per_h2.items()},
                activity=dict(presscake_wet_kgph=wet, presscake_water_kgph=water,
                              presscake_dry_kgph=wet-water, presscake_moisture_fraction=water/wet,
                              h2_kgph=h2,
                              pure_caco3_kgph=sum(float(s.imass['CaCO3']) for s in products),
                              cakes=[dict(stream=s.ID, total_kgph=float(s.F_mass),
                                          pure_caco3_kgph=float(s.imass['CaCO3'])) for s in products],
                              potential_gcc_kgCO2eph=gcc_potential,
                              potential_decomposition_kgCO2eph=rot['avoided_co2e_kg'],
                              anaerobic_ch4_kgph=rot['anaerobic_ch4_kg'],
                              atmospheric_ch4_kgph=rot['atmospheric_ch4_kg'],
                              anaerobic_co2_kgph=rot['anaerobic_co2_kg'],
                              aerobic_co2_kgph=rot['aerobic_co2_kg'],
                              biogenic_co2_kgph=rot['biogenic_co2_kg']),
                include_gcc=gcc, include_decomposition=dec, ch4_gwp100=rot['ch4_gwp100'],
                parameters=rot['parameters'], decomposition=rot,
                decomposition_basis='actual presscake organic component CHONS',
                conversion_assumption=d['conversion_assumption'],
                legacy_beach_rot_included=False, biogenic_co2_included=False)


def scenario_rows(system, scenario, ree_enabled, original_ci):
    """Three actual-flow bases, separate ledgers and one-at-a-time sensitivities."""
    rows = []
    cfg = assumptions()['avoided_sargassum_decomposition_emissions']
    for label, gcc, dec in (('main', True, False), ('potential', True, True), ('configured', None, None),
                            ('original_only', False, False), ('gcc_only', True, False), ('decomposition_only', False, True)):
        settings = [('reference', None, {})]
        if label == 'potential':
            settings += [(key, float(value), {key: float(value)})
                         for key, values in cfg['sensitivities'].items() for value in values]
        for parameter, value, overrides in settings:
            result = calculate_avoided_emissions(system, original_ci, include_gcc=gcc,
                                                include_decomposition=dec, **overrides)
            a = result['activity']
            inv = result['decomposition']['inventory']
            scales = dict(per_kg_h2=1./a['h2_kgph'], per_tonne_wet_presscake=1000./a['presscake_wet_kgph'],
                          per_tonne_dry=1000./a['presscake_dry_kgph'])
            for basis, scale in scales.items():
                rows.append(dict(scenario=scenario, ree_enabled=ree_enabled, basis=basis,
                                 credit_case=label, **result['parameters'],
                                 sensitivity_parameter=parameter, sensitivity_value=value,
                                 reference_case=(parameter=='reference'),
                                 decomposition_basis=result['decomposition_basis'],
                                 include_gcc=result['include_gcc'], include_decomposition=result['include_decomposition'],
                                 anaerobic_ch4_kg=a['anaerobic_ch4_kgph']*scale,
                                 atmospheric_ch4_kg=a['atmospheric_ch4_kgph']*scale,
                                 anaerobic_co2_kg=a['anaerobic_co2_kgph']*scale,
                                 aerobic_co2_kg=a['aerobic_co2_kgph']*scale,
                                 biogenic_co2_kg=a['biogenic_co2_kgph']*scale,
                                 methane_climate_impact_kgCO2e=a['potential_decomposition_kgCO2eph']*scale,
                                 organic_mass_kg=inv['organic_mass_kg']*scale,
                                 **{f'organic_{e}_kg': m*scale for e, m in inv['element_mass_kg'].items()},
                                 unmineralized_carbon_kg=result['decomposition']['unmineralized_carbon_kg']*scale,
                                 unrealized_ch4_kg=result['decomposition']['unrealized_ch4_kg']*scale,
                                 formula_unit_kmol=inv['formula_unit_kmol']*scale,
                                 formula_mw_kg_per_kmol=inv['formula_mw_kg_per_kmol'],
                                 **{f'formula_{e}_per_C': n for e, n in inv['normalized_formula'].items()},
                                 conversion_assumption=result['conversion_assumption'], **result[basis]))
    return rows


BASIS_LABELS = dict(per_kg_h2='kg CO2e/kg H2', per_tonne_dry='kg CO2e/tonne dry Sargassum (0 wt% moisture)',
                    per_tonne_wet_presscake='kg CO2e/tonne modeled wet presscake (actual model moisture)')


def reference_rows(data, credit_case, basis=None):
    return [r for r in data['avoided_emissions']['rows'] if r['credit_case']==credit_case
            and r['reference_case'] and (basis is None or r['basis']==basis)]


def _method_text():
    d = assumptions()['avoided_sargassum_decomposition_emissions']
    return ('Hypothetical ATT presscake left to decompose on a beach. CHONS inventories come from actual organic '
            f'component formulas, including protein sulfur. Original organic matter is allocated {d["anaerobic_fraction"]:.0%} anaerobic and '
            f'{1.-d["anaerobic_fraction"]:.0%} aerobic in the reference screening scenario. Boyle CH4 and CO2 are scaled once by anaerobic '
            'biodegradability; aerobic carbon oxidation uses a separately configurable mineralization fraction. '
            'Its reference transfers the anaerobic-derived BI to aerobic mineralization by modeling assumption, '
            'not independent aerobic validation. '
            'Only atmospheric methane times GWP100 enters the additional climate indicator. '
            'Biogenic CO2 is modeled formation, not necessarily direct atmospheric release in waterlogged settings. '
            'Neither historical IPCC beach rot nor the former Bueno factor enters this calculation.')


def report_section(data):
    """Portable optional-indicator tables, including physical gas accounting."""
    from html import escape
    potential = reference_rows(data, 'potential')
    d = data['avoided_emissions']['assumptions']['avoided_sargassum_decomposition_emissions']
    parts = ['<section class="card" id="avoided-emissions"><h2>Main CI and additional beach-decomposition scenario</h2>',
             '<p>Main CI = original CI minus GCC avoided production. Existing storage remains included once in original CI. '
             'Beach decomposition is excluded from main CI and baseline ATT LCA.</p>',
             '<p>'+escape(_method_text())+'</p>',
             '<p><a href="ATT_S3_Figures.pdf">S3 figures</a> | '
             '<a href="avoided_emissions_report.md">Equations, inputs and limitations</a> | '
             '<a href="avoided_emissions_sensitivity.csv">One-at-a-time sensitivity data</a></p>']
    for basis, unit in BASIS_LABELS.items():
        parts.append('<h3>'+escape(unit)+'</h3><table><thead><tr><th>Scenario</th><th>REE</th>'
                     '<th>Original CI</th><th>GCC reduction</th><th>Main CI</th>'
                     '<th>Additional methane reduction</th><th>Potential CI</th></tr></thead><tbody>')
        for r in potential:
            if r['basis'] != basis:
                continue
            values = ''.join(f'<td>{r[k]:.6f}</td>' for k in ('original_CI', 'avoided_gcc_production_emissions',
                             'main_CI', 'avoided_sargassum_decomposition_emissions', 'expanded_CI'))
            parts.append(f'<tr><td>{r["scenario"]}</td><td>{"On" if r["ree_enabled"] else "Off"}</td>{values}</tr>')
        parts.append('</tbody></table>')
    parts += ['<h3 id="potential-decomposition">Physical gases per tonne wet ATT presscake</h3><p>CH4 production and atmospheric CH4 are distinct. '
              'CO2 columns describe biogenic formation and receive no climate credit.</p>',
              '<table><tr><th>Scenario</th><th>REE</th><th>CH4 produced</th><th>Atmospheric CH4</th>'
              '<th>Anaerobic CO2</th><th>Aerobic CO2</th><th>Total biogenic CO2</th></tr>']
    for r in potential:
        if r['basis'] == 'per_tonne_wet_presscake':
            values = ''.join(f'<td>{r[k]:.6f}</td>' for k in ('anaerobic_ch4_kg','atmospheric_ch4_kg',
                             'anaerobic_co2_kg','aerobic_co2_kg','biogenic_co2_kg'))
            parts.append(f'<tr><td>{r["scenario"]}</td><td>{"On" if r["ree_enabled"] else "Off"}</td>{values}</tr>')
    parts += ['</table><p>Independent one-at-a-time sensitivities vary anaerobic allocation, anaerobic biodegradability, '
              'aerobic mineralization and atmospheric methane realization. Each holds the remaining inputs fixed.</p>',
              '<img src="potential_decomposition_sensitivity.png" alt="Four independent decomposition sensitivities: methane climate impact and physical biogenic CO2" style="width:100%">',
              '<p>'+escape(d['limitation'])+'</p></section>']
    return '<div class="wrap">'+'\n'.join(parts)+'</div>'


def _write_outputs(out, data):
    from biorefineries.ATT.analyses.comprehensive_report import _save_csv
    payload = data['avoided_emissions']
    rows = payload['rows']
    main = reference_rows(data, 'main')
    potential = reference_rows(data, 'potential')
    sensitivity = [r for r in rows if r['credit_case']=='potential' and not r['reference_case']]
    _save_csv(out/'avoided_emissions.csv', main)
    _save_csv(out/'avoided_emissions_sensitivity.csv', rows)
    _save_csv(out/'potential_decomposition.csv', potential)
    (out/'avoided_emissions.json').write_text(json.dumps(payload, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    d = payload['assumptions']['avoided_sargassum_decomposition_emissions']
    g = payload['assumptions']['avoided_gcc_production_emissions']
    lines = ['# ATT avoided-emission indicators', '', _method_text(), '',
             'Main CI = original CI - GCC. Potential CI = main CI - atmospheric methane climate impact. '
             'The optional calculation never changes system impacts, TEA or H2 production.', '',
             '## Equations', '',
             'For carbon-normalized organic formula CaHbOcNdSe, with a = 1:', '',
             '- y_CH4 = a/2 + b/8 - c/4 - 3d/8 - e/4',
             '- y_CO2 = a/2 - b/8 + c/4 + 3d/8 + e/4',
             '- n_formula = organic carbon kmol, summed from component mass / native MW times C atoms',
             '- CH4 produced = n_formula * f_an * BI_an * y_CH4 * MW_CH4',
             '- Anaerobic CO2 = n_formula * f_an * BI_an * y_CO2 * MW_CO2',
             '- Aerobic CO2 = organic C mass * (1 - f_an) * MF_aer * MW_CO2 / AW_C',
             '- Atmospheric CH4 = CH4 produced * methane realization',
             '- Additional avoided CO2e = atmospheric CH4 * CH4 GWP100',
             '- Unmineralized C = organic C * [f_an * (1 - BI_an) + (1 - f_an) * (1 - MF_aer)]', '',
             'No legacy GWP-minus-CO2 subtraction and no 87.5% raw-moisture conversion are used. '
             'Unrealized methane is tracked separately and is not presumed to become atmospheric CO2.', '',
             '## Inputs, sources and assumptions', '', '| Parameter | Reference | Source / status |', '|---|---:|---|',
             f'| Anaerobic fraction of original organics | {d["anaerobic_fraction"]:g} | {d["allocation_note"]} |',
             f'| Anaerobic BI | {d["anaerobic_biodegradability"]:.12g} | {d["anaerobic_biodegradability_source"]} |',
             f'| Aerobic mineralization | {d["aerobic_mineralization"]:g} | {d["aerobic_mineralization_source"]} |',
             f'| Atmospheric methane realization | {d["methane_realization"]:g} | {d["methane_realization_note"]} |',
             f'| Non-fossil methane GWP100 | {d["ch4_gwp100"]:g} | {d["reference_gwp_source"]} |', '',
             f'Boyle: [{d["source"]}]({d["url"]}).',
             f'BI: [Milledge et al., Table 11]({d["anaerobic_biodegradability_url"]}).',
             f'Aerobic factor: [transfer of the anaerobic-derived BI by modeling assumption]({d["aerobic_mineralization_url"]}); '
             'not an independently validated aerobic biodegradability value.',
             f'GWP: [IPCC errata]({d["reference_gwp_url"]}).', '',
             f'GCC remains {g["emission_factor"]:g} kg CO2e/kg contained CaCO3: [{g["source"]}]({g["url"]}).', '',
             '## Active organic composition per tonne wet presscake', '',
             '| Scenario | REE | Organics kg | C kg | H kg | O kg | N kg | S kg | Formula units kmol | Formula MW kg/kmol |',
             '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for r in potential:
        if r['basis'] != 'per_tonne_wet_presscake':
            continue
        values = ' | '.join(f'{r[k]:.9f}' for k in ('organic_mass_kg','organic_C_kg','organic_H_kg','organic_O_kg',
                           'organic_N_kg','organic_S_kg','formula_unit_kmol','formula_mw_kg_per_kmol'))
        lines.append(f'| {r["scenario"]} | {"On" if r["ree_enabled"] else "Off"} | {values} |')
    reference = next(r for r in potential if r['basis']=='per_tonne_wet_presscake')
    formula = 'C'+''.join(f'{e}{reference[f"formula_{e}_per_C"]:.8f}' for e in ('H','O','N','S'))
    lines += ['', f'First reference case organic formula: **{formula}**. Recomputed from native component formulas; not a hardcoded input.', '',
              'Native atomic masses are from chemicals.elements.periodic_table, matching ThermoSTEAM molecular weights. '
              'The older carbon-fate ledger uses rounded AW_C = 12.011; its tiny carbon-mass difference is retained to preserve baseline reporting.', '']
    for basis, unit in BASIS_LABELS.items():
        lines += [f'## Reference results: {unit}', '',
                  '| Scenario | REE | Original CI | GCC reduction | Main CI | Additional methane reduction | Potential CI |',
                  '|---|---|---:|---:|---:|---:|---:|']
        for r in potential:
            if r['basis']==basis:
                values=' | '.join(f'{r[k]:.9f}' for k in ('original_CI','avoided_gcc_production_emissions','main_CI',
                                 'avoided_sargassum_decomposition_emissions','expanded_CI'))
                lines.append(f'| {r["scenario"]} | {"On" if r["ree_enabled"] else "Off"} | {values} |')
        lines.append('')
    lines += ['## Physical gas formation per tonne wet ATT presscake', '',
              '| Scenario | REE | CH4 produced kg | Atmospheric CH4 kg | Anaerobic CO2 kg | Aerobic CO2 kg | Total biogenic CO2 kg |',
              '|---|---|---:|---:|---:|---:|---:|']
    for r in potential:
        if r['basis']=='per_tonne_wet_presscake':
            values=' | '.join(f'{r[k]:.9f}' for k in ('anaerobic_ch4_kg','atmospheric_ch4_kg','anaerobic_co2_kg','aerobic_co2_kg','biogenic_co2_kg'))
            lines.append(f'| {r["scenario"]} | {"On" if r["ree_enabled"] else "Off"} | {values} |')
    lines += ['', '## Independent one-at-a-time sensitivity', '', d['sensitivity_note'], '',
              'S3 REE On; gas masses and climate impact below are per tonne actual wet presscake. '
              'The full CSV includes all six cases and wet, dry and H2 bases.', '',
              '| Varied parameter | Value | CH4 produced kg | Atmospheric CH4 kg | Anaerobic CO2 kg | Aerobic CO2 kg | Total biogenic CO2 kg | Methane climate impact kg CO2e |',
              '|---|---:|---:|---:|---:|---:|---:|---:|']
    for r in sensitivity:
        if r['scenario']=='S3' and r['ree_enabled'] and r['basis']=='per_tonne_wet_presscake':
            values=' | '.join(f'{r[k]:.9f}' for k in ('anaerobic_ch4_kg','atmospheric_ch4_kg','anaerobic_co2_kg',
                              'aerobic_co2_kg','biogenic_co2_kg','methane_climate_impact_kgCO2e'))
            lines.append(f'| {r["sensitivity_parameter"]} | {r["sensitivity_value"]:.9g} | {values} |')
    lines += ['', '![One-at-a-time sensitivity](potential_decomposition_sensitivity.png)', '',
              '## Limitations and carbon-credit accounting', '', d['limitation'], '',
              'The methane-based BI is applied to anaerobic CO2 as a modeling approximation. '
              'No timescale or beach-wide anaerobic fraction has been established. The aerobic screening interval '
              'includes the revised BI-transfer reference and retains the earlier comparison values; it is not a measured Sargassum range. '
              'The reference aerobic factor is an anaerobic-derived BI transfer assumption, not independent aerobic validation. NH3/H2S stoichiometry is included '
              'in Boyle closure but these gases receive no characterization in this methane-only indicator.', '',
              'Existing stored-carbon credit is neither recalculated nor subtracted a second time. Physical biogenic '
              'CO2 is never added to the methane climate credit. Combined storage and avoided-methane claims remain '
              'conditional on compatible carbon fate, counterfactual and permanence evidence.', '',
              '## Reproduce', '', '```text',
              'python -m biorefineries.ATT.analyses.comprehensive_report',
              'python -m biorefineries.ATT.analyses.s3_figures', '```', '']
    (out/'avoided_emissions_report.md').write_text('\n'.join(lines), encoding='utf-8')
    _figure(out, main, potential)
    from matplotlib import pyplot as plt
    fig = plt.figure(figsize=(13, 8.5))
    fig.suptitle('One-at-a-time decomposition sensitivities | S3 REE On', fontsize=16, y=.96)
    fig.text(.09,.88,'All other inputs fixed. Dotted lines mark reference inputs; gas formation and methane climate impact are distinct.',fontsize=9)
    draw_decomposition_sensitivity(fig, sensitivity)
    fig.text(.09,.06,'Aerobic reference assumes transfer of anaerobic BI; no independent aerobic validation. Biogenic CO2 formation receives no climate credit.',fontsize=8)
    fig.savefig(out/'potential_decomposition_sensitivity.png', dpi=180)
    fig.savefig(out/'potential_decomposition_sensitivity.pdf')
    plt.close(fig)


def draw_decomposition_sensitivity(fig, rows):
    """Four OAT panels; physical CO2 and methane CO2e have distinct axes."""
    cfg = assumptions()['avoided_sargassum_decomposition_emissions']
    labels = ('Anaerobic fraction', 'Anaerobic biodegradability',
              'Aerobic mineralization', 'Atmospheric methane realization')
    positions = ((.09,.55,.33,.23), (.59,.55,.33,.23),
                 (.09,.19,.33,.23), (.59,.19,.33,.23))
    for parameter, label, position in zip(_PARAMETERS, labels, positions):
        series = sorted((r for r in rows if r['scenario']=='S3' and r['ree_enabled']
                         and r['basis']=='per_tonne_wet_presscake' and r['credit_case']=='potential'
                         and r['sensitivity_parameter']==parameter), key=lambda r:r['sensitivity_value'])
        ax = fig.add_axes(position)
        physical = ax.twinx()
        x = [r['sensitivity_value'] for r in series]
        ax.plot(x, [r['methane_climate_impact_kgCO2e'] for r in series], 'o-', color='#176B50', label='Methane climate impact')
        physical.plot(x, [r['biogenic_co2_kg'] for r in series], 's--', color='#B15F20', label='Biogenic CO2 formation')
        ax.axvline(cfg[parameter], color='#64748B', linewidth=.8, linestyle=':')
        ax.set_xlabel(label, fontsize=9)
        ax.set_ylabel('kg CO2e / t wet presscake', color='#176B50', fontsize=8)
        physical.set_ylabel('kg biogenic CO2 / t wet presscake', color='#B15F20', fontsize=8)
        ax.tick_params(axis='y', labelcolor='#176B50', labelsize=8)
        physical.tick_params(axis='y', labelcolor='#B15F20', labelsize=8)
        ax.tick_params(axis='x', labelsize=8)
        ax.set_ylim(bottom=0.)
        physical.set_ylim(bottom=0.)
        ax.grid(alpha=.2)
        if parameter == _PARAMETERS[0]:
            lines = ax.lines[:1]+physical.lines[:1]
            ax.legend(lines, [line.get_label() for line in lines], fontsize=7, loc='upper center', bbox_to_anchor=(.5,1.28))


def _figure(out, rows, potential):
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib import pyplot as plt
    selected = [r for r in rows if r['basis']=='per_kg_h2']
    companion = [r for r in potential if r['basis']=='per_kg_h2']
    fig, ax = plt.subplots(figsize=(11, 6.5))
    x = list(range(len(selected)))
    ax.bar([i-.2 for i in x], [r['expanded_CI'] for r in selected], .4, label='Main: GCC included; without decomposition')
    ax.bar([i+.2 for i in x], [r['expanded_CI'] for r in companion], .4, label='Potential additional beach-decomposition avoidance')
    ax.scatter(x,[r['original_CI'] for r in selected],marker='D',s=25,color='#233746',label='Original ATT CI',zorder=4)
    ax.set_xticks(x, [f'{r["scenario"]}\nREE {"On" if r["ree_enabled"] else "Off"}' for r in selected])
    ax.set_ylabel('kg CO2e/kg H2')
    ax.set_title(f'GCC-adjusted main CI and potential decomposition effect (CH4 GWP100 = {selected[0]["ch4_gwp100"]:g})')
    ax.axhline(0, color='black', linewidth=.7)
    ax.legend()
    fig.tight_layout(rect=(0,.20,1,1))
    d = assumptions()['avoided_sargassum_decomposition_emissions']
    fig.text(.07,.06,f'Component-specific Boyle + aerobic carbon oxidation; anaerobic fraction {d["anaerobic_fraction"]:g}, BI {d["anaerobic_biodegradability"]:.4f}.\n'
             f'Aerobic mineralization {d["aerobic_mineralization"]:g}; atmospheric methane realization {d["methane_realization"]:g}; GWP100 {d["ch4_gwp100"]:g}.\n'
             'Aerobic factor assumes transfer of anaerobic BI; no independent aerobic validation. Biogenic CO2 has no climate credit.\n'
             'GCC and existing storage remain unchanged in both versions. Historical IPCC and Bueno indicators are excluded.', fontsize=8.5)
    fig.savefig(out/'avoided_emissions_ci.png', dpi=180)
    fig.savefig(out/'avoided_emissions_ci.pdf')
    plt.close(fig)


def generate():
    """Generate only inside the dedicated ATT folder, regardless of output-root env."""
    from biorefineries.ATT.analyses import comprehensive_report
    out = output_dir('avoided_emissions', root=ATT_ROOT/'results').resolve()
    out.mkdir(parents=True, exist_ok=True)
    data = comprehensive_report.collect(include_avoided_emissions=True)
    comprehensive_report.write_report(out, data)
    _write_outputs(out, data)
    from biorefineries.ATT.analyses.s3_figures import generate as s3_generate
    s3_generate(out=out, data=data)
    return out


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    print('Saved', generate(), flush=True)


if __name__ == '__main__':
    main()
