"""Steps 7.7-7.8A: deterministic functional tests and full utility auditing.

Place at biorefineries/sabre/test_att_heat_integration.py.
From repository root run: python -m biorefineries.sabre.test_att_heat_integration
Optional real BioSTEAM integration smoke test:
    $env:ATT_RUN_REAL_SYSTEM_TEST='1'
    python -m biorefineries.sabre.test_att_heat_integration

The default tests use small controlled stand-ins; they do not alter the flowsheet.
"""
from __future__ import annotations

import importlib
import inspect
import math
import os
from pathlib import Path
from types import SimpleNamespace
import unittest

MODULE_NAME = 'biorefineries.sabre.analyses._att_heat_integration'


def stream(T, H):
    return SimpleNamespace(T=T, H=H)


def unit(ID, ins=(), outs=(), duties=()):
    return SimpleNamespace(ID=ID, ins=list(ins), outs=list(outs),
                           heat_utilities=[SimpleNamespace(duty=q) for q in duties])


def fixture_system():
    # Artificial inputs for verifying arithmetic, NOT measured ATT operating data.
    units = SimpleNamespace(
        U3HX=unit('U3HX', [stream(800, 15000)], [stream(380, 9000)], [-6000]),
        RC1=unit('RC1', [stream(750, 8000)], [stream(365, 5000)], [-3000]),
        D0=unit('D0', [stream(300, 0)], [stream(390, 0)], [1000, -250]),
        U2=unit('U2', [stream(340, 0)], [stream(800, 0)], [2400]),
        C1=unit('C1', [stream(340, 0), stream(345, 0)], [stream(363, 0)], [800]),
        EC1=unit('EC1', [stream(350, 0)], [stream(370, 0), stream(370, 0)], [3000, -2700]),
        U3D=unit('U3D', [stream(300, 0)], [stream(310, 0)], [-50]),
    )
    return SimpleNamespace(flowsheet=SimpleNamespace(unit=units))


class TestATTHeatIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = importlib.import_module(MODULE_NAME)

    # Preserve the original three structural checks.
    def test_module_imported_from_analyses(self):
        self.assertEqual(self.mod.__name__, MODULE_NAME)
        self.assertEqual(Path(self.mod.__file__).name, '_att_heat_integration.py')

    def test_public_functions_have_valid_signatures(self):
        functions = {n: f for n, f in vars(self.mod).items()
                     if inspect.isfunction(f) and f.__module__ == MODULE_NAME
                     and not n.startswith('_')}
        self.assertTrue(functions)
        for name, func in functions.items():
            with self.subTest(function=name):
                self.assertIsInstance(inspect.signature(func), inspect.Signature)

    def test_heat_analysis_function_categories(self):
        for name in ('get_hot_streams', 'get_cold_streams',
                     'get_heat_duty_summary', 'check_temperature_feasibility',
                     'build_temperature_feasibility_matrix'):
            with self.subTest(api=name):
                self.assertTrue(callable(getattr(self.mod, name, None)))

    def test_heatstream_kw_conversion(self):
        s = self.mod.HeatStream('sample', 'T1', 'hot', 7200, 400, 350)
        self.assertEqual(s.duty_kW, 2.0)
        self.assertTrue(s.include_in_matching)

    def test_hot_duty_is_enthalpy_drop_and_clamped(self):
        sys = fixture_system()
        hot = {s.unit_id: s for s in self.mod.get_hot_streams(sys)}
        self.assertEqual(set(hot), {'U3HX', 'RC1'})
        self.assertEqual(hot['U3HX'].duty_kJph, 6000)
        self.assertEqual(hot['RC1'].duty_kJph, 3000)
        self.assertTrue(all(s.kind == 'hot' for s in hot.values()))
        self.assertEqual(hot['U3HX'].T_in_K, 800)
        self.assertEqual(hot['RC1'].T_out_K, 365)
        sys.flowsheet.unit.RC1.outs[0].H = 10000
        hot = {s.unit_id: s for s in self.mod.get_hot_streams(sys)}
        self.assertEqual(hot['RC1'].duty_kJph, 0)

    def test_enthalpy_drop_rejects_non_one_to_one_unit(self):
        with self.assertRaises(ValueError):
            self.mod._process_enthalpy_drop_kJph(unit('bad', [stream(300, 10), stream(300, 2)], [stream(300, 0)]))

    def test_cold_duties_only_sum_positive_utilities(self):
        cold = {s.unit_id: s for s in self.mod.get_cold_streams(fixture_system())}
        self.assertEqual(set(cold), {'D0', 'U2', 'C1', 'EC1', 'U3D'})
        self.assertEqual({k: v.duty_kJph for k, v in cold.items()},
                         {'D0': 1000, 'U2': 2400, 'C1': 800, 'EC1': 3000, 'U3D': 0})
        self.assertFalse(cold['U3D'].include_in_matching)
        self.assertIsNone(cold['C1'].T_in_K)  # multi-inlet: do not invent temperature
        self.assertIsNone(cold['EC1'].T_out_K)  # multi-outlet: do not invent temperature
        self.assertTrue(all(s.kind == 'cold' for s in cold.values()))

    def test_duty_summary_excludes_unmatched_and_converts_units(self):
        summary = self.mod.get_heat_duty_summary(fixture_system())
        self.assertEqual(summary['gross_hot_available_kJph'], 9000)
        self.assertEqual(summary['gross_cold_demand_kJph'], 7200)
        self.assertAlmostEqual(summary['gross_hot_available_kW'], 2.5)
        self.assertAlmostEqual(summary['gross_cold_demand_kW'], 2)
        self.assertEqual(len(summary['hot_streams']), 2)
        self.assertEqual(len(summary['cold_streams']), 5)

    def make_pair(self, hi=500, ho=360, ci=300, co=450):
        return (self.mod.HeatStream('H', 'H', 'hot', 1000, hi, ho),
                self.mod.HeatStream('C', 'C', 'cold', 500, ci, co))

    def test_temperature_feasible_and_approaches(self):
        result = self.mod.check_temperature_feasibility(*self.make_pair(), delta_T_min_K=10)
        self.assertEqual(result['status'], 'FEASIBLE')
        self.assertIs(result['feasible'], True)
        self.assertEqual(result['hot_end_approach_K'], 50)
        self.assertEqual(result['cold_end_approach_K'], 60)

    def test_temperature_not_feasible_and_boundary(self):
        h, c = self.make_pair(hi=459, ho=360, ci=300, co=450)
        self.assertEqual(self.mod.check_temperature_feasibility(h, c, 10)['status'], 'NOT_FEASIBLE')
        h.T_in_K = 460  # exact ΔTmin at hot end should pass
        self.assertEqual(self.mod.check_temperature_feasibility(h, c, 10)['status'], 'FEASIBLE')
        h.T_out_K = 309  # fails at the cold end
        self.assertEqual(self.mod.check_temperature_feasibility(h, c, 10)['status'], 'NOT_FEASIBLE')

    def test_missing_temperature_returns_unknown(self):
        h, c = self.make_pair()
        c.T_in_K = None
        result = self.mod.check_temperature_feasibility(h, c)
        self.assertIsNone(result['feasible'])
        self.assertEqual(result['status'], 'INSUFFICIENT_TEMPERATURE_DATA')

    def test_invalid_hot_or_cold_kind_is_rejected(self):
        h, c = self.make_pair()
        h.kind = 'cold'
        with self.assertRaises(ValueError):
            self.mod.check_temperature_feasibility(h, c)
        h.kind = 'hot'
        c.kind = 'hot'
        with self.assertRaises(ValueError):
            self.mod.check_temperature_feasibility(h, c)

    def test_matrix_shape_and_unknown_temperature(self):
        rows = self.mod.build_temperature_feasibility_matrix(fixture_system(), 10)
        self.assertEqual(len(rows), 8)  # 2 eligible hot × 4 eligible cold
        self.assertEqual({r['hot_stream'] for r in rows}, {'U2 hot gas/steam cooling', 'ATT residue cooling'})
        self.assertTrue(any(r['status'] == 'INSUFFICIENT_TEMPERATURE_DATA' for r in rows))
        self.assertTrue(all(r['delta_T_min_K'] == 10 for r in rows))

    # Step 7.8A: full-system utility audit (separate heating and cooling).
    def test_audit_captures_simultaneous_positive_and_negative_utilities(self):
        audit = self.mod.get_heat_utility_audit(fixture_system())
        by_unit = {r['unit_id']: r for r in audit['units']}
        self.assertEqual(len(by_unit), 7)
        self.assertEqual(by_unit['EC1']['heating_kJph'], 3000)
        self.assertEqual(by_unit['EC1']['cooling_kJph'], 2700)
        self.assertEqual(by_unit['EC1']['net_utility_kJph'], 300)
        ec1_duties = [r['duty_kJph'] for r in audit['utilities']
                      if r['unit_id'] == 'EC1']
        self.assertEqual(ec1_duties, [3000, -2700])
        self.assertEqual(audit['summary']['total_heating_kJph'], 7200)
        self.assertEqual(audit['summary']['total_cooling_kJph'], 12000)
        self.assertEqual(audit['summary']['net_utility_kJph'], -4800)
        self.assertEqual(audit['summary']['total_heating_kW'], 2)
        self.assertEqual(audit['summary']['mixed_duty_unit_ids'], ['D0', 'EC1'])

    def test_audit_unmatched_cooling_is_not_counted_as_hot_candidate(self):
        audit = self.mod.get_heat_utility_audit(fixture_system())
        s = audit['summary']
        self.assertEqual(s['explicit_hot_candidate_cooling_kJph'], 9000)
        self.assertEqual(s['additional_cooling_requires_review_kJph'], 3000)
        labels = {(r['unit_id'], r['direction']): r['classification']
                  for r in audit['utilities']}
        self.assertEqual(labels[('EC1', 'cooling')], 'CONDENSER_REVIEW_REQUIRED')
        self.assertEqual(labels[('U3D', 'cooling')], 'PROVISIONAL_NATIVE_MODEL')
        self.assertEqual(labels[('RC1', 'cooling')], 'EXPLICIT_HOT_STREAM_CANDIDATE')
        self.assertEqual(s['selected_cold_heating_kJph'], 7200)

    def test_audit_includes_other_system_units_and_zero_duty(self):
        sys = fixture_system()
        units = list(vars(sys.flowsheet.unit).values())
        extra = unit('EXTRA', [stream(330, 0)], [stream(360, 0)], [80, -20])
        empty = unit('NO_HU')
        sys.units = units + [extra, empty]
        audit = self.mod.get_heat_utility_audit(sys)
        self.assertEqual(len(audit['units']), 9)
        other = {r['unit_id']: r for r in audit['units']}
        self.assertEqual(other['NO_HU']['heat_utility_count'], 0)
        self.assertEqual(other['EXTRA']['heating_kJph'], 80)
        self.assertEqual(other['EXTRA']['cooling_kJph'], 20)
        self.assertEqual(audit['summary']['total_heating_kJph'], 7280)
        self.assertEqual(audit['summary']['total_cooling_kJph'], 12020)
        self.assertEqual(audit['summary']['additional_heating_requires_review_kJph'], 80)

    def test_audit_deduplicates_repeated_unit_and_utility_objects(self):
        sys = fixture_system()
        shared = SimpleNamespace(duty=-100)
        u1 = unit('X1', duties=[])
        u2 = unit('X2', duties=[])
        u1.heat_utilities = [shared]
        u2.heat_utilities = [shared]
        sys.units = [u1, u1, u2]
        audit = self.mod.get_heat_utility_audit(sys)
        self.assertEqual(len(audit['units']), 2)
        self.assertEqual(audit['summary']['total_cooling_kJph'], 100)
        self.assertEqual(len(audit['warnings']), 1)

    def test_audit_rejects_invalid_duty_and_format_report(self):
        sys = fixture_system()
        sys.flowsheet.unit.EC1.heat_utilities[0].duty = float('nan')
        with self.assertRaisesRegex(ValueError, 'Non-finite'):
            self.mod.get_heat_utility_audit(sys)
        report = self.mod.format_heat_utility_audit(
            self.mod.get_heat_utility_audit(fixture_system()))
        self.assertIn('EC1', report)
        self.assertIn('CONDENSER_REVIEW_REQUIRED', report)
        self.assertIn('TOTAL external cooling utilities', report)

    @unittest.skipUnless(os.getenv('ATT_RUN_REAL_SYSTEM_TEST') == '1',
                         'Set ATT_RUN_REAL_SYSTEM_TEST=1 to run real BioSTEAM model')
    def test_real_biosteam_flowsheet_smoke(self):
        from biorefineries.sabre.systems._att_system import create_att_system
        sys = create_att_system(dry_sargassum_kgph=1.0)
        sys.set_tolerance(mol=1e-9, rmol=1e-9, T=1e-5, rT=1e-5,
                          maxiter=200, method='fixedpoint')
        # Full BioSTEAM simulation generates equipment heat utilities.
        sys.simulate()
        result = self.mod.get_heat_duty_summary(sys)
        print("\n=== REAL ATT HEAT DIAGNOSTICS ===")
        for item in result['hot_streams'] + result['cold_streams']:
            unit_obj = getattr(sys.flowsheet.unit, item.unit_id)
            utilities = [float(hu.duty) for hu in unit_obj.heat_utilities]
            print(f"{item.kind} {item.unit_id}: duty={item.duty_kJph:.6g} kJ/h, "
                  f"heat_utilities={utilities}, "
                  f"Tin={item.T_in_K}, Tout={item.T_out_K}")
        print("Gross hot (kJ/h):", result['gross_hot_available_kJph'])
        print("Gross cold (kJ/h):", result['gross_cold_demand_kJph'])
        self.assertEqual({s.unit_id for s in result['hot_streams']}, {'U3HX', 'RC1'})
        self.assertEqual({s.unit_id for s in result['cold_streams']},
                         {'D0', 'U2', 'C1', 'EC1', 'U3D'})
        for s in result['hot_streams'] + result['cold_streams']:
            self.assertTrue(math.isfinite(s.duty_kJph))
            self.assertGreaterEqual(s.duty_kJph, 0)
        self.assertGreater(result['gross_hot_available_kJph'], 0)
        self.assertGreater(
            result['gross_cold_demand_kJph'], 0,
            "Cold demand remains zero after full simulation; inspect diagnostics."
        )
        audit = self.mod.get_heat_utility_audit(sys)
        print('\n' + self.mod.format_heat_utility_audit(audit))
        unit_audit = {r['unit_id']: r for r in audit['units']}
        self.assertIn('EC1', unit_audit)
        self.assertGreater(audit['summary']['total_heating_kJph'], 0)
        self.assertGreater(audit['summary']['total_cooling_kJph'], 0)
        self.assertGreaterEqual(audit['summary']['total_heating_kJph'],
                                result['gross_cold_demand_kJph'] - 1e-6)
        self.assertGreaterEqual(audit['summary']['total_cooling_kJph'],
                                result['gross_hot_available_kJph'] - 1e-6)
        for hot in result['hot_streams']:
            # U3HX and RC1 have simple 1-in/1-out HXutility duties.
            self.assertTrue(math.isclose(unit_audit[hot.unit_id]['cooling_kJph'],
                                         hot.duty_kJph, rel_tol=1e-6, abs_tol=1e-4))
        if unit_audit['EC1']['cooling_kJph'] > 0:
            self.assertTrue(any(r['unit_id'] == 'EC1' and
                                r['classification'] == 'CONDENSER_REVIEW_REQUIRED'
                                for r in audit['utilities']))
        assessment = self.mod.get_att_heat_recovery_assessment(sys)
        print('\n' + self.mod.format_att_heat_recovery_assessment(assessment))
        screening = self.mod.get_att_heat_recovery_assessment(sys, assume_isothermal_d0_ec1=True)
        print('\n' + self.mod.format_att_heat_recovery_assessment(screening))
        self.assertEqual(screening['credited_recovery_kJph'], 0.0)
        if os.getenv('ATT_REQUIRE_C1_UTILITY_MATCH') == '1':
            self.assertFalse(screening['unregistered_custom_thermal_duties'],
                             'C1 custom calculated thermal duty does not reconcile with utilities. ' +
                             str(screening['unregistered_custom_thermal_duties']))
        self.assertLessEqual(screening['conditional_ideal_recovery_kJph'],
                             screening['arithmetic_hot_cold_upper_bound_kJph'] + 1e-6)
        matrix = self.mod.build_temperature_feasibility_matrix(sys)
        self.assertTrue(matrix)
        self.assertTrue(all(row['status'] in ('FEASIBLE', 'NOT_FEASIBLE',
                                               'INSUFFICIENT_TEMPERATURE_DATA') for row in matrix))




