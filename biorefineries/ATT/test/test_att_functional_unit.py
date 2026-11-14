import unittest
from biorefineries.ATT.analyses.functional_unit import normalize_case


class FunctionalUnitTests(unittest.TestCase):
    def test_conversions_and_cost_components(self):
        r = normalize_case(wet_kgph=1000, dry_kgph=237, h2_kgph=10, hours=8000,
                           flows_kgph={'char': 20}, operating_cost_usd_year=1600000,
                           coproduct_revenue_usd_year=400000, capital_charge_usd_year=800000,
                           gross_gwp_per_kg_h2=25, credit_gwp_per_kg_h2=-8, msp_per_kg_h2=2)
        self.assertEqual(r['per_tonne_wet']['dry_presscake_kg'], 237)
        self.assertEqual(r['per_kg_h2']['wet_presscake_kg'], 100)
        self.assertEqual(r['per_tonne_wet']['char_kg'], 20)
        self.assertEqual(r['annual']['net_treatment_cost_usd'], 2000000)
        self.assertEqual(r['per_tonne_wet']['net_treatment_cost_usd'], 250)
        self.assertEqual(r['per_tonne_wet']['net_gwp_kg_co2e'], 170)
        self.assertEqual(r['per_kg_h2']['net_gwp_kg_co2e'], 17)

    def test_invalid_basis(self):
        args = dict(wet_kgph=0, dry_kgph=0, h2_kgph=1, hours=1, flows_kgph={},
                    operating_cost_usd_year=0, coproduct_revenue_usd_year=0,
                    capital_charge_usd_year=0, gross_gwp_per_kg_h2=1,
                    credit_gwp_per_kg_h2=0, msp_per_kg_h2=1)
        with self.assertRaises(ValueError):
            normalize_case(**args)

if __name__ == '__main__': unittest.main()

class FunctionalUnitIntegrationTests(unittest.TestCase):
    def test_six_cases_preserve_bases_and_accounting(self):
        from biorefineries.ATT.analyses.treatment_report import run
        rows, balances, carbon, pseudo = run()
        self.assertEqual(len(rows), 12)
        self.assertEqual({(r['scenario'], r['ree_enabled']) for r in rows},
                         {(s, e) for s in ('S1', 'S2', 'S3') for e in (True, False)})
        for r in rows:
            self.assertAlmostEqual(r['net_gwp_kg_co2e'], r['gross_gwp_kg_co2e'] + r['credit_gwp_kg_co2e'])
            self.assertAlmostEqual(r['annual_net_treatment_cost_usd'], r['annual_operating_cost_usd']
                                   + r['annual_capital_charge_usd'] - r['annual_coproduct_revenue_usd'])
            if r['basis'] == 'per_tonne_wet':
                self.assertAlmostEqual(r['wet_presscake_kg'], 1000.)
                self.assertAlmostEqual(r['dry_presscake_kg'] / 1000., 1 - r['moisture_fraction'])
        self.assertTrue(any(r['stream'] == 'att_residue_untracked' and r['species'] == 'ResidueCHO' for r in pseudo))
        self.assertEqual(len(balances), 2)
        self.assertTrue(any(r['stream'] == 'att_residue_untracked' for r in carbon))
