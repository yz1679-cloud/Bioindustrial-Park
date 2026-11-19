"""Separate environmental credits on the unchanged ATT process and baseline CI.

Run from the repository root:
    python -m biorefineries.ATT.analyses.avoided_emissions

All generated files, including the opt-in comprehensive report, stay inside
ATT/results/avoided_emissions. No stream factors or process impacts are set here.
"""
import argparse
from copy import deepcopy
import json

from biorefineries.ATT.analyses import inventory, lca
from biorefineries.ATT.analyses.paths import ATT_ROOT, output_dir

__all__ = ('gcc_production_emissions', 'decomposition_emissions', 'decomposition_emissions_dry',
           'raw_sargassum_equivalent', 'calculate_avoided_emissions', 'generate')


def assumptions():
    """Return independent configuration; callers cannot mutate baseline settings."""
    return deepcopy(lca._LCA['avoided_emissions'])


def gcc_production_emissions(products, emission_factor=None):
    """Positive avoided kg CO2e on the supplied streams' mass basis (normally /h)."""
    if emission_factor is None:
        emission_factor = assumptions()['avoided_gcc_production_emissions']['emission_factor']
    return sum(float(s.imass['CaCO3']) for s in products) * float(emission_factor)


def raw_sargassum_equivalent(presscake_mass, presscake_water, raw_moisture=None):
    """Optional reporting equivalence only; not the methane calculation basis."""
    if raw_moisture is None:
        raw_moisture = assumptions()['avoided_sargassum_decomposition_emissions']['reference_raw_moisture_fraction']
    return (float(presscake_mass) - float(presscake_water)) / (1. - float(raw_moisture))


def decomposition_emissions(raw_mass, ch4_gwp100=None):
    """Published wet-reference emissions; ATT calculations use dry solids below.

    Retained for reference checks and wet-basis reporting. Biogenic CO2 is
    informational, never CO2e.
    """
    c = assumptions()['avoided_sargassum_decomposition_emissions']
    gwp = float(c['ch4_gwp100'] if ch4_gwp100 is None else ch4_gwp100)
    gas = {name: sum(float(s['mass_fraction']) * float(s[name]) for s in c['species'].values()) / 1000.
           for name in ('CH4', 'CO2')}
    ch4 = float(raw_mass) * gas['CH4']
    return dict(avoided_ch4_kg=ch4, biogenic_co2_kg=float(raw_mass) * gas['CO2'],
                avoided_co2e_kg=ch4 * gwp, ch4_gwp100=gwp,
                weighted_ch4_g_per_kg_raw=gas['CH4'] * 1000.,
                weighted_co2_g_per_kg_raw=gas['CO2'] * 1000.)


def decomposition_emissions_dry(dry_mass_kg, ch4_gwp100=None):
    """Potential emissions from actual dry solids, independent of feed water.

    Derive kg CH4/t dry from the existing published weighted wet factor for
    one reference tonne. Do not recalculate rounded species-specific dry
    factors. The caller applies the unchanged realization fraction.
    """
    c = assumptions()['avoided_sargassum_decomposition_emissions']
    reference = decomposition_emissions(1000., ch4_gwp100)
    solids = 1. - float(c['reference_raw_moisture_fraction'])
    ch4_factor = reference['avoided_ch4_kg'] / solids
    co2_factor = reference['biogenic_co2_kg'] / solids
    tonnes_dry = float(dry_mass_kg) / 1000.
    ch4 = tonnes_dry * ch4_factor
    return dict(reference, avoided_ch4_kg=ch4, biogenic_co2_kg=tonnes_dry * co2_factor,
                avoided_co2e_kg=ch4 * reference['ch4_gwp100'],
                ch4_kg_per_t_dry=ch4_factor, biogenic_co2_kg_per_t_dry=co2_factor)


def _check_existing_credits(system, products, gcc, decomposition):
    if gcc and (lca._LCA['coproduct']['CaCO3_treatment'] == 'substitution'
                or any(s.characterization_factors.get(lca.KEY, 0.) for s in products)):
        raise ValueError('GCC displacement is already present in original CI; disable the additional GCC indicator.')
    items = system.process_impact_items.get(lca.KEY, ())
    if decomposition and any(any(word in item.name.lower() for word in ('beach', 'decompos', 'avoided ch4'))
                             for item in items):
        raise ValueError('Beach decomposition is already present in original CI; disable the additional decomposition indicator.')


