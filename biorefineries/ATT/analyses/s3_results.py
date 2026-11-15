"""Export independent S3 results and current S1/S2/S3 comparisons.

Default output: results/s3_results (git-ignored; regenerated in place).
"""
import argparse
import csv
import json
import math
from pathlib import Path


def _clean(value):
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _csv(path, rows, columns):
    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def write_outputs(output_dir, cases, comparison):
    """Write complete case results and tables in a new, non-existing directory."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    document = _clean(dict(cases=cases, scenario_comparison=comparison))
    with (out / 'results.json').open('w', encoding='utf-8') as f:
        json.dump(document, f, indent=2, allow_nan=False, default=float)
        f.write('\n')
    summary_keys = ['ree_enabled', 'operating_hours_per_year', 'h2_kg_per_hour', 'boundary_flows_unchanged',
                    'available_kW', 'feasible_overlap_kW', 'source_extracted_overlap_kW', 'transfer_loss_overlap_kW',
                    'useful_steam_overlap_kW', 'used_average_kW', 'unused_overlap_kW', 'baseline_steam_kW',
                    'remaining_steam_average_kW', 'remaining_fired_heating_kW', 'heating_before_kW',
                    'heating_after_average_kW', 'avoided_boiler_fuel_average_kW', 'recovered_MWh_per_year',
                    'recovered_GJ_per_year', 'auxiliary_average_kW', 'incremental_capex_usd',
                    'incremental_foc_usd_per_year', 'auxiliary_electricity_cost_usd_per_year',
                    'heat_purchase_cost_usd_per_year', 'avoided_cost_usd_per_year', 's3_FCI_usd',
                    's3_net_AOC_usd_per_year', 's3_MSP_usd_per_kg_H2', 'MSP_change_usd_per_kg_H2',
                    'avoided_emissions_kg_per_hour', 'auxiliary_emissions_kg_per_hour', 'heat_burden_kg_per_hour',
                    's3_GWP_kg_per_kg_H2', 'GWP_change_kg_per_kg_H2', 'hxn_energy_balance_percent_error']
    summaries = [dict(c, s1_MSP_USD_per_kg_H2=c['s1']['MSP_USD_per_kg_H2'],
                      s1_GWP_kg_per_kg_H2=c['s1']['GWP_kgCO2e_per_kg_H2'],
                      mass_in_kg_per_h=c['mass_audit']['mass_in_kgph'],
                      mass_out_kg_per_h=c['mass_audit']['mass_out_kgph'],
                      mass_relative_error=c['mass_audit']['mass_relative_error']) for c in cases]
    _csv(out / 'summary.csv', summaries, summary_keys + ['s1_MSP_USD_per_kg_H2', 's1_GWP_kg_per_kg_H2',
         'mass_in_kg_per_h', 'mass_out_kg_per_h', 'mass_relative_error'])
    _csv(out / 'heat_sources.csv', [dict(row, ree_enabled=c['ree_enabled']) for c in cases for row in c['source_details']],
         ['ree_enabled', 'source', 'available_kW', 'temperature_feasible_kW', 'extracted_kW', 'loss_kW', 'steam_kW', 'unused_kW'])
    _csv(out / 'heat_allocations.csv', [dict(row, ree_enabled=c['ree_enabled']) for c in cases for row in c['allocations']],
         ['ree_enabled', 'source', 'unit', 'extracted_kW', 'used_kW', 'interval_bottom_C', 'sink_temperature_C'])
    _csv(out / 'process_products.csv', [dict(flow, ree_enabled=c['ree_enabled'], stream=key)
         for c in cases for key, flow in c['product_flows'].items()],
         ['ree_enabled', 'stream', 'mass_kg_per_h', 'H2_kg_per_h', 'CaCO3_kg_per_h', 'REO_kg_per_h'])
    _csv(out / 'scenario_comparison.csv', comparison,
         ['ree_enabled', 'scenario', 'operating_hours_per_year', 'H2_kg_per_h', 'FCI_USD',
          'MSP_USD_per_kg_H2', 'GWP_kgCO2e_per_kg_H2', 'note'])
    return out


def run_comparison(**config):
    """Calculate S3 and S2 on each matching REE configuration in this runtime."""
    from biorefineries.ATT.analyses import scenarios, marine_tea
    from biorefineries.ATT.analyses.s3_industrial import run
    cases, comparison = [], []
    for enabled in (True, False):
        c = run(enable_ree_recovery=enabled, **config)
        cases.append(c)
        common = dict(ree_enabled=enabled, H2_kg_per_h=c['h2_kg_per_hour'])
        comparison.append(dict(common, scenario='S1', operating_hours_per_year=c['operating_hours_per_year'],
            FCI_USD=c['s1']['FCI_MUSD']*1e6, MSP_USD_per_kg_H2=c['s1']['MSP_USD_per_kg_H2'],
            GWP_kgCO2e_per_kg_H2=c['s1']['GWP_kgCO2e_per_kg_H2'], note='Land baseline'))
        system = scenarios.create(scenarios.ATT_S2, ree_recovery=enabled)
        ref = marine_tea.s1_reference(system)
        _, hours, load = marine_tea.operating_mode()
        row, _ = marine_tea.evaluate_case(system, ref, 'S2 with marine WHR',
                    sources=('jacket', 'scavenge', 'exhaust'), hours=hours, load=load)
        comparison.append(dict(common, scenario='S2', operating_hours_per_year=hours, FCI_USD=row['FCI_USD'],
            H2_kg_per_h=row['H2_t_per_yr']*1000/hours,
            MSP_USD_per_kg_H2=row['MSP_USD_per_kg_H2'], GWP_kgCO2e_per_kg_H2=row['GWP_kgCO2e_per_kg_H2'],
            note='Marine accounting; inherited U3D sink inventory issue'))
        comparison.append(dict(common, scenario='S3', operating_hours_per_year=c['operating_hours_per_year'],
            FCI_USD=c['s3_FCI_usd'], MSP_USD_per_kg_H2=c['s3_MSP_usd_per_kg_H2'],
            GWP_kgCO2e_per_kg_H2=c['s3_GWP_kg_per_kg_H2'], note='Preliminary land-based LP steam screen'))
    return cases, comparison


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, help='output directory (default: results/s3_results)')
    parser.add_argument('--reference-hours', type=float, default=7920.)
    parser.add_argument('--host-hours', type=float, default=7920.)
    parser.add_argument('--utilization', type=float, default=1.)
    parser.add_argument('--approach-C', type=float, default=20.)
    parser.add_argument('--effectiveness', type=float, default=.9)
    parser.add_argument('--installed-cost-usd-per-kW', type=float, default=500.)
    parser.add_argument('--auxiliary-kW-per-kW', type=float, default=.01)
    parser.add_argument('--heat-price-usd-per-MWh', type=float, default=0.)
    parser.add_argument('--heat-burden-kg-per-MWh', type=float, default=0.)
    options = vars(parser.parse_args())
    out = options.pop('out')
    if out is None:
        from biorefineries.ATT.analyses.paths import output_dir
        out = output_dir('s3_results')
    cases, comparison = run_comparison(**options)
    print('Saved S3 results to', write_outputs(out, cases, comparison).resolve())


if __name__ == '__main__':
    main()
