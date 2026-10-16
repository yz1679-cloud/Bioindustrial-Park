"""Consistency checks of the ATT research-stage inventory (att.inventory)."""
import unittest

from biorefineries.sabre.analyses.att import inventory as inv
from biorefineries.sabre.systems._att_system import create_att_system
from biorefineries.sabre.utils import load_assumptions

_ATT = load_assumptions("att.yaml")["att"]


def _simulate(dry_kgph):
    sys = create_att_system(dry_sargassum_kgph=dry_kgph)
    sys.set_tolerance(mol=1e-11 * dry_kgph, rmol=1e-11, T=1e-5, rT=1e-5, maxiter=200, method="fixedpoint")
    sys.simulate()
    return sys


class TestATTInventory(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.sys = _simulate(1.0)
        cls.flows = inv.get_att_external_flows(cls.sys)
        cls.utilities = inv.get_att_purchased_utilities(cls.sys)
        cls.products = inv.get_att_product_scenarios(cls.sys)
        cls.u = {r["item"]: r["per_kg_dry"] for r in cls.utilities}

    def test_mass_and_element_balance(self):
        check = inv.check_att_inventory(self.sys, self.flows, self.utilities)
        self.assertLess(abs(check["mass_relative_error"]), 1e-8)
        for element, error in check["element_relative_error"].items():
            self.assertLess(abs(error), 1e-8, element)

    def test_every_stream_has_one_fate(self):
        streams = {r["stream"] for r in self.flows}
        self.assertEqual(streams, {s.ID for s in (*self.sys.feeds, *self.sys.products)})
        self.assertEqual(_ATT["inventory"]["stream_fates"]["u3_tail_gas"][1], "coproduct_offgas")

    def test_natural_gas_efficiency_applied_once(self):
        delivered = self.u["U2 natural gas: heat delivered incl. 5 % reactor loss"]
        fuel = self.u["U2 natural gas: fuel input (LHV)"]
        eta = float(_ATT["energy_sources"]["natural_gas"]["burner_efficiency"])
        self.assertAlmostEqual(fuel, delivered / eta, places=12)
        self.assertGreater(delivered, self.u["U2 natural gas: process heat"])
        biosteam_fuel = self.u["U2 natural gas: BioSTEAM agent fuel (cross-check only)"]
        self.assertLess(abs(fuel / biosteam_fuel - 1.0), 0.02)

    def test_gas_products(self):
        p = {r["item"]: r for r in self.products}
        s = {u.ID: u for u in self.sys.units}["U2"]._gas_scale_factor
        self.assertAlmostEqual(s, 0.5998, places=4)
        for gas in ("H2", "CH4", "CO", "CO2"):
            row = p[f"{gas} in U2 gas"]
            self.assertAlmostEqual(row["model_mmol_per_g_daf"], s * row["reported_mmol_per_g_daf"], places=10)
        self.assertAlmostEqual(p["H2 product (after PSA)"]["kg_per_kg_dry"], 0.0793 * s, places=4)
        tail = [s for s in self.sys.products if s.ID == "u3_tail_gas"][0]
        self.assertAlmostEqual(p["CO2 in collected off-gas"]["kg_per_kg_dry"], float(tail.imass["CO2"]), places=12)

    def test_h2_discrepancy_documented(self):
        rows = {r["item"]: r["value"] for r in inv.get_att_h2_yield_basis_check(self.sys)}
        self.assertGreater(rows["Reported gases / feed electrons"], 1.3)

    def test_carbon_fate_closes(self):
        rows = inv.get_att_carbon_fate(self.sys)
        c_in = sum(r["kg_C_per_kg_dry"] for r in rows if r["direction"] == "input")
        c_out = sum(r["kg_C_per_kg_dry"] for r in rows if r["direction"] == "output")
        self.assertAlmostEqual(c_out / c_in, 1.0, places=8)

    def test_lci_uses_collaborator_factors_and_no_offgas_emission(self):
        lci = {r["flow"]: r for r in inv.get_att_lci(self.flows, self.utilities, self.products)}
        self.assertEqual(lci["NaOH makeup"]["EF"], 1.12)
        self.assertEqual(lci["Ca(OH)2 (CaOH2_limestone)"]["EF"], 0.91)
        self.assertEqual(lci["PSA off-gas (collected)"]["GWP_kgCO2e_per_kg_dry"], 0.0)
        self.assertEqual(lci["CaCO3 cake (coproduct)"]["GWP_kgCO2e_per_kg_dry"], 0.0)


    def test_final_verification_tables(self):
        for r in inv.get_att_unit_balances(self.sys):
            self.assertLess(abs(r["mass_relative_error"]), 1e-8, r["unit"])
            for e in ("C", "H", "O", "N", "Na", "Ca"):
                self.assertLess(abs(r[f"{e}_relative_error"]), 1e-8, (r["unit"], e))
        self.assertTrue(all(r["status"] == "OK" for r in inv.get_att_stream_sanity_check(self.sys)))
        water = {r["item"]: r["kg_per_kg_dry"] for r in inv.get_att_water_balance(self.sys)}
        self.assertLess(abs(water["inputs + formation - outputs"]), 1e-8)
        ledger = {r["item"]: r["value"] for r in inv.get_att_sodium_calcium_ledger(self.sys)}
        self.assertTrue(0.75 < ledger["Effective NaOH recovery = 1 - makeup / gross"] < 0.80)
        for r in inv.get_att_utility_consistency_check(self.sys):
            self.assertEqual(r["status"], "PASS", r["check"])
        for r in inv.get_att_unit_energy_balance(self.sys):
            if r["unexplained_MJ_per_kg_dry"] == r["unexplained_MJ_per_kg_dry"]:
                self.assertLess(abs(r["unexplained_MJ_per_kg_dry"]), 1e-6, r["unit"])

    def test_ch4_reported_value_kept_and_labeled(self):
        gas = {r["species"]: r for r in inv.get_att_gas_accounting(self.sys)}
        self.assertAlmostEqual(gas["CH4"]["reported_mmol_per_g_daf"], 8.768738649553573, places=12)
        self.assertGreater(gas["CH4"]["model_mmol_per_g_daf"], 0.0)
        for g in ("H2", "CH4", "CO", "CO2"):
            self.assertIn("NOT a measurement", gas[g]["basis"])

    def test_experimental_gas_yield_scenario_keeps_reported_gases(self):
        rows = {r["item"]: r for r in inv.get_att_experimental_gas_yield_scenario(self.sys)}
        self.assertAlmostEqual(rows["CH4"]["reported_mmol_per_g_daf"], 8.768738649553573, places=12)
        self.assertAlmostEqual(rows["CO"]["reported_mmol_per_g_daf"], 0.1648486662946429, places=12)
        self.assertAlmostEqual(rows["CH4"]["U2_outlet_kg_per_kg_dry"], 0.0921, places=4)
        self.assertAlmostEqual(rows["H2"]["to_H2_product_kg_per_kg_dry"], 0.0793, places=4)
        self.assertIn("NOT element/redox balanced", rows["CH4"]["status"])

    def test_energy_summary_uses_own_system(self):
        # A later system must not change the reported utilities of this one.
        from biorefineries.sabre.analyses.att.mass_energy import get_att_energy_summary
        before = get_att_energy_summary(self.sys)["U2_utility_heat_kJph"]
        _simulate(2.0)
        after = get_att_energy_summary(self.sys)["U2_utility_heat_kJph"]
        self.assertEqual(before, after)


class TestATTCostEstimates(unittest.TestCase):

    def test_reference_scale_estimates(self):
        scale = inv.get_att_reference_scale()
        sys = _simulate(scale["dry_feed_kgph"])
        rows = {r["item"]: r for r in inv.get_att_cost_estimates(sys)}
        for item in ("C1 agitated tank", "U2 reactor vessel",
                     "EC1 forced-circulation evaporator", "EC1 condenser"):
            self.assertGreater(rows[item]["purchase_cost"], 0.0, item)
        self.assertNotEqual(rows["PSA unit"]["purchase_cost"], rows["PSA unit"]["purchase_cost"])  # NaN: missing


if __name__ == "__main__":
    unittest.main()
