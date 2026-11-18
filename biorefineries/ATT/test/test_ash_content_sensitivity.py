"""Reported ash sensitivity and independent material/element conservation checks.

The experimental yields and screening gas masses below are independent of the
reactor implementation. Full-scale cases run in fresh processes so thermodynamic
settings, flowsheets and solved TEA prices cannot leak between cases.
"""
import unittest

from biorefineries.ATT.analyses.ash_content_sensitivity import run_case


class TestAshContentSensitivity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = [run_case(ash, ree) for ash, ree in
                     ((0.3207, True), (0.167, True), (0.3207, False), (0.167, False))]
        cls.repeated = run_case(0.3207, True)

    def test_reported_gas_production_from_experiment(self):
        # 5029.17 kg dry/h, 54.15/0.60 mmol/g DAF; textbook MW [g/mol].
        reference = {0.3207: (372.924630359, 32.883659783),
                     0.167: (457.303425716, 40.323993227)}
        for case in self.cases:
            m = case['process']
            for gas, expected in zip(('H2', 'CH4'), reference[case['ash_fraction']]):
                with self.subTest(ash=case['ash_fraction'], ree=case['ree_enabled'], gas=gas):
                    self.assertAlmostEqual(m[f'{gas}_kgph'] / expected, 1., delta=1e-5)
            self.assertEqual(case['gas_yields_mmol_per_g_daf'],
                             {'H2': 54.15, 'CH4': .60, 'CO': 0., 'CO2': .77})

    def test_feed_mass_and_moisture_conservation(self):
        for case in self.cases:
            m = case['process']
            self.assertAlmostEqual(sum(case['dry_composition'].values()), 1., delta=1e-12)
            self.assertAlmostEqual(m['dry_feed_kgph'], 5029.17, delta=1e-7)
            self.assertAlmostEqual(m['feed_moisture_fraction'], .763, delta=1e-10)
            self.assertAlmostEqual(m['dried_feed_moisture_fraction'], .5, delta=1e-10)
            self.assertAlmostEqual(m['ash_fraction_measured'], case['ash_fraction'], delta=1e-10)
            self.assertAlmostEqual(m['gross_NaOH_kgph'], 5029.17, delta=1e-6)
            self.assertEqual(m['operating_hours'], 7920.)

    def test_unit_and_boundary_mass_element_conservation(self):
        for case in self.cases:
            for row in case['balances']:
                with self.subTest(ash=case['ash_fraction'], ree=case['ree_enabled'], **row):
                    self.assertLess(abs(row['relative_error']), 1e-8)

    def test_recycle_species_are_at_steady_state(self):
        for case in self.cases:
            self.assertLess(case['process']['recycle_max_relative_change'], 1e-6)

    def test_organic_elemental_composition_is_preserved(self):
        # Renormalizing minerals must preserve the organic source material;
        # this also pins the reported DAF composition rather than only ash.
        base = self.cases[0]['dry_composition']
        for case in self.cases:
            composition = case['dry_composition']
            for component in base:
                if component != 'Ash':
                    self.assertAlmostEqual(composition[component]/(1-case['ash_fraction']),
                                           base[component]/(1-.3207), delta=1e-12)
            self.assertEqual(case['fixed_assumptions'], self.cases[0]['fixed_assumptions'])

    def test_scenario_operating_cost_and_gwp_accounting(self):
        for case in self.cases:
            for row in case['scenarios']:
                costs = sum(r['USD_per_yr'] for r in case['opex'] if r['scenario'] == row['scenario'])
                impact = sum(r['kgCO2e_per_year'] for r in case['scenario_impacts'] if r['scenario'] == row['scenario'])
                self.assertAlmostEqual(costs/row['net_OPEX_USD_per_year'], 1., delta=1e-9)
                self.assertAlmostEqual(impact/row['net_GWP_kgCO2e_per_year'], 1., delta=1e-9)

    def test_baseline_result_reproducible_after_sensitivity(self):
        before, after = self.cases[0], self.repeated
        for key in ('H2_kgph', 'CH4_kgph', 'fresh_NaOH_kgph', 'CaOH2_kgph', 'U2_heating_kW'):
            self.assertAlmostEqual(after['process'][key] / before['process'][key], 1., delta=1e-5)
        for a, b in zip(before['scenarios'], after['scenarios']):
            for key in ('FCI_USD', 'MSP_USD_per_kg_H2', 'GWP_kgCO2e_per_kg_H2'):
                self.assertAlmostEqual(b[key] / a[key], 1., delta=1e-5)


if __name__ == '__main__':
    unittest.main()
