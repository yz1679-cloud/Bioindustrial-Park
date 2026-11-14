"""Industrial heat screening: source capacity and conservative temperature bounds."""
import unittest
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

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

    def test_steam_generation_ignores_nonsteam_demand(self):
        source = [dict(source='H', available_kW=100., T_in_C=200., T_out_C=100.)]
        sinks = [dict(unit='U2', utility='natural_gas', eligible=True, purchased_kW=100.)]
        self.assertEqual(whr.generate_steam(source, sinks, steam_temperature_C=70.)['used_kW'], 0.)

    def test_duplicate_source_identifiers_are_rejected(self):
        source = dict(source='H1', available_kW=100., T_in_C=200., T_out_C=100.)
        sink = dict(unit='steam', utility='low_pressure_steam', eligible=True, purchased_kW=200.)
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            whr.generate_steam([source, source.copy()], [sink], steam_temperature_C=70.)

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

    def test_cooling_exchanger_is_not_a_steam_sink(self):
        def hu(agent, duty):
            return SimpleNamespace(agent=SimpleNamespace(ID=agent), duty=duty * 3600)
        self.assertEqual(whr.steam_duty_kW([hu('cooling_water', -625.833)]), 0)
        self.assertEqual(whr.steam_duty_kW([hu('low_pressure_steam', 4148.6), hu('cooling_water', -10)]), 4148.6)

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

    def test_effectiveness_and_zero_demand(self):
        source = [dict(source='H', available_kW=100, T_in_C=200, T_out_C=100)]
        sink = [dict(unit='x', purchased_kW=200, T_out_C=80, eligible=True)]
        self.assertAlmostEqual(whr.allocate(source, sink, effectiveness=.8)['used_kW'], 80)
        self.assertEqual(whr.allocate(source, [], effectiveness=.8)['used_kW'], 0)

    def test_annual_heat_units(self):
        self.assertEqual(whr.annual_heat(1000., 1000.), (1000., 3600.))

    def test_invalid_inputs_rejected(self):
        with self.assertRaises(ValueError):
            whr.industrial_sources(host_hours=0)
        with self.assertRaises(ValueError):
            whr.allocate([], [], effectiveness=1.1)

    def test_unreconciled_sink_inventory_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'steam inventory'):
            whr.check_steam_inventory([dict(utility='low_pressure_steam', purchased_kW=105.)], 100.)
        whr.check_steam_inventory([dict(utility='low_pressure_steam', purchased_kW=100.)], 100.)


class S3IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from biorefineries.ATT.analyses.att_s3_industrial import run
        cls.cases = [run(enable_ree_recovery=value) for value in (True, False)]

    def test_both_cases_close_heat_and_credits(self):
        import biosteam as bst
        agent = bst.HeatUtility.get_agent('low_pressure_steam')
        agent_latent_kJ_per_kg = float(agent.chemicals['Water'].Hvap(agent.T)) / float(agent.MW)
        for case in self.cases:
            with self.subTest(ree=case['ree_enabled']):
                self.assertLessEqual(case['used_average_kW'], case['feasible_overlap_kW'])
                self.assertLessEqual(case['feasible_overlap_kW'], case['available_kW'])
                self.assertGreater(case['steam_agent']['temperature_C'], 130.)
                self.assertGreater(case['steam_agent']['latent_heat_kJ_per_kg'], 0.)
                self.assertAlmostEqual(case['steam_agent']['temperature_C'], agent.T - 273.15)
                self.assertAlmostEqual(case['steam_agent']['pressure_Pa'], agent.P)
                self.assertAlmostEqual(case['steam_agent']['latent_heat_kJ_per_kg'], agent_latent_kJ_per_kg)
                self.assertAlmostEqual(case['source_extracted_overlap_kW'], case['used_average_kW'] / case['overlap_fraction'] + case['transfer_loss_overlap_kW'])
                self.assertAlmostEqual(case['remaining_steam_average_kW'] + case['used_average_kW'], case['baseline_steam_kW'])
                self.assertAlmostEqual(case['avoided_boiler_fuel_average_kW'], case['used_average_kW'] / .8)
                self.assertAlmostEqual(case['steam_generated_average_kg_per_h'] * case['steam_agent']['latent_heat_kJ_per_kg'] / 3600., case['used_average_kW'])
                self.assertAlmostEqual(case['process_heat_equivalent_average_kW'], case['used_average_kW'] * case['steam_agent']['utility_to_process_ratio'])
                self.assertAlmostEqual(case['avoided_emissions_kg_per_hour'], case['avoided_boiler_fuel_average_kW'] * 3.6 * (.056 + .0098))
                self.assertAlmostEqual(case['avoided_cost_usd_per_year'], case['used_average_kW'] * case['sinks'][0]['usd_per_kWh'] * 7920.)
                self.assertAlmostEqual(case['available_kW'], case['source_extracted_overlap_kW'] + case['unused_overlap_kW'])
                self.assertGreaterEqual(case['heating_after_average_kW'], 0.)
                self.assertAlmostEqual(case['heating_before_kW'] - case['heating_after_average_kW'], case['used_average_kW'])
                self.assertAlmostEqual(case['recovered_GJ_per_year'], case['recovered_MWh_per_year'] * 3.6)
                self.assertAlmostEqual(sum(a['used_kW'] for a in case['allocations']) * case['overlap_fraction'], case['used_average_kW'])
                for a in case['allocations']:
                    self.assertGreaterEqual(a['interval_bottom_C'] + 1e-8, a['sink_temperature_C'] + 20.)
                self.assertAlmostEqual(next(s for s in case['sinks'] if s['unit'] == 'U3D')['purchased_kW'], 0., places=8)
                self.assertLess(case['hxn_enthalpy_audit']['max_lifecycle_error_kW'], 1e-5)
                self.assertLess(case['hxn_enthalpy_audit']['max_exchanger_error_kW'], 1e-5)
                self.assertTrue(case['s3_MSP_usd_per_kg_H2'] > 0)
                self.assertAlmostEqual(case['GWP_change_kg_per_kg_H2'],
                    (case['auxiliary_emissions_kg_per_hour'] + case['heat_burden_kg_per_hour'] - case['avoided_emissions_kg_per_hour']) / case['h2_kg_per_hour'])

    def test_s1_material_flows_are_preserved_and_exported(self):
        for case in self.cases:
            self.assertTrue(case['boundary_flows_unchanged'])
            self.assertGreater(case['product_flows']['h2_product']['H2_kg_per_h'], 0.)
            self.assertEqual('ree_product' in case['product_flows'], case['ree_enabled'])

    def test_export_is_strict_json_and_refuses_overwrite(self):
        from biorefineries.ATT.analyses.att_s3_results import write_outputs
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'new-results'
            comparison = [{'scenario': 'S1', 'ree_enabled': True, 'MSP_USD_per_kg_H2': 1.0}]
            write_outputs(out, self.cases, comparison)
            self.assertTrue((out / 'scenario_comparison.csv').is_file())
            self.assertTrue((out / 'heat_sources.csv').is_file())
            self.assertTrue((out / 'heat_allocations.csv').is_file())
            self.assertTrue((out / 'process_products.csv').is_file())
            self.assertTrue((out / 'summary.csv').is_file())
            with (out / 'results.json').open(encoding='utf-8') as f:
                data = json.load(f, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
            self.assertEqual(len(data['cases']), 2)
            with self.assertRaises(FileExistsError):
                write_outputs(out, self.cases, comparison)


if __name__ == '__main__':
    unittest.main()
