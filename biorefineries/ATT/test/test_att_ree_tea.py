"""REE economics: independent DCF root, real revenue credit and annual ledgers."""
import unittest
import warnings


class REETeaVerificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        warnings.filterwarnings('ignore')
        from biorefineries.ATT.analyses.ree_tea_verification import collect_ree_tea
        cls.data = collect_ree_tea()

    def test_six_case_dcf_and_annual_cost_reconciliation(self):
        # (REE off, REE on), USD/kg H2. Environment: biosteam a4f6d15, thermosteam d3d4c7f, hensmith 95e9362 (see
        # test_att_baseline). Yu Zhou's report (2026-11-07; her environment) gives S1 1.84222142 / 1.85420646,
        # S2 2.04398179 / 2.08109738 and S3 1.48445443 / 1.49643947 for the same model; the differences come from
        # the heat integration (hensmith) only.
        expected = {'S1': (1.91774738, 1.93007488),
                    'S2': (2.11950775, 2.15696580),
                    'S3': (1.55998039, 1.57230789)}
        self.assertEqual(len(self.data['cases']), 6)
        for row in self.data['cases']:
            msp = expected[row['scenario']][int(row['ree_enabled'])]
            # 8 % covers Yu Zhou's environment (up to 5.1 % lower) and this one; the DCF and the independent root
            # must agree with each other exactly in any environment
            self.assertAlmostEqual(row['dcf_msp_usd_per_kg_H2']/msp, 1., delta=0.08)
            self.assertAlmostEqual(row['independent_msp_usd_per_kg_H2'], row['dcf_msp_usd_per_kg_H2'], places=6)
            self.assertLess(abs(row['discounted_cashflow_residual_usd']), 1.)
            self.assertAlmostEqual(sum(row[k] for k in ('materials_usd_per_year', 'utilities_usd_per_year',
                'waste_usd_per_year', 'fixed_usd_per_year')), row['gross_opex_usd_per_year'], places=5)
            self.assertAlmostEqual(row['gross_opex_usd_per_year']-row['coproduct_revenue_usd_per_year'],
                                   row['net_opex_usd_per_year'], places=5)
            self.assertAlmostEqual(row['net_opex_usd_per_year']+row['screening_capital_usd_per_year'],
                                   row['net_treatment_cost_usd_per_year'], places=5)
            parts = [x['usd_per_kg_H2'] for x in self.data['dcf_components']
                     if x['scenario']==row['scenario'] and x['ree_enabled']==row['ree_enabled']]
            self.assertAlmostEqual(sum(parts), row['dcf_msp_usd_per_kg_H2'], places=7)

    def test_coproduct_revenues_are_credited_once_in_dcf(self):
        for row in self.data['cases']:
            for product in ('reo', 'caco3'):
                self.assertAlmostEqual(row[f'msp_without_{product}_revenue']-row['dcf_msp_usd_per_kg_H2'],
                    row[f'{product}_revenue_usd_per_year']/row['h2_kg_per_year'], places=7)
            self.assertAlmostEqual(row['FCI_usd'], row['installed_capital_sum_usd'], places=5)
            self.assertAlmostEqual(row['HCl_usd_per_year'], row['HCl_feed_cost_usd_per_year'], places=5)
            self.assertAlmostEqual(row['oxalic_usd_per_year'], row['oxalic_feed_cost_usd_per_year'], places=5)

    def test_ree_increment_reconciles_without_changing_production(self):
        self.assertEqual(len(self.data['increments']),3)
        for row in self.data['increments']:
            self.assertAlmostEqual(row['delta_h2_kg_per_year'],0.,delta=1e-6)       # the same H2 output, up to rounding
            self.assertEqual(row['delta_operating_hours'],0.)
            self.assertGreater(row['delta_msp_usd_per_kg_H2'],0.)
            self.assertAlmostEqual(row['delta_gross_opex_usd_per_year']+row['delta_screening_capital_usd_per_year']
                -row['delta_coproduct_revenue_usd_per_year'],row['delta_net_treatment_cost_usd_per_year'], places=5)
            if row['scenario']=='S1':
                self.assertAlmostEqual(row['delta_FCI_usd']/1e6,1.28829,places=4)
                self.assertAlmostEqual(row['delta_gross_opex_usd_per_year'],416516.,delta=5000.)     # 415505 from Yu's values
                self.assertAlmostEqual(row['delta_coproduct_revenue_usd_per_year'],547064.,delta=2.)


if __name__=='__main__': unittest.main()