def calculate_avoided_emissions(system, original_ci=None, *, include_gcc=None,
                               include_decomposition=None, ch4_gwp100=None, decomposition_fraction=1.):
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
    rot = decomposition_emissions_dry(dry, ch4_gwp100)
    raw = raw_sargassum_equivalent(wet, water)  # optional reporting equivalence only
    gcc_potential = gcc_production_emissions(products)
    gcc_credit = gcc_potential if gcc else 0.
    if not 0. <= decomposition_fraction <= 1.:
        raise ValueError('Decomposition realization must be between zero and one.')
    dec_credit = rot['avoided_co2e_kg'] * decomposition_fraction if dec else 0.
    storage = lca.get_att_stored_carbon_credit(system)
    original = float(original_ci)
    per_h2 = dict(original_CI=original, existing_storage_credit=storage,
                  avoided_gcc_production_emissions=gcc_credit / h2,
                  avoided_sargassum_decomposition_emissions=dec_credit / h2,
                  expanded_CI=original - gcc_credit / h2 - dec_credit / h2,
                  main_CI=original - gcc_credit / h2,
                  potential_CI=original - gcc_credit / h2 - rot['avoided_co2e_kg'] * decomposition_fraction / h2)
    return dict(per_kg_h2=per_h2,
                per_tonne_wet_presscake={k: v * h2 / wet * 1000. for k, v in per_h2.items()},
                per_tonne_dry={k: v * h2 / dry * 1000. for k, v in per_h2.items()},
                per_tonne_fresh_87_5={k: v * h2 / dry * 125. for k, v in per_h2.items()},
                per_tonne_wet_75={k: v * h2 / dry * 250. for k, v in per_h2.items()},
                activity=dict(presscake_wet_kgph=wet, presscake_water_kgph=water,
                              presscake_dry_kgph=wet-water, presscake_moisture_fraction=water/wet,
                              h2_kgph=h2, raw_equivalent_kgph=raw,
                              pure_caco3_kgph=sum(float(s.imass['CaCO3']) for s in products),
                              cakes=[dict(stream=s.ID, total_kgph=float(s.F_mass),
                                          pure_caco3_kgph=float(s.imass['CaCO3'])) for s in products],
                              potential_gcc_kgCO2eph=gcc_potential,
                              potential_decomposition_kgCO2eph=rot['avoided_co2e_kg'],
                              avoided_ch4_kgph=rot['avoided_ch4_kg'] * decomposition_fraction,
                              biogenic_co2_kgph=rot['biogenic_co2_kg']),
                include_gcc=gcc, include_decomposition=dec, ch4_gwp100=rot['ch4_gwp100'],
                decomposition_fraction=decomposition_fraction,
                weighted_ch4_g_per_kg_raw=rot['weighted_ch4_g_per_kg_raw'],
                weighted_co2_g_per_kg_raw=rot['weighted_co2_g_per_kg_raw'],
                ch4_kg_per_t_dry=rot['ch4_kg_per_t_dry'],
                decomposition_basis='actual presscake dry solids',
                raw_basis='optional fresh-mass reporting equivalence; upstream press not simulated',
                conversion_assumption=d['conversion_assumption'],
                legacy_beach_rot_included=False, biogenic_co2_included=False)


