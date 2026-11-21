"""Conservation of reported energy and zero-boundary feedstock headroom."""
import unittest
import warnings

from biorefineries.ATT.analyses import s3_figures as figures


class TestFeedstockHeadroom(unittest.TestCase):
    def test_allowance_and_deficit_close_the_zero_boundary(self):
        # Additional acquisition cost/emissions consume a surplus; a deficit
        # instead requires cost savings/emissions reductions, never an allowance.
        for cost, emissions, cost_cap, cost_gap, emissions_cap, emissions_gap in (
            (-25., 40., 25., 0., 0., 40.),
            (12., -80., 0., 12., 80., 0.),
            (0., 0., 0., 0., 0., 0.),
        ):
            result = figures.feedstock_headroom(cost, emissions)
            self.assertEqual(result['allowable_cost_usd_per_t_dry'], cost_cap)
            self.assertEqual(result['cost_deficit_usd_per_t_dry'], cost_gap)
            self.assertEqual(result['allowable_emissions_kgCO2e_per_t_dry'], emissions_cap)
            self.assertEqual(result['emissions_deficit_kgCO2e_per_t_dry'], emissions_gap)
            self.assertEqual(cost+result['allowable_cost_usd_per_t_dry']-result['cost_deficit_usd_per_t_dry'], 0.)
            self.assertEqual(emissions+result['allowable_emissions_kgCO2e_per_t_dry']-result['emissions_deficit_kgCO2e_per_t_dry'], 0.)


class TestReportedEnergyConservation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        warnings.filterwarnings('ignore')
        figures._load()
        cls.energy = figures.energy()

    def test_actual_presscake_energy_matches_hourly_process_energy(self):
        bases = figures.energy_basis_values(self.energy)
        dry = bases['dry']
        wet = bases['presscake']
        # Independent inlet inventory supplies the reporting denominator.
        external = figures.B['external']
        feed = next(row for row in external if row['stream'] == 'att_sargassum_feed' and row['component'] == 'TOTAL')
        wet_kgph = feed['kg_per_h']
        self.assertAlmostEqual(wet['factor'], .237, places=12)
        for kind in ('demand', 'supply'):
            for name, value in wet[kind].items():
                self.assertAlmostEqual(value*wet_kgph, dry[kind][name]*figures.DRY, places=7)
        self.assertAlmostEqual(wet['total_demand'], wet['total_supply'], places=10)
        # Pins the reported corrected figure, with heat-integration tolerance.
        self.assertAlmostEqual(wet['total_demand']/6.5047356, 1., delta=.08)
        self.assertAlmostEqual(bases['fresh_reference']['factor'], .125, places=12)

    def test_benchmark_headroom_reconstructs_existing_economic_and_gwp_ledgers(self):
        for benchmark in figures.BENCHMARKS:
            for decomposition in (False, True):
                economic, environmental = figures.treatment_components(benchmark, decomposition)
                result = figures.benchmark_headroom(benchmark, decomposition)
                # Apply the reported allowance or resolve its reported deficit:
                # this must return to zero in both existing accounting ledgers.
                self.assertAlmostEqual(sum(value for _, value, _ in economic)
                    +result['allowable_cost_usd_per_t_dry']-result['cost_deficit_usd_per_t_dry'], 0., places=8)
                self.assertAlmostEqual(sum(value for _, value, _ in environmental)
                    +result['allowable_emissions_kgCO2e_per_t_dry']-result['emissions_deficit_kgCO2e_per_t_dry'], 0., places=8)

    def test_displayed_net_heating_reconciles_to_discounted_cashflow(self):
        displayed = figures.contribution_values()[0]
        # Independent underlying DCF ledger: fuel/steam costs and the existing
        # discounted avoided-heat saving belong to one displayed contribution.
        expected = sum(r['usd_per_kg_H2'] for r in figures.DCF
                       if r['component'] in ('Utility: natural_gas', 'Utility: low_pressure_steam',
                                             'Industrial WHR: avoided heat')
                       or r['component'].startswith('Natural gas:'))
        net_heat = sum(value for label, value, _ in displayed if label.startswith('Heating / natural gas'))
        self.assertAlmostEqual(net_heat, expected, places=10)
        self.assertAlmostEqual(net_heat/.801199, 1., delta=.08)
        self.assertAlmostEqual(sum(value for _, value, _ in displayed),
                               sum(r['usd_per_kg_H2'] for r in figures.DCF), places=10)
        self.assertAlmostEqual(sum(value for _, value, _ in displayed),
                               figures.ECON['independent_msp_usd_per_kg_H2'], places=6)


if __name__ == '__main__':
    unittest.main()
