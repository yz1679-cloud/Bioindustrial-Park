"""Industrial heat screening (S3): the heat taken from the source is bounded by the source capacity, the sink demand and the
temperatures, and every kW is accounted for once."""
import unittest

from biorefineries.ATT.analyses import industrial_whr as whr


class IndustrialHeatTests(unittest.TestCase):
    def test_steam_generation_respects_steam_temperature_and_balance(self):
        sources = [dict(source='H', available_kW=100., T_in_C=200., T_out_C=100.)]
        sinks = [dict(unit='steam', utility='low_pressure_steam', eligible=True, purchased_kW=200.)]
        r = whr.generate_steam(sources, sinks, steam_temperature_C=130., approach_C=20., effectiveness=.8)
        self.assertAlmostEqual(r['feasible_kW'], 50.)
        self.assertAlmostEqual(r['extracted_kW'], 50.)
        self.assertAlmostEqual(r['used_kW'], 40.)
        self.assertAlmostEqual(r['loss_kW'], 10.)
        self.assertAlmostEqual(r['unused_kW'], 50.)

    def test_steam_generation_limits_extraction_to_demand_and_handles_zero(self):
        sources = [dict(source='H', available_kW=100., T_in_C=200., T_out_C=100.)]
        sinks = [dict(unit='steam', utility='low_pressure_steam', eligible=True, purchased_kW=20.)]
        r = whr.generate_steam(sources, sinks, steam_temperature_C=70., effectiveness=.8)
        self.assertAlmostEqual(r['extracted_kW'], 25.)
        self.assertAlmostEqual(r['used_kW'], 20.)
        self.assertEqual(whr.generate_steam(sources, sinks, steam_temperature_C=70., effectiveness=0.)['used_kW'], 0.)

    def test_cold_source_cannot_generate_steam_and_multiple_sinks_share_heat(self):
        sources = [dict(source='cold', available_kW=100., T_in_C=140., T_out_C=40.),
                   dict(source='hot', available_kW=100., T_in_C=200., T_out_C=100.)]
        sinks = [dict(unit='a', utility='low_pressure_steam', eligible=True, purchased_kW=35.),
                 dict(unit='b', utility='low_pressure_steam', eligible=True, purchased_kW=35.)]
        r = whr.generate_steam(sources, sinks, steam_temperature_C=130., effectiveness=1.)
        self.assertAlmostEqual(r['feasible_kW'], 50.)
        self.assertAlmostEqual(r['used_kW'], 50.)
        self.assertAlmostEqual(sum(a['used_kW'] for a in r['allocations'] if a['unit'] == 'a'), 35.)
        self.assertAlmostEqual(sum(a['used_kW'] for a in r['allocations'] if a['unit'] == 'b'), 15.)
        self.assertAlmostEqual(r['unused_kW'], 150.)

    def test_source_capacity_and_hours(self):
        sources = whr.industrial_sources()
        self.assertAlmostEqual(sources[0]['available_kW'], 12040 * .90718474)
        self.assertAlmostEqual(sources[1]['available_kW'], 3930 * .90718474)
        self.assertAlmostEqual(whr.industrial_sources(host_hours=4000)[0]['available_kW'],
                               sources[0]['available_kW'] * 7920 / 4000)

    def test_allocation_obeys_temperature_and_conservation(self):
        sources = [dict(source='H', available_kW=100, T_in_C=200, T_out_C=100)]
        sinks = [dict(unit='cold', purchased_kW=80, T_out_C=130, eligible=True),
                 dict(unit='hot', purchased_kW=80, T_out_C=190, eligible=True)]
        result = whr.allocate(sources, sinks, approach_C=20, effectiveness=1)
        self.assertAlmostEqual(result['feasible_kW'], 50)
        self.assertAlmostEqual(result['used_kW'], 50)
        self.assertEqual({a['unit'] for a in result['allocations']}, {'cold'})
        self.assertAlmostEqual(result['unused_kW'], 50)

    def test_effectiveness_limits_the_heat_delivered(self):
        source = [dict(source='H', available_kW=100, T_in_C=200, T_out_C=100)]
        sink = [dict(unit='x', purchased_kW=200, T_out_C=80, eligible=True)]
        self.assertAlmostEqual(whr.allocate(source, sink, effectiveness=.8)['used_kW'], 80)
        self.assertEqual(whr.allocate(source, [], effectiveness=.8)['used_kW'], 0)


class S3IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from biorefineries.ATT.analyses.att_s3_industrial import run
        cls.cases = [run(enable_ree_recovery=value) for value in (True, False)]

    def test_both_cases_conserve_heat_and_respect_temperatures(self):
        for case in self.cases:
            with self.subTest(ree=case['ree_enabled']):
                # the heat used is bounded by what the temperatures allow, and that by what the source has
                self.assertLessEqual(case['used_average_kW'], case['feasible_overlap_kW'])
                self.assertLessEqual(case['feasible_overlap_kW'], case['available_kW'])
                # every kW of the source is extracted or unused, and every extracted kW is used or lost
                self.assertAlmostEqual(case['available_kW'], case['source_extracted_overlap_kW'] + case['unused_overlap_kW'])
                self.assertAlmostEqual(case['source_extracted_overlap_kW'],
                                       case['used_average_kW'] / case['overlap_fraction'] + case['transfer_loss_overlap_kW'])
                # the steam demand falls by exactly the heat used, and the steam generated carries that heat
                self.assertAlmostEqual(case['remaining_steam_average_kW'] + case['used_average_kW'], case['baseline_steam_kW'])
                self.assertAlmostEqual(case['heating_before_kW'] - case['heating_after_average_kW'], case['used_average_kW'])
                self.assertGreaterEqual(case['heating_after_average_kW'], 0.)
                self.assertAlmostEqual(case['steam_generated_average_kg_per_h'] * case['steam_agent']['latent_heat_kJ_per_kg'] / 3600.,
                                       case['used_average_kW'])
                self.assertAlmostEqual(sum(a['used_kW'] for a in case['allocations']) * case['overlap_fraction'], case['used_average_kW'])
                # no heat flows to a sink at less than the minimum approach temperature
                for a in case['allocations']:
                    self.assertGreaterEqual(a['interval_bottom_C'] + 1e-8, a['sink_temperature_C'] + 20.)
                # the heat-exchanger-network enthalpy audit closes
                self.assertLess(case['hxn_enthalpy_audit']['max_lifecycle_error_kW'], 1e-5)
                self.assertLess(case['hxn_enthalpy_audit']['max_exchanger_error_kW'], 1e-5)

    def test_s1_material_flows_are_preserved(self):
        for case in self.cases:
            self.assertTrue(case['boundary_flows_unchanged'])


if __name__ == '__main__':
    unittest.main()