def scenario_rows(system, scenario, ree_enabled, original_ci):
    """Both functional units, independent switches, and CH4 GWP sensitivity."""
    rows = []
    cfg = assumptions()
    default = float(cfg['avoided_sargassum_decomposition_emissions']['ch4_gwp100'])
    gwps = dict.fromkeys([default, *cfg['avoided_sargassum_decomposition_emissions']['sensitivity_ch4_gwp100']])
    for gwp in gwps:
        for label, gcc, dec in (('main', True, False), ('potential', True, True), ('configured', None, None),
                                ('original_only', False, False), ('gcc_only', True, False), ('decomposition_only', False, True)):
            fractions = sorted(set([1., *cfg['avoided_sargassum_decomposition_emissions']['sensitivity_avoidance_fraction']])) if label=='potential' else [1.]
            for fraction in fractions:
                result = calculate_avoided_emissions(system, original_ci, include_gcc=gcc,
                                                    include_decomposition=dec, ch4_gwp100=gwp, decomposition_fraction=fraction)
                a = result['activity']
                scales = dict(per_kg_h2=1./a['h2_kgph'], per_tonne_wet_presscake=1000./a['presscake_wet_kgph'],
                              per_tonne_dry=1000./a['presscake_dry_kgph'], per_tonne_fresh_87_5=125./a['presscake_dry_kgph'],
                              per_tonne_wet_75=250./a['presscake_dry_kgph'])
                for basis, scale in scales.items():
                    rows.append(dict(scenario=scenario, ree_enabled=ree_enabled, basis=basis,
                                 credit_case=label, ch4_gwp100=gwp, reference_gwp=(gwp == default),
                                 decomposition_fraction=fraction, reference_fraction=(fraction==1.),
                                 decomposition_basis=result['decomposition_basis'],
                                 ch4_kg_per_t_dry=result['ch4_kg_per_t_dry'],
                                 include_gcc=result['include_gcc'], include_decomposition=result['include_decomposition'],
                                 biogenic_co2_kg=a['biogenic_co2_kgph']*scale,
                                 avoided_ch4_kg=a['avoided_ch4_kgph']*scale,
                                 raw_equivalent_kg=a['raw_equivalent_kgph']*scale,
                                 conversion_assumption=result['conversion_assumption'], **result[basis]))
    return rows


BASIS_LABELS = dict(per_kg_h2='kg CO2e/kg H2', per_tonne_dry='kg CO2e/tonne dry Sargassum (0 wt% moisture)',
                    per_tonne_fresh_87_5='kg CO2e/tonne fresh Sargassum equivalent (87.5 wt% moisture)',
                    per_tonne_wet_75='kg CO2e/tonne wet-feed equivalent (75 wt% moisture)',
                    per_tonne_wet_presscake='kg CO2e/tonne modeled wet presscake (actual model moisture)')


def reference_rows(data, credit_case, basis=None):
    return [r for r in data['avoided_emissions']['rows'] if r['credit_case']==credit_case
            and r['reference_gwp'] and r['reference_fraction'] and (basis is None or r['basis']==basis)]