class TestATTHeatCascade(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = importlib.import_module(MODULE_NAME)

    def seg(self, ID, kind, t0, t1, q):
        return self.mod.HeatInterval(ID, kind, t0, t1, q)

    def test_empty_temperature_cascade_gives_zero(self):
        result = self.mod.calculate_temperature_cascade(())
        self.assertEqual(result['ideal_recovery_kJph'], 0)
        self.assertEqual(result['minimum_hot_utility_kJph'], 0)

    def test_equal_temperature_latent_plus_sensible(self):
        # Hot 500 -> 350 with Q=100, latent cold Q=80 at T=400.
        # At dT=10, hot must remain >=410 K. Its available Q is 60.
        h = self.seg('H', 'hot', 500, 350, 100)
        c = self.seg('C', 'cold', 400, 400, 80)
        r = self.mod.calculate_temperature_cascade((h,c), 10)
        self.assertAlmostEqual(r['ideal_recovery_kJph'], 60)
        self.assertAlmostEqual(r['minimum_hot_utility_kJph'], 20)
        self.assertAlmostEqual(r['minimum_cold_utility_kJph'], 40)
        self.assertLess(r['energy_closure_kJph'], 1e-7)

    def test_nonoverlapping_temperature_has_no_recovery(self):
        h = self.seg('H','hot',350,300,100)
        c = self.seg('C','cold',400,450,80)
        r = self.mod.calculate_temperature_cascade((h,c),10)
        self.assertEqual(r['ideal_recovery_kJph'], 0)
        self.assertEqual(r['minimum_hot_utility_kJph'], 80)
        self.assertEqual(r['minimum_cold_utility_kJph'], 100)

    def test_duty_is_never_created_by_cascade(self):
        # No cold load, so no process heat recovery regardless of hot supply.
        r=self.mod.calculate_temperature_cascade((self.seg('H','hot',600,300,55),))
        self.assertEqual(r['ideal_recovery_kJph'],0)
        self.assertEqual(r['minimum_cold_utility_kJph'],55)

    def test_tighter_approach_does_not_improve_heat_recovery(self):
        ints=(self.seg('H','hot',500,350,100),
              self.seg('C','cold',400,400,80))
        r1=self.mod.calculate_temperature_cascade(ints,10)
        r2=self.mod.calculate_temperature_cascade(ints,30)
        self.assertLessEqual(r2['ideal_recovery_kJph'], r1['ideal_recovery_kJph'])

    def test_invalid_profiles_rejected(self):
        cases=(self.seg('H','hot',310,380,10),
               self.seg('C','cold',500,300,10),
               self.seg('A','hot',500,350,-1))
        for item in cases:
            with self.subTest(item=item):
                with self.assertRaises(ValueError):
                    self.mod.calculate_temperature_cascade([item])
        with self.assertRaises(ValueError):
            self.mod.calculate_temperature_cascade([],float('nan'))

    def test_att_default_assessment_does_not_credit_heat(self):
        sys=fixture_system()
        report=self.mod.get_att_heat_recovery_assessment(sys)
        self.assertEqual(report['credited_recovery_kJph'],0)
        self.assertEqual(report['conditional_ideal_recovery_kJph'],0)
        self.assertEqual(report['model_heating_kJph'],7200)
        self.assertEqual(report['model_cooling_kJph'],12000)
        self.assertTrue(report['temperature_audit'])
        self.assertIn('NO_HEN_IMPLEMENTED',report['status'])
        txt=self.mod.format_att_heat_recovery_assessment(report)
        self.assertIn('U3HX',txt)
        self.assertIn('Actual implemented / TEA-LCA credited recovery: 0.000',txt)

    def test_screening_does_not_automatically_count_u3hx_condensation(self):
        sys=fixture_system()
        sys.flowsheet.unit.D0.T=390
        report=self.mod.get_att_heat_recovery_assessment(
            sys, assume_isothermal_d0_ec1=True)
        ids={seg.unit_id for seg in report['selected_segments']}
        self.assertEqual(ids, {'RC1', 'D0', 'EC1'})
        self.assertNotIn('U3HX',ids)
        self.assertGreater(report['conditional_ideal_recovery_kJph'],0)
        self.assertEqual(report['credited_recovery_kJph'],0)

    def test_extra_segments_bounded_by_audited_unit_duty(self):
        sys=fixture_system()
        extra=self.seg('U3HX','hot',800,500,6001)
        with self.assertRaisesRegex(ValueError,'exceeds audited'):
            self.mod.get_att_heat_recovery_assessment(
                sys,additional_segments=[extra])
        okay=self.seg('U3HX','hot',800,500,1500)
        report=self.mod.get_att_heat_recovery_assessment(
            sys,additional_segments=[okay])
        self.assertEqual(report['credited_recovery_kJph'],0)
        self.assertEqual(report['selected_temperature_cascade']['hot_kJph'],4500)

    def test_c1_custom_duty_not_registered_is_audit_warning(self):
        sys=fixture_system()
        sys.flowsheet.unit.C1._utility_heat_duty_kJph=950
        report=self.mod.get_att_heat_recovery_assessment(sys)
        self.assertEqual(len(report['unregistered_custom_thermal_duties']), 1)
        self.assertAlmostEqual(report['unregistered_custom_thermal_duties'][0]['difference_kJph'],150)
        self.assertTrue(report['recorded_heating_may_be_incomplete'])
        self.assertTrue(any('C1 CUSTOM' in s for s in report['caveats']))

    def test_target_temperature_missing_is_not_invented(self):
        sys=fixture_system()
        sys.flowsheet.unit.EC1.outs=[]
        report=self.mod.get_att_heat_recovery_assessment(
            sys,assume_isothermal_d0_ec1=True)
        ids={s.unit_id for s in report['selected_segments']}
        self.assertNotIn('EC1',ids)
        self.assertTrue(any('EC1: missing' in w for w in report['caveats']))


class TestATTPinchTargets(unittest.TestCase):
    """Phase-resolved T-Q intervals and pinch targets of the real flowsheet."""

    @classmethod
    def setUpClass(cls):
        import warnings
        warnings.filterwarnings('ignore')
        from biorefineries.sabre.systems._att_system import create_att_system
        cls.mod = importlib.import_module(MODULE_NAME)
        cls.sys = create_att_system(dry_sargassum_kgph=1.0)
        cls.sys.set_tolerance(mol=1e-11, rmol=1e-11, T=1e-5, rT=1e-5,
                              maxiter=300, method='fixedpoint')
        cls.sys.simulate()
        cls.targets = {dT: cls.mod.get_att_pinch_targets(cls.sys, dT) for dT in (5., 10., 20.)}

    def test_intervals_reproduce_process_stream_duties(self):
        u = self.sys.flowsheet.unit
        totals = {}
        for s in self.targets[10.]['intervals']:
            totals[(s.unit_id, s.kind)] = totals.get((s.unit_id, s.kind), 0.) + s.duty_kJph
        liquor = u.C1.ins[0].copy()
        H0 = liquor.H
        liquor.T = u.C1.target_temperature_K
        expected = {
            ('U3HX', 'hot'): -sum(h.duty for h in u.U3HX.heat_utilities),
            ('RC1', 'hot'): -sum(h.duty for h in u.RC1.heat_utilities),
            ('EC1', 'hot'): -u.EC1._condenser_duty_kJph,
            ('EC1', 'cold'): u.EC1._heat_duty_kJph,        # process duty, no heat loss
            ('C1', 'cold'): liquor.H - H0,                  # carbonate liquor preheating only
        }
        self.assertEqual(set(totals), set(expected))
        for key, q in totals.items():
            with self.subTest(key=key):
                self.assertAlmostEqual(q / expected[key], 1.0, delta=0.005)
        self.assertLess(expected[('C1', 'cold')], u.C1._heat_duty_kJph)

    def test_product_gas_releases_most_heat_by_condensation(self):
        gas = [s for s in self.targets[10.]['intervals'] if s.unit_id == 'U3HX']
        above_100C = sum(s.duty_kJph for s in gas if s.T_end_K >= 373.15)
        below_100C = sum(s.duty_kJph for s in gas if s.T_start_K <= 373.15)
        self.assertGreater(below_100C, 2 * above_100C)

    def test_targets_are_consistent(self):
        for dT, r in self.targets.items():
            with self.subTest(dT=dT):
                self.assertAlmostEqual(r['minimum_hot_utility_kJph'] + r['recoverable_kJph'],
                                       r['integrated_heating_now_kJph'], places=6)
                self.assertLessEqual(r['recoverable_kJph'],
                                     min(r['integrated_heating_now_kJph'],
                                         r['integrated_hot_available_kJph']) + 1e-6)
                self.assertGreater(r['recoverable_kJph'], 0.)
        self.assertGreaterEqual(self.targets[5.]['recoverable_kJph'], self.targets[10.]['recoverable_kJph'])
        self.assertGreaterEqual(self.targets[10.]['recoverable_kJph'], self.targets[20.]['recoverable_kJph'])

    def _utilities(self):
        return [(x.ID, hu.duty) for x in self.sys.units for hu in x.heat_utilities]

    def test_hen_matches_are_temperature_feasible_and_conserve_heat(self):
        before = self._utilities()
        for dryer in (None, 'belt_hot_air'):
            r = self.mod.design_att_heat_exchanger_network(self.sys, dryer)
            with self.subTest(dryer=dryer):
                self.assertTrue(r['matches'])
                for m in r['matches']:
                    self.assertGreaterEqual(m['minimum_approach_K'], r['delta_T_min_K'] - 1e-6)
                    self.assertGreater(m['hot_T_in_K'], m['cold_T_out_K'])
                self.assertAlmostEqual(r['recovered_kJph'],
                                       sum(x['recovered_kJph'] for x in r['heating'].values()), places=6)
                self.assertAlmostEqual(r['recovered_kJph'],
                                       sum(x['recovered_kJph'] for x in r['cooling'].values()), places=6)
                for rows in (r['heating'], r['cooling']):
                    for row in rows.values():
                        self.assertGreaterEqual(row['remaining_external_kJph'], -1e-6)
                d0 = [m for m in r['matches'] if m['cold_unit'] == 'D0']
                if dryer is None:
                    self.assertFalse(d0)
                    self.assertEqual(r['dryer_dependent_recovery_kJph'], 0.0)
                else:
                    self.assertTrue(d0)
                    self.assertTrue(all(m['basis'] == 'unverified_dryer_assumption' for m in d0))
                self.assertEqual(r['status'], 'DESIGN_VERIFIED_NOT_CREDITED_IN_FLOWSHEET')
        self.assertEqual(before, self._utilities())  # baseline utilities untouched

    def test_hen_design_does_not_beat_its_pinch_target(self):
        r = self.mod.design_att_heat_exchanger_network(self.sys, None, 10.)
        self.assertGreaterEqual(r['integrated_heating_remaining_kJph'] + 1e-6,
                                self.targets[10.]['minimum_hot_utility_kJph'])


class TestATTHeatIntegrationScenario(unittest.TestCase):
    """heat_integration=True is an optional scenario; the baseline is unchanged."""

    @staticmethod
    def _build(heat_integration):
        import warnings
        warnings.filterwarnings('ignore')
        from biorefineries.sabre.systems._att_system import create_att_system
        sys = create_att_system(dry_sargassum_kgph=1.0, heat_integration=heat_integration)
        sys.set_tolerance(mol=1e-11, rmol=1e-11, T=1e-5, rT=1e-5, maxiter=300, method='fixedpoint')
        sys.simulate()
        return sys

    @staticmethod
    def _duties(sys):
        out = {}
        for x in sys.units:
            if x.heat_utilities:
                out[x.ID] = (sum(h.duty for h in x.heat_utilities if h.duty > 0),
                             sum(h.duty for h in x.heat_utilities if h.duty < 0))
        return out

    @classmethod
    def setUpClass(cls):
        cls.base = cls._build(False)
        cls.scen = cls._build(True)

    def test_baseline_has_no_heat_recovery_facility(self):
        self.assertFalse(self.base.facilities)
        self.assertIn('HXR', [f.ID for f in self.scen.facilities])

    def test_only_temperature_verified_matches_are_credited(self):
        HXR = self.scen.flowsheet.unit.HXR
        self.assertTrue(HXR.credited_matches)
        for m in HXR.credited_matches:
            self.assertEqual(m['basis'], 'temperature_verified')
            self.assertNotEqual(m['cold_unit'], 'D0')
            self.assertGreaterEqual(m['minimum_approach_K'], m['required_approach_K'] - 1e-6)

    def test_utilities_reduced_exactly_by_credited_heat(self):
        base, scen = self._duties(self.base), self._duties(self.scen)
        HXR = self.scen.flowsheet.unit.HXR
        heating_cut = {}
        cooling_cut = {}
        for m in HXR.credited_matches:
            heating_cut[m['cold_unit']] = heating_cut.get(m['cold_unit'], 0.) + m['duty_kJph']
            cooling_cut[m['hot_unit']] = cooling_cut.get(m['hot_unit'], 0.) + m['duty_kJph']
        for ID, (heat, cool) in base.items():
            with self.subTest(unit=ID):
                self.assertAlmostEqual(scen[ID][0], heat - heating_cut.get(ID, 0.), delta=1e-3)
                self.assertAlmostEqual(scen[ID][1], cool + cooling_cut.get(ID, 0.), delta=1e-3)
        for ID in ('D0', 'U2'):
            self.assertAlmostEqual(scen[ID][0], base[ID][0], delta=1e-6)

    def test_recovery_never_replaces_heat_loss_or_exceeds_stream_duty(self):
        units = {x.ID: x for x in self.scen.units}
        HXR = self.scen.facilities[0]
        for ID in ('EC1', 'C1'):
            unit = units[ID]
            recovered = sum(m['duty_kJph'] for m in HXR.credited_matches if m['cold_unit'] == ID)
            utility = sum(h.duty for h in unit.heat_utilities if h.duty > 0)
            with self.subTest(unit=ID):
                self.assertLessEqual(recovered, unit._heat_duty_kJph + 1e-6)
                # Remaining utility = process duty - recovered + heat loss.
                self.assertAlmostEqual(utility, unit._heat_duty_kJph - recovered + unit._heat_loss_kJph,
                                       delta=1e-3)
                self.assertGreaterEqual(utility, unit._heat_loss_kJph - 1e-6)
        liquor = units['C1'].ins[0].copy()
        H0 = liquor.H
        liquor.T = units['C1'].target_temperature_K
        c1_recovered = sum(m['duty_kJph'] for m in HXR.credited_matches if m['cold_unit'] == 'C1')
        self.assertLessEqual(c1_recovered, liquor.H - H0 + 1e-6)

    def test_facility_is_idempotent(self):
        u = self.scen.flowsheet.unit
        before = self._duties(self.scen)
        u.HXR.simulate()
        self.assertEqual(before, self._duties(self.scen))


class TestATTEC1TemperatureScenario(unittest.TestCase):
    """115 C EC1 is an optimization scenario; the 90 C baseline is unchanged."""

    def test_baseline_rejects_and_scenario_flags_solubility_extrapolation(self):
        from biorefineries.sabre import _naoh_properties as naoh
        with self.assertRaises(ValueError):
            naoh.na2co3_solubility_mol_per_kg_water(20.0, 388.15)
        import warnings
        warnings.filterwarnings('ignore')
        from biorefineries.sabre.systems._att_system import create_att_system
        sys = create_att_system(dry_sargassum_kgph=1.0, ec1_temperature_K=388.15)
        sys.set_tolerance(mol=1e-11, rmol=1e-11, T=1e-5, rT=1e-5, maxiter=300, method='fixedpoint')
        sys.simulate()
        EC1 = sys.flowsheet.unit.EC1
        self.assertFalse(EC1.is_baseline_temperature)
        self.assertTrue(EC1._na2co3_solubility_extrapolated)
        self.assertAlmostEqual(EC1.T, 388.15)
        self.assertGreater(EC1._condensation_temperature_K, 343.15 + 10.0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
