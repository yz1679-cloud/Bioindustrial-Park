"""Run a READ-ONLY ATT heating/cooling audit and pinch targets.

Execute from repository root::

    python -m biorefineries.sabre.test.run_att_heat_integration
    python -m biorefineries.sabre.test.run_att_heat_integration --delta-t-min 5 --json-out att_heat_report.json

IMPORTANT: No process heat recovery is installed or credited by this tool.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, is_dataclass
import json
from pathlib import Path


def _to_json(value):
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return {k: _to_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_json(v) for v in value]
    return value


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dry-feed-kgph', type=float, default=1.0,
                   help='Dry Sargassum model basis [kg/h]; default 1.0')
    p.add_argument('--delta-t-min', type=float, default=10.0,
                   help='Minimum temperature approach in K; default 10')
    p.add_argument('--screen-isothermal', action='store_true',
                   help='Treat D0 and EC1 duties as isothermal for an UNVALIDATED screening scenario')
    p.add_argument('--ec1-temperature-K', type=float, default=None,
                   help='EC1 OPTIMIZATION SCENARIO temperature; default = 90 C baseline')
    p.add_argument('--hen', action='store_true',
                   help='Design and verify the heat-exchanger network for each dryer option')
    p.add_argument('--json-out', type=Path, default=None,
                   help='Optional output path for model-derived audit and screening; default no file')
    args = p.parse_args(argv)
    if args.dry_feed_kgph <= 0:
        p.error('--dry-feed-kgph must be positive')
    if args.delta_t_min < 0:
        p.error('--delta-t-min must be nonnegative')

    from biorefineries.sabre.systems._att_system import create_att_system
    from biorefineries.sabre.analyses.att.heat_integration import (
        get_heat_utility_audit, format_heat_utility_audit,
        get_att_heat_recovery_assessment, format_att_heat_recovery_assessment,
        get_att_pinch_targets, design_att_heat_exchanger_network,
        format_att_heat_exchanger_network,
    )

    sys = create_att_system(dry_sargassum_kgph=args.dry_feed_kgph,
                            ec1_temperature_K=args.ec1_temperature_K)
    sys.set_tolerance(mol=1e-11, rmol=1e-11, T=1e-5, rT=1e-5,
                      maxiter=300, method='fixedpoint')
    # Full simulation intentionally: otherwise native equipment HUs can be zero.
    sys.simulate()

    audit = get_heat_utility_audit(sys)
    assessment = get_att_heat_recovery_assessment(
        sys, delta_T_min_K=args.delta_t_min,
        assume_isothermal_d0_ec1=args.screen_isothermal,
    )
    print(format_heat_utility_audit(audit))
    print()
    print(format_att_heat_recovery_assessment(assessment))
    targets = get_att_pinch_targets(sys, args.delta_t_min)
    print()
    print('=== PHASE-RESOLVED PINCH TARGETS (U3HX VLE, RC1, EC1 electrolyte model) ===')
    print(f"dTmin = {targets['delta_T_min_K']:.1f} K; integrated cold units: {', '.join(targets['integrated_cold_units'])}")
    print(f"Heating now: {targets['integrated_heating_now_kJph']:,.1f} kJ/h; recoverable: {targets['recoverable_kJph']:,.1f}; "
          f"minimum external heating: {targets['minimum_hot_utility_kJph']:,.1f}; minimum cooling: {targets['minimum_cold_utility_kJph']:,.1f}")
    if targets['pinch_shifted_temperature_K'] is not None:
        print(f"Pinch (shifted): {targets['pinch_shifted_temperature_K'] - 273.15:.1f} C")

    designs = {}
    if args.hen:
        total_heating = audit['summary']['total_heating_kJph']
        total_cooling = audit['summary']['total_cooling_kJph']
        print()
        print(f'Plant external heating / cooling WITHOUT recovery (as simulated): '
              f'{total_heating:,.1f} / {total_cooling:,.1f} kJ/h')
        for dryer in (None, 'belt_hot_air'):
            design = design_att_heat_exchanger_network(sys, dryer, args.delta_t_min)
            designs[str(dryer)] = design
            print()
            print(format_att_heat_exchanger_network(design))
            label = ("credited in the heat_integration=True scenario" if dryer is None
                     else "EVALUATION ONLY, includes unverified dryer-dependent recovery")
            print(f"  Plant external heating / cooling with this network ({label}): "
                  f"{total_heating - design['recovered_kJph']:,.1f} / "
                  f"{total_cooling - design['recovered_kJph']:,.1f} kJ/h")

    if args.json_out is not None:
        data = {
            'dry_feed_kgph': args.dry_feed_kgph,
            'delta_T_min_K': args.delta_t_min,
            'heat_utility_audit': audit,
            'heat_recovery_screening': assessment,
            'pinch_targets': targets,
            'hen_designs': designs,
        }
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(_to_json(data), indent=2), encoding='utf-8')
        print(f'\nReport written to: {args.json_out}')
    if assessment['unregistered_custom_thermal_duties']:
        print('\nWARNING: C1 custom reaction duty does not match BioSTEAM heat utilities; '
              'baseline utility totals require review.')
    print('IMPORTANT: No HEN was installed; recovered utility credit remains 0 kJ/h.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