def report_section(data):
    """Static, portable section embedded only in the opt-in comprehensive report."""
    from html import escape
    rows = reference_rows(data, 'main')
    potential = reference_rows(data, 'potential')
    moisture = next(r['moisture_fraction'] for r in data['functional'] if r['basis']=='per_kg_h2')
    dry_reference = decomposition_emissions_dry(1000.)
    parts = ['<section class="card" id="avoided-emissions"><h2>Main CI including GCC avoided production</h2>',
             '<p>Main CI = original CI - GCC avoided production. Existing storage is already included in original CI. '
             'Sargassum decomposition is excluded from main results and appears below as a potential additional analysis.</p>',
             f'<p>Actual modeled wet presscake moisture: {moisture*100:.3f} wt%. Dry-feed units throughout mean 0 wt% moisture. The two wet reference cases below are equivalent masses, not new simulations.</p>',
             '<p><a href="ATT_S3_Figures.pdf">Updated S3 figures</a> | <a href="avoided_emissions_ci.pdf">Six-case CI comparison</a></p>']
    for basis, unit in BASIS_LABELS.items():
        parts.append(f'<h3>{unit}</h3><table><thead><tr><th>Scenario</th><th>REE</th><th>Original CI</th>'
                     '<th>Existing storage (included)</th><th>Avoided GCC</th><th>Decomposition in main</th><th>Main CI</th></tr></thead><tbody>')
        for r in rows:
            if r['basis'] != basis:
                continue
            values = ''.join(f'<td>{r[k]:.6f}</td>' for k in ('original_CI', 'existing_storage_credit',
                             'avoided_gcc_production_emissions', 'avoided_sargassum_decomposition_emissions', 'expanded_CI'))
            parts.append(f'<tr><td>{r["scenario"]}</td><td>{"On" if r["ree_enabled"] else "Off"}</td>{values}</tr>')
        parts.append('</tbody></table>')
    parts += ['</section><section class="card" id="potential-decomposition"><h2>Potential additional beach-decomposition analysis</h2>',
              '<p><a href="figure_2c_carbon_intensity_with_and_without_decomposition.pdf">Figure 2C: S3 carbon intensity with and without avoided Sargassum decomposition</a></p>',
              '<p>Natural reference: fresh, unprocessed Sargassum decomposes on beaches. '
              f'ATT receives dewatered presscake at {moisture*100:.1f} wt% moisture and applies the literature-derived factor '
              f'{dry_reference["ch4_kg_per_t_dry"]:g} kg CH4/t dry to its actual dry-solids mass, then GWP100 and realization. '
              'Methane potential relates to biodegradable organic matter; moisture only converts reporting units. '
              'Dry-solids conservation through pressing is assumed. Organic losses, biodegradability and field emissions remain uncertain; '
              'this is not a methane measurement from UCLA feedstock or actual beaches. It is outside main CI. Biogenic CO2 has no credit.</p>',
              '<img src="avoided_emissions_ci.png" alt="Main GCC-adjusted CI and potential additional decomposition comparison" style="width:100%;max-width:1100px">',
              '<table><tr><th>Scenario</th><th>REE</th><th>Main without decomposition</th><th>Additional decomposition reduction</th><th>Potential with decomposition</th></tr>']
    for r in potential:
        if r['basis']=='per_kg_h2':
            parts.append(f'<tr><td>{r["scenario"]}</td><td>{"On" if r["ree_enabled"] else "Off"}</td>'
                         f'<td>{r["main_CI"]:.6f}</td><td>{r["avoided_sargassum_decomposition_emissions"]:.6f}</td><td>{r["expanded_CI"]:.6f}</td></tr>')
    parts.append('</table><p>Table units: kg CO2e/kg H2. GWP100 and 0-100% CH4-realization sensitivities are provided in the CSV and S3 PDF.</p>')
    parts.append('<p><a href="avoided_emissions_report.md">Methods, sources, limitations and sensitivity</a> | '
                 '<a href="avoided_emissions_sensitivity.csv">All credit switches and CH4 GWP cases</a></p>')
    for c in data['avoided_emissions']['assumptions'].values():
        parts.append('<p>'+escape(c.get('conversion_assumption', '')+' '+c['limitation'])
                     + ' <a href="'+escape(c['url'], quote=True)+'">'+escape(c['source'])+'</a></p>')
    parts.append('</section>')
    return '<div class="wrap">' + '\n'.join(parts) + '</div>'


