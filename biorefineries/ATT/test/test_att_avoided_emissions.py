"""Reported reference values and accounting identities for the optional credits."""
import unittest
import warnings

import biosteam as bst

from biorefineries.ATT.analyses import inventory, lca, scenarios, tea
from biorefineries.ATT.analyses import avoided_emissions as avoided
from biorefineries.ATT._chemicals import create_chemicals
from biorefineries.ATT.utils import load_assumptions, make_sargassum_feed
from chemicals.elements import periodic_table


class TestAvoidedEmissionReferences(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        create_chemicals(include_att=True)
        cfg = load_assumptions('feedstock.yaml')['feedstock_type']['nlr_pressed']
        cls.feed = make_sargassum_feed(1000., cfg['moisture_frac'], cfg['dry_composition'])

    def test_reported_mechanistic_reference(self):
        # Aerobic pin revised: transfer the anaerobic-derived BI to aerobic
        # mineralization by modeling assumption, without changing methane.
        r = avoided.decomposition_emissions(self.feed)
        for key, expected in [('anaerobic_ch4_kg', 5.314), ('anaerobic_co2_kg', 15.56),
                              ('aerobic_co2_kg', 45.204030), ('biogenic_co2_kg', 60.762259)]:
            self.assertAlmostEqual(r[key], expected, delta=.01, msg=key)
        self.assertAlmostEqual(r['avoided_co2e_kg'], 134.44, delta=.02)
        self.assertAlmostEqual(r['avoided_co2e_kg']/r['inventory']['dry_mass_kg']*1000., 567.3, delta=.1)

    def test_active_component_element_and_formula_accounting(self):
        r = avoided.decomposition_emissions(self.feed)
        inv = r['inventory']
        self.assertAlmostEqual(inv['dry_mass_kg'], 237., places=10)
        self.assertAlmostEqual(inv['organic_mass_kg'], 160.9941, places=10)
        for e in ('C', 'H', 'O', 'N', 'S'):
            # Native stream atom accounting is independent of our inventory loop.
            expected = self.feed.get_atomic_flow(e)
            if e in ('H', 'O'):
                expected -= self.feed.imol['Water'] * (2 if e=='H' else 1)
            self.assertAlmostEqual(inv['element_kmol'][e], expected, places=10)
            self.assertAlmostEqual(inv['element_mass_kg'][e], expected*periodic_table[e].MW, places=9)
        self.assertGreater(inv['element_mass_kg']['S'], .13)
        self.assertAlmostEqual(sum(inv['element_mass_kg'].values()), inv['organic_mass_kg'], places=9)
        self.assertAlmostEqual(inv['formula_unit_kmol']*inv['formula_mw_kg_per_kmol'], inv['organic_mass_kg'], places=9)

    def test_boyle_element_balance_and_sulfur(self):
        # Cellulose: one repeat + H2O -> 3 CH4 + 3 CO2.
        r = avoided.boyle_coefficients(dict(C=6., H=10., O=5., N=0., S=0.))
        self.assertEqual((r['CH4'], r['CO2'], r['H2O']), (3., 3., 1.))
        # Methanethiol: CH4S + 0.5 H2O -> .75 CH4 + .25 CO2 + H2S.
        r = avoided.boyle_coefficients(dict(C=1., H=4., O=0., N=0., S=1.))
        self.assertEqual((r['CH4'], r['CO2'], r['H2S'], r['H2O']), (.75, .25, 1., .5))
        atoms = avoided.organic_inventory(self.feed)['normalized_formula']
        r = avoided.boyle_coefficients(atoms)
        self.assertAlmostEqual(r['CH4']+r['CO2'], atoms['C'])
        self.assertAlmostEqual(4*r['CH4']+3*r['NH3']+2*r['H2S'], atoms['H']+2*r['H2O'])
        self.assertAlmostEqual(2*r['CO2'], atoms['O']+r['H2O'])
        self.assertEqual(r['NH3'], atoms['N'])
        self.assertEqual(r['H2S'], atoms['S'])

    def test_pathway_carbon_allocation_and_residual(self):
        for anaerobic in (0., .2, .4, .6, .8, 1.):
            r = avoided.decomposition_emissions(self.feed, anaerobic_fraction=anaerobic)
            carbon = r['inventory']['element_mass_kg']['C']
            self.assertAlmostEqual(r['anaerobic_organic_mass_kg']+r['aerobic_organic_mass_kg'], 160.9941)
            self.assertAlmostEqual(r['anaerobic_carbon_kg']+r['aerobic_carbon_kg'], carbon)
            self.assertAlmostEqual(r['anaerobic_gas_carbon_kg']+r['aerobic_gas_carbon_kg']+r['unmineralized_carbon_kg'], carbon)
            # Independently recover gas carbon from emitted species masses.
            gas_carbon = (r['anaerobic_ch4_kg']/self.feed.chemicals['CH4'].MW
                          + (r['anaerobic_co2_kg']+r['aerobic_co2_kg'])/self.feed.chemicals['CO2'].MW)*periodic_table['C'].MW
            self.assertAlmostEqual(gas_carbon+r['unmineralized_carbon_kg'], carbon)
            self.assertGreaterEqual(min(r[k] for k in ('anaerobic_ch4_kg','anaerobic_co2_kg','aerobic_co2_kg')), 0.)
        self.assertEqual(avoided.decomposition_emissions(self.feed, anaerobic_fraction=0.)['anaerobic_ch4_kg'], 0.)
        self.assertEqual(avoided.decomposition_emissions(self.feed, anaerobic_fraction=1.)['aerobic_co2_kg'], 0.)

    def test_independent_mineralization_and_atmospheric_accounting(self):
        full = avoided.decomposition_emissions(self.feed, anaerobic_biodegradability=1.)
        half = avoided.decomposition_emissions(self.feed, anaerobic_biodegradability=.5)
        self.assertAlmostEqual(half['anaerobic_ch4_kg'], full['anaerobic_ch4_kg']/2.)
        self.assertAlmostEqual(half['anaerobic_co2_kg'], full['anaerobic_co2_kg']/2.)
        self.assertEqual(half['aerobic_co2_kg'], full['aerobic_co2_kg'])
        none = avoided.decomposition_emissions(self.feed, aerobic_mineralization=0., methane_realization=0.)
        self.assertEqual(none['aerobic_co2_kg'], 0.)
        self.assertEqual(none['atmospheric_ch4_kg'], 0.)
        self.assertEqual(none['avoided_co2e_kg'], 0.)
        self.assertGreater(none['anaerobic_ch4_kg'], 0.)
        quarter = avoided.decomposition_emissions(self.feed, methane_realization=.25)
        self.assertAlmostEqual(quarter['atmospheric_ch4_kg']+quarter['unrealized_ch4_kg'], quarter['anaerobic_ch4_kg'])
        self.assertAlmostEqual(quarter['atmospheric_ch4_kg'], quarter['anaerobic_ch4_kg']/4.)


class TestAvoidedEmissionAccounting(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        warnings.filterwarnings('ignore')
        cls.system = scenarios.create(scenarios.ATT_S1)
        lca.apply_att_gwp(cls.system, overrides=scenarios.lca_overrides())

    def test_mixed_cake_component_and_epd_reference(self):
        stream = bst.Stream(None, CaCO3=1000., Water=200., Ash=50., units='kg/hr')
        self.assertAlmostEqual(avoided.gcc_production_emissions([stream]), 12.5, places=7)
        # Adding impurities changes total mass but cannot create displacement.
        stream.imass['Water'] = 800.
        self.assertAlmostEqual(avoided.gcc_production_emissions([stream]), 12.5, places=7)

    def test_credit_ledger_and_model_invariance(self):
        sys = self.system
        def snapshot():
            result = tea.evaluate_att_tea(sys, **scenarios.tea_config())
            return ([(s.ID, tuple(s.mass), s.H, s.T, s.P) for s in inventory._streams(sys).values()],
                    [(u.ID, u.power_utility.rate, tuple((h.duty, h.flow) for h in u.heat_utilities)) for u in sys.units],
                    result['msp'], result['tea'].FCI, result['tea'].AOC,
                    sys.get_net_impact(lca.KEY), lca.get_att_stored_carbon_credit(sys),
                    lca.get_att_avoided_emission(sys))
        before = snapshot()
        expanded = avoided.calculate_avoided_emissions(sys, include_decomposition=True)
        gcc_only = avoided.calculate_avoided_emissions(sys, include_decomposition=False)
        decomposition_only = avoided.calculate_avoided_emissions(sys, include_gcc=False, include_decomposition=True)
        off = avoided.calculate_avoided_emissions(sys, include_gcc=False, include_decomposition=False)
        self.assertEqual(before, snapshot())
        for basis in ('per_kg_h2', 'per_tonne_wet_presscake'):
            b = expanded[basis]
            # Independent accounting: each credit reduces the original once.
            self.assertAlmostEqual(b['original_CI'] - b['expanded_CI'],
                                   (b['original_CI'] - gcc_only[basis]['expanded_CI'])
                                   + (b['original_CI'] - decomposition_only[basis]['expanded_CI']))
            self.assertEqual(off[basis]['original_CI'], off[basis]['expanded_CI'])
            self.assertEqual(b['original_CI'], off[basis]['original_CI'])
        b = expanded['per_kg_h2']
        self.assertAlmostEqual(b['existing_storage_credit'], before[-2])
        self.assertAlmostEqual(b['original_CI'] - b['expanded_CI'],
                               b['avoided_gcc_production_emissions']
                               + b['avoided_sargassum_decomposition_emissions'])
        # No biogenic CO2 or legacy optional beach-rot result enters this sum.
        h2 = expanded['activity']['h2_kgph']
        wet = expanded['activity']['presscake_wet_kgph']
        for key, value in b.items():
            self.assertAlmostEqual(value * h2, expanded['per_tonne_wet_presscake'][key] * wet / 1000.)

    def test_existing_gcc_displacement_cannot_be_credited_twice(self):
        sys = self.system
        cake = inventory._streams(sys)['caco3_cake']
        saved = dict(cake.characterization_factors)
        try:
            cake.set_CF(lca.KEY, .0125)
            with self.assertRaisesRegex(ValueError, 'already'):
                avoided.calculate_avoided_emissions(sys)
        finally:
            cake.characterization_factors.clear()
            cake.characterization_factors.update(saved)

    def test_existing_decomposition_cannot_be_credited_twice(self):
        sys = self.system
        saved = list(sys.process_impact_items[lca.KEY])
        try:
            sys.define_process_impact(lca.KEY, 'Avoided beach decomposition', 'kg', lambda: -1., 1.)
            with self.assertRaisesRegex(ValueError, 'already'):
                avoided.calculate_avoided_emissions(sys, include_decomposition=True)
        finally:
            sys.process_impact_items[lca.KEY] = saved

    def test_main_and_potential_credit_ledgers(self):
        main = avoided.calculate_avoided_emissions(self.system)
        potential = avoided.calculate_avoided_emissions(self.system, include_decomposition=True)
        none = avoided.calculate_avoided_emissions(self.system, include_decomposition=True, methane_realization=0.)
        half = avoided.calculate_avoided_emissions(self.system, include_decomposition=True, methane_realization=.5)
        for basis in ('per_kg_h2', 'per_tonne_wet_presscake'):
            m, p = main[basis], potential[basis]
            self.assertEqual(m['avoided_sargassum_decomposition_emissions'], 0.)
            self.assertAlmostEqual(m['original_CI']-m['expanded_CI'], m['avoided_gcc_production_emissions'])
            self.assertAlmostEqual(m['expanded_CI']-p['expanded_CI'], p['avoided_sargassum_decomposition_emissions'])
            self.assertAlmostEqual(none[basis]['expanded_CI'], m['expanded_CI'])
            self.assertAlmostEqual(half[basis]['expanded_CI'], (m['expanded_CI']+p['expanded_CI'])/2.)
        # Independently specified reference results per dry tonne, not copied formulas.
        for realization, expected in [(0., 0.), (.1, 56.73), (.5, 283.65), (1., 567.3)]:
            result = avoided.calculate_avoided_emissions(self.system, include_decomposition=True,
                                                       methane_realization=realization)
            self.assertAlmostEqual(result['per_tonne_dry']['avoided_sargassum_decomposition_emissions'], expected, delta=.1)

    def test_constant_dry_solids_methane_is_invariant_to_water(self):
        # Change water only; this read-only credit calculation must not infer
        # changed methane potential from a different wet-feed moisture.
        feed = inventory._streams(self.system)['att_sargassum_feed']
        water = float(feed.imass['Water'])
        baseline = avoided.calculate_avoided_emissions(self.system, include_decomposition=True)
        dry = baseline['activity']['presscake_dry_kgph']
        try:
            for moisture in (.5, .763, .875, .9):
                feed.imass['Water'] = dry * moisture / (1.-moisture)
                current = avoided.calculate_avoided_emissions(self.system, include_decomposition=True)
                self.assertAlmostEqual(current['activity']['atmospheric_ch4_kgph'], baseline['activity']['atmospheric_ch4_kgph'], places=8)
                self.assertAlmostEqual(current['activity']['presscake_dry_kgph'], dry, places=8)
                for key in ('original_CI','existing_storage_credit','avoided_gcc_production_emissions',
                            'main_CI','potential_CI','avoided_sargassum_decomposition_emissions'):
                    self.assertAlmostEqual(current['per_kg_h2'][key], baseline['per_kg_h2'][key], places=8)
        finally:
            feed.imass['Water'] = water

    def test_actual_feed_and_hydrogen_normalization(self):
        result = avoided.calculate_avoided_emissions(self.system, include_decomposition=True)
        a = result['activity']
        for key, dry_value in result['per_tonne_dry'].items():
            self.assertAlmostEqual(result['per_tonne_wet_presscake'][key], dry_value*a['presscake_dry_kgph']/a['presscake_wet_kgph'])
            self.assertAlmostEqual(result['per_kg_h2'][key]*a['h2_kgph'], dry_value*a['presscake_dry_kgph']/1000.)
        self.assertAlmostEqual(result['per_kg_h2']['avoided_sargassum_decomposition_emissions'], 7.65, delta=.01)

    def test_sensitivity_pathway_and_climate_accounting(self):
        rows = avoided.scenario_rows(self.system, 'S1', True, 20.)
        reference = next(r for r in rows if r['credit_case']=='potential' and r['reference_case'] and r['basis']=='per_tonne_wet_presscake')
        cfg = avoided.assumptions()['avoided_sargassum_decomposition_emissions']
        for r in rows:
            if r['credit_case']!='potential' or r['basis']!='per_tonne_wet_presscake':
                continue
            for key in cfg['sensitivities']:
                if key != r['sensitivity_parameter']:
                    self.assertEqual(r[key], cfg[key])
            self.assertAlmostEqual(r['anaerobic_fraction']+r['aerobic_fraction'], 1.)
            self.assertAlmostEqual(r['anaerobic_co2_kg']+r['aerobic_co2_kg'], r['biogenic_co2_kg'])
            self.assertAlmostEqual(r['atmospheric_ch4_kg']*r['ch4_gwp100'], r['methane_climate_impact_kgCO2e'])
            if r['sensitivity_parameter']=='aerobic_mineralization':
                self.assertEqual(r['methane_climate_impact_kgCO2e'], reference['methane_climate_impact_kgCO2e'])
            if r['sensitivity_parameter']=='methane_realization':
                self.assertEqual(r['biogenic_co2_kg'], reference['biogenic_co2_kg'])


if __name__ == '__main__':
    unittest.main()
