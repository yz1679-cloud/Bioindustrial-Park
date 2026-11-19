"""Reported reference values and accounting identities for the optional credits."""
import unittest
import warnings

import biosteam as bst

from biorefineries.ATT.analyses import inventory, lca, scenarios, tea
from biorefineries.ATT.analyses import avoided_emissions as avoided


class TestAvoidedEmissionReferences(unittest.TestCase):

    def test_brazilian_mix_reported_reference(self):
        # Bueno Table 3 wet-basis mixture; 1 tonne raw biomass, not presscake.
        reference = avoided.decomposition_emissions(1000.)
        self.assertAlmostEqual(reference['avoided_ch4_kg'], 7.7005, places=7)
        self.assertAlmostEqual(reference['biogenic_co2_kg'], 23.125, places=7)
        self.assertAlmostEqual(reference['avoided_co2e_kg'], 215.614, places=7)
        ar6 = avoided.decomposition_emissions(1000., ch4_gwp100=25.3)
        self.assertAlmostEqual(ar6['avoided_co2e_kg'], 194.82265, places=7)

    def test_presscake_dry_solids_identity(self):
        # One tonne at the current 76.3% moisture represents 237 kg solids.
        raw = avoided.raw_sargassum_equivalent(1000., 763.)
        self.assertAlmostEqual(raw, 1896., places=7)
        reference = avoided.decomposition_emissions(raw)
        self.assertAlmostEqual(reference['avoided_co2e_kg'], 408.804144, places=7)
        # Reconstruct dry matter on the reference raw basis independently.
        self.assertAlmostEqual(raw - raw * .875, 237., places=7)

    def test_reported_dry_solids_reference(self):
        dry = avoided.decomposition_emissions_dry(1000.)
        self.assertAlmostEqual(dry['ch4_kg_per_t_dry'], 61.604, places=7)
        self.assertAlmostEqual(dry['avoided_ch4_kg'], 61.604, places=7)
        self.assertAlmostEqual(dry['avoided_co2e_kg'], 1724.912, places=7)
        presscake = avoided.decomposition_emissions_dry(237.)
        self.assertAlmostEqual(presscake['avoided_ch4_kg'], 14.600148, places=7)
        self.assertAlmostEqual(presscake['avoided_co2e_kg'], 408.804144, places=7)
        ar6 = avoided.decomposition_emissions_dry(1000., ch4_gwp100=25.3)
        self.assertAlmostEqual(ar6['avoided_co2e_kg'], 1558.5812, places=7)


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
        none = avoided.calculate_avoided_emissions(self.system, include_decomposition=True, decomposition_fraction=0.)
        half = avoided.calculate_avoided_emissions(self.system, include_decomposition=True, decomposition_fraction=.5)
        for basis in ('per_kg_h2', 'per_tonne_wet_presscake'):
            m, p = main[basis], potential[basis]
            self.assertEqual(m['avoided_sargassum_decomposition_emissions'], 0.)
            self.assertAlmostEqual(m['original_CI']-m['expanded_CI'], m['avoided_gcc_production_emissions'])
            self.assertAlmostEqual(m['expanded_CI']-p['expanded_CI'], p['avoided_sargassum_decomposition_emissions'])
            self.assertAlmostEqual(none[basis]['expanded_CI'], m['expanded_CI'])
            self.assertAlmostEqual(half[basis]['expanded_CI'], (m['expanded_CI']+p['expanded_CI'])/2.)
        # Independently specified reference results per dry tonne, not copied formulas.
        for realization, expected in [(0., 0.), (.1, 172.4912), (.5, 862.456), (1., 1724.912)]:
            result = avoided.calculate_avoided_emissions(self.system, include_decomposition=True,
                                                       decomposition_fraction=realization)
            self.assertAlmostEqual(result['per_tonne_dry']['avoided_sargassum_decomposition_emissions'], expected, places=7)

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
                self.assertAlmostEqual(current['activity']['avoided_ch4_kgph'], baseline['activity']['avoided_ch4_kgph'], places=8)
                self.assertAlmostEqual(current['activity']['presscake_dry_kgph'], dry, places=8)
                self.assertEqual(current['decomposition_basis'], 'actual presscake dry solids')
                for key in ('original_CI','existing_storage_credit','avoided_gcc_production_emissions',
                            'main_CI','potential_CI','avoided_sargassum_decomposition_emissions'):
                    self.assertAlmostEqual(current['per_kg_h2'][key], baseline['per_kg_h2'][key], places=8)
        finally:
            feed.imass['Water'] = water

    def test_wet_reference_solids_accounting(self):
        result = avoided.calculate_avoided_emissions(self.system)
        dry = result['per_tonne_dry']
        for basis, solids in [('per_tonne_fresh_87_5', .125), ('per_tonne_wet_75', .25)]:
            for key, value in dry.items():
                self.assertAlmostEqual(result[basis][key], value*solids)
        # Source-reference decomposition per fresh tonne is independent of ATT yield.
        potential = avoided.calculate_avoided_emissions(self.system, include_decomposition=True)
        self.assertAlmostEqual(potential['per_tonne_fresh_87_5']['avoided_sargassum_decomposition_emissions'], 215.614)


if __name__ == '__main__':
    unittest.main()