def _write_outputs(out, data):
    from biorefineries.ATT.analyses.comprehensive_report import _save_csv
    payload = data['avoided_emissions']
    rows = payload['rows']
    base = reference_rows(data, 'main')
    potential = reference_rows(data, 'potential')
    moisture = next(r['moisture_fraction'] for r in data['functional'] if r['basis']=='per_kg_h2')
    _save_csv(out/'avoided_emissions.csv', base)
    _save_csv(out/'avoided_emissions_sensitivity.csv', rows)
    _save_csv(out/'potential_decomposition.csv', potential)
    (out/'avoided_emissions.json').write_text(json.dumps(payload, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    lines = ['# ATT avoided-emission indicators', '',
             'Main CI includes GCC avoided production and excludes beach-decomposition avoidance. Original CI and existing storage are retained separately. ',
             'Potential CI additionally subtracts assumption-dependent CH4 avoidance; it is not a base result. Biogenic CO2 is informational only.', '',
             'The comprehensive HTML and S3 figures in this folder use current model runs.', '',
             f'Actual modeled wet presscake moisture is {moisture*100:.3f} wt%. Reference wet-basis conversions do not change it.', '']
    for basis, unit in BASIS_LABELS.items():
        lines += [f'## Main results: {unit}', '', '| Scenario | REE | Original CI | Existing storage (already included) | Avoided GCC | Decomposition in main | Main CI |',
                  '|---|---|---:|---:|---:|---:|---:|']
        for r in base:
            if r['basis'] == basis:
                values = ' | '.join(f'{r[k]:.6f}' for k in ('original_CI','existing_storage_credit','avoided_gcc_production_emissions',
                                   'avoided_sargassum_decomposition_emissions','expanded_CI'))
                lines.append(f'| {r["scenario"]} | {"On" if r["ree_enabled"] else "Off"} | {values} |')
        lines.append('')
    lines += ['## Potential additional Sargassum decomposition', '',
              'Counterfactual: Sargassum left on beaches and allowed to decompose. This is additional, potential and assumption-dependent; never the default CI.', '',
              '| Scenario | REE | Basis | Main without decomposition | Additional decomposition reduction | Potential with decomposition |',
              '|---|---|---|---:|---:|---:|']
    for r in potential:
        lines.append(f'| {r["scenario"]} | {"On" if r["ree_enabled"] else "Off"} | {BASIS_LABELS[r["basis"]]} | '
                     f'{r["main_CI"]:.6f} | {r["avoided_sargassum_decomposition_emissions"]:.6f} | {r["expanded_CI"]:.6f} |')
    lines += ['## Active configuration', '',
              '| Indicator | Enabled in configured case | Active factor |', '|---|---|---|']
    g = payload['assumptions']['avoided_gcc_production_emissions']
    d = payload['assumptions']['avoided_sargassum_decomposition_emissions']
    dry_reference = decomposition_emissions_dry(1000.)
    presscake_reference = decomposition_emissions_dry(1000.*(1.-moisture))
    lines += [f'| Avoided GCC | {g["enabled"]} | {g["emission_factor"]:g} {g["unit"]} |',
              f'| Avoided decomposition | {d["enabled"]} | {dry_reference["ch4_kg_per_t_dry"]:g} kg CH4/t dry; CH4 GWP100 = {d["ch4_gwp100"]:g} |', '',
              f'Published fresh-reference moisture: {d["reference_raw_moisture_fraction"]:.6%}. '
              'The dry-solids factor is derived from the existing weighted wet factor divided by the literature solids fraction, '
              'not from rounded species-specific dry factors. Avoided CO2e = actual dry tonnes x dry CH4 factor x GWP100 x realization.', '',
              '| Active mixture species | Mass fraction | CH4 g/kg wet raw | CO2 g/kg wet raw |',
              '|---|---:|---:|---:|']
    for name, species in d['species'].items():
        lines.append(f'| {name} | {species["mass_fraction"]:g} | {species["CH4"]:g} | {species["CO2"]:g} |')
    active = decomposition_emissions(1., ch4_gwp100=d['ch4_gwp100'])
    lines += ['', f'Active weighted CH4 factor: {active["weighted_ch4_g_per_kg_raw"]:g} g/kg wet raw; '
              f'active weighted CO2 factor: {active["weighted_co2_g_per_kg_raw"]:g} g/kg wet raw. '
              f'Derived primary CH4 factor: {dry_reference["ch4_kg_per_t_dry"]:g} kg CH4/t dry.', '',
              'Complete configuration, per-species source values and references are recorded in avoided_emissions.json.', '',
              '## Published source factors and reference checks', '',
              'The following values document the requested reference case; the active configuration above governs the generated tables.', '',
              'Published GCC reference: 12.5 kg CO2e per declared 1000 kg = 0.0125 kg CO2e/kg pure CaCO3, GWP-total, A1-A3. '
              '[Lafarge Granulats (2026), EPD-IES-0031144:001](https://www.environdec.com/library/epd31144). '
              'Only the CaCO3 component of the two final product cakes is multiplied; purity is not applied again.', '',
              'Brazilian mixture: 50% S. fluitans + 15% S. natans I + 35% S. natans VIII. '
              'Table 3 wet-basis CH4 values are 7.02, 4.37, 10.1 g/kg; CO2 values are 20.4, 12.2, 31.7 g/kg. '
              'Weighted CH4 = 7.7005 g/kg and CO2 = 23.125 g/kg raw wet Sargassum. '
              '[Bueno et al. (2023), Tables 2-3 and section 3.2](https://doi.org/10.3390/su15076254). '
              'Reference moisture is 87.5%. Reference GWP100 is the user-requested 28; '
              '25.3 is the optional non-fossil CH4 sensitivity from '
              '[IPCC AR6 WGI errata, 7 October 2025, p. 3, Table 7.15](https://www.ipcc.ch/report/ar6/wg1/downloads/report/IPCC_AR6_WGI_Errata.pdf). '
              'Baseline emission factors are not re-characterized.', '',
              'Reference check: one tonne raw wet mixture gives 7.7005 kg CH4, 215.614 kg CO2e at 28, '
              '194.82265 kg CO2e at 25.3, and 23.125 kg biogenic CO2 reported separately.', '',
              f'Dry-solids reference check at GWP100 = {dry_reference["ch4_gwp100"]:g}: one tonne dry gives '
              f'{dry_reference["avoided_ch4_kg"]:.6f} kg CH4 and {dry_reference["avoided_co2e_kg"]:.6f} kg CO2e; '
              f'one tonne presscake at {moisture*100:.1f} wt% moisture gives {presscake_reference["avoided_ch4_kg"]:.6f} kg CH4 '
              f'and {presscake_reference["avoided_co2e_kg"]:.6f} kg CO2e.', '',
              'Natural reference: fresh, unprocessed Sargassum is deposited on beaches and decomposes. ATT receives dewatered presscake. '
              'The calculation applies the normalized dry-solids factor to actual feed dry mass. Methane potential follows biodegradable '
              'organic matter, not water content itself: holding dry solids and biodegradability constant preserves total potential. '
              'Moisture converts functional units only. Fresh-mass equivalence remains optional reporting information. '
              'The reference-scale press-retention configuration is not a validated upstream pressing balance. '
              'The factor is not measured methane from the UCLA feedstock or actual beaches. Actual feed water, CaCO3 and H2 '
              'are read from the model; total gas mass is not used as H2.', '',
              '## Limitations and double counting', '']
    for c in payload['assumptions'].values():
        if c.get('conversion_assumption'):
            lines += [c['conversion_assumption'], '']
        lines += [c['limitation'], '']
    lines += ['Existing carbonate/char storage is shown as a negative credit already inside original CI. '
              'It is neither recalculated as a new credit nor subtracted again. The separate legacy IPCC beach-rot '
              'estimate is retained for backward compatibility and excluded from expanded CI. These are screening '
              'counterfactuals, not a validated consequential LCA; the storage and avoided-decomposition claims '
              'need compatible carbon-fate and counterfactual evidence.', '',
              '## Sensitivity: kg CO2e/kg H2', '',
              'Illustrative 0%, 10%, 50% and 100% realization of semi-empirical CH4 avoidance explores lower or variable emissions. '
              'These are screening fractions, not a measured confidence interval.', '',
              '| Scenario | REE | CH4 GWP100 | Realization fraction | Potential CI |', '|---|---|---:|---:|---:|']
    for r in rows:
        if r['basis']=='per_kg_h2' and r['credit_case']=='potential':
            lines.append(f'| {r["scenario"]} | {"On" if r["ree_enabled"] else "Off"} | {r["ch4_gwp100"]:g} | {r["decomposition_fraction"]:g} | {r["expanded_CI"]:.6f} |')
    lines += ['', 'The sensitivity CSV includes original-only, GCC-only and decomposition-only cases on both functional units.', '',
              '## Reproduce', '', 'From the repository root:', '',
              '```text', 'python -m biorefineries.ATT.analyses.avoided_emissions', '```', '',
              'Configure the two independent enabled switches and factors in data/lca.yaml: lca.avoided_emissions. '
              'No factors are registered on the BioSTEAM system. All artifacts from this command stay in '
              'results/avoided_emissions/, which is covered by the existing results Git-ignore rule.', '']
    (out/'avoided_emissions_report.md').write_text('\n'.join(lines), encoding='utf-8')
    _figure(out, base, potential, moisture)


def _figure(out, rows, potential, moisture):
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
    dry_reference = decomposition_emissions_dry(1000.)
    fig.text(.07,.06,f'Potential beach decomposition (Bueno et al. 2023): {dry_reference["ch4_kg_per_t_dry"]:g} kg CH4/t dry, derived from 7.7005 kg/t fresh at 87.5 wt% moisture.\n'
             f'ATT uses actual presscake dry solids (current moisture {moisture*100:.1f} wt%). Moisture converts units; water alone does not change methane potential.\n'
             'Dry-solids conservation is assumed; organic losses, biodegradability and beach CH4 are uncertain. Not UCLA measurements; biogenic CO2 is excluded.\n'
             'GWP100 = 25.3 and 0-100% realization sensitivities are separate analyses. GCC (0.0125 kg CO2e/kg pure CaCO3) remains in both versions.',fontsize=8.5)
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
