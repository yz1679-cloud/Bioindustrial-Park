"""Contained-REO reference and avoided-production accounting identities."""
import unittest
import warnings

from biorefineries.ATT.analyses import avoided_emissions as avoided
from biorefineries.ATT.analyses import inventory, lca, scenarios, tea


class TestREOCredit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        warnings.filterwarnings('ignore')
        cls.systems = [scenarios.create(ree_recovery=enabled) for enabled in (True, False)]

    def test_reported_contained_reo_credit_and_element_equivalent_balance(self):
        sys = self.systems[0]
        streams = inventory._streams(sys)
        result = avoided.calculate_avoided_emissions(sys, original_ci=10.)
        # Independent reported flow pin, unaffected by heat-integration releases.
        self.assertAlmostEqual(result['activity']['contained_reo_kgph'], 1.97537750928, delta=1e-5)
        self.assertAlmostEqual(result['activity']['potential_reo_kgCO2eph'], 41.6409578956224, places=8)
        self.assertAlmostEqual(result['per_tonne_dry']['avoided_reo_production_emissions'], 8.27988672, places=8)
        self.assertAlmostEqual(result['per_tonne_wet_presscake']['avoided_reo_production_emissions'], 1.96233315264, places=8)
        # TREE reconstructed on the configured oxide basis must close.
        self.assertAlmostEqual(streams['att_sargassum_feed'].imass['REO']/1.169,
                               (streams['ree_product'].imass['REO']+streams['att_char'].imass['REO'])/1.169, places=10)

    def test_credit_ledger_normalization_and_no_process_or_tea_change(self):
        for enabled, sys in zip((True, False), self.systems):
            lca.apply_att_gwp(sys, overrides=scenarios.lca_overrides())
            def snapshot():
                econ = tea.evaluate_att_tea(sys, **scenarios.tea_config())
                return ([(s.ID, tuple(s.mass), s.T, s.P, s.H) for s in inventory._streams(sys).values()],
                        [(u.ID, u.power_utility.rate, tuple((h.duty, h.flow) for h in u.heat_utilities)) for u in sys.units],
                        econ['msp'], econ['tea'].FCI, econ['tea'].AOC,
                        sys.get_net_impact(lca.KEY), lca.get_att_stored_carbon_credit(sys), lca.get_att_avoided_emission(sys))
            before = snapshot()
            old = avoided.calculate_avoided_emissions(sys, include_reo=False, include_decomposition=True)
            new = avoided.calculate_avoided_emissions(sys, include_decomposition=True)
            for basis in ('per_kg_h2', 'per_tonne_dry', 'per_tonne_wet_presscake'):
                a, b = old[basis], new[basis]
                credit = b['avoided_reo_production_emissions']
                self.assertEqual(a['original_CI'], b['original_CI'])
                for key in ('existing_storage_credit', 'avoided_gcc_production_emissions',
                            'avoided_sargassum_decomposition_emissions'):
                    self.assertEqual(a[key], b[key])
                self.assertAlmostEqual(a['main_CI']-b['main_CI'], credit, places=10)
                self.assertAlmostEqual(a['potential_CI']-b['potential_CI'], credit, places=10)
                self.assertAlmostEqual(b['original_CI'], b['expanded_CI']+credit
                                       +b['avoided_gcc_production_emissions']
                                       +b['avoided_sargassum_decomposition_emissions'], places=10)
                if not enabled:
                    self.assertEqual(credit, 0.)
            a = new['activity']
            hourly = new['per_kg_h2']['avoided_reo_production_emissions']*a['h2_kgph']
            for basis, flow in (('per_tonne_dry', a['presscake_dry_kgph']),
                                ('per_tonne_wet_presscake', a['presscake_wet_kgph'])):
                self.assertAlmostEqual(hourly, new[basis]['avoided_reo_production_emissions']*flow/1000., places=10)
            self.assertEqual(before, snapshot())

    def test_substitution_and_product_mass_do_not_create_extra_reo(self):
        sys = self.systems[0]
        full = avoided.calculate_avoided_emissions(sys, original_ci=10.)
        half = avoided.calculate_avoided_emissions(sys, original_ci=10., reo_substitution_fraction=.5)
        zero = avoided.calculate_avoided_emissions(sys, original_ci=10., reo_substitution_fraction=0.)
        product = inventory._streams(sys)['ree_product']
        ash = float(product.imass['Ash'])
        try:
            product.imass['Ash'] = ash*2.
            diluted = avoided.calculate_avoided_emissions(sys, original_ci=10.)
        finally:
            product.imass['Ash'] = ash
        credit = full['per_kg_h2']['avoided_reo_production_emissions']
        self.assertEqual(diluted['per_kg_h2']['avoided_reo_production_emissions'], credit)
        self.assertEqual(half['per_kg_h2']['avoided_reo_production_emissions'], credit/2.)
        self.assertEqual(zero['per_kg_h2']['avoided_reo_production_emissions'], 0.)


if __name__ == '__main__':
    unittest.main()
