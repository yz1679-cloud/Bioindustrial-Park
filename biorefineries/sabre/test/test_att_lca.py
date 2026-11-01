"""GWP100 of the frozen ATT model (att.lca): accounting and conversions."""
import unittest
import warnings

from biorefineries.sabre.analyses.att import inventory as inv
from biorefineries.sabre.analyses.att import lca


class TestATTGWP(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        warnings.filterwarnings("ignore")
        cls.sys = lca.create_att_lca_system()
        cls.estimates = inv.get_att_cost_estimates(cls.sys)
        cls.applied = lca.apply_att_gwp(cls.sys, estimates=cls.estimates)
        cls.contributions = lca.get_att_gwp_contributions(cls.sys, cls.applied)
        cls.c = {r["item"]: r for r in cls.contributions}
        cls.dry = inv._dry_feed_kgph(cls.sys)

    def test_numerical_checks_pass(self):
        utilities = inv.get_att_purchased_utilities(self.sys, self.estimates)
        for r in lca.check_att_lca(self.sys, self.applied, self.contributions, utilities):
            self.assertEqual(r["status"], "PASS", r["check"])

    def test_functional_unit_is_model_h2(self):
        total = self.c["TOTAL (System.get_net_impact)"]
        h2 = float(inv._streams(self.sys)["h2_product"].imass["H2"]) / self.dry
        units = inv._units(self.sys)
        U2 = units["U2"]
        recovery = 0.9 if "U3P" in units else 1.0     # PSA recovery; ATT Scenario 1 has no PSA
        self.assertAlmostEqual(h2, U2._model_gas_yield_mmol_per_g_daf["H2"] * U2._daf_sargassum_kgph / self.dry
                               * 2.01588e-3 * recovery, places=10)
        self.assertAlmostEqual(total["GWP_kgCO2e_per_kg_H2"], total["GWP_kgCO2e_per_kg_dry"] / h2, places=9)

    def test_no_credits_or_unmodeled_ch4(self):
        self.assertEqual(self.sys.get_total_products_impact(lca.KEY), 0.0)
        self.assertFalse(any("CH4" in item or "CaCO3" in item for item in self.c))

    def test_steel_slag_scenario(self):
        base = self.c["TOTAL (System.get_net_impact)"]["GWP_kgCO2e_per_kg_dry"]
        s = inv._streams(self.sys)
        lime = sum(float(s[ID].F_mass) for ID in ("lime", "scrubber_lime") if ID in s) / self.dry       # C1 lime + CO2-scrubber lime
        try:
            lca.apply_att_gwp(self.sys, lime_source="CaOH2_steel_slag", estimates=self.estimates)
            slag = self.sys.get_net_impact(lca.KEY) / (self.dry * self.sys.operating_hours)
        finally:
            lca.apply_att_gwp(self.sys, estimates=self.estimates)
        self.assertAlmostEqual(base - slag, lime * 0.91, places=9)

    def test_neutralization_stoichiometry(self):
        streams = inv._streams(self.sys)
        expected = sum(float(streams[ID].imol["NaOH"] + streams[ID].imol["Na2CO3"])
                       for ID in ("liquor_purge", "f2_wash_liquor") if ID in streams) / 2 * 98.07848
        self.assertAlmostEqual(lca._h2so4_kgph(self.sys), float(expected), places=6)

    def test_optional_collection_transport(self):
        settings = lca._LCA["collection_transport"]
        try:
            settings["marine_fuel_kg_per_t_wet"] = 1.0
            lca.apply_att_gwp(self.sys, estimates=self.estimates)
            item = next(i for i in self.sys.process_impact_items[lca.KEY]
                        if i.name == "Sargassum collection and transport")
            wet_t = float(inv._streams(self.sys)["att_sargassum_feed"].F_mass) / 1e3
            self.assertAlmostEqual(item.impact(), wet_t * 3.2 * self.sys.operating_hours, places=3)
        finally:
            settings["marine_fuel_kg_per_t_wet"] = None
            lca.apply_att_gwp(self.sys, estimates=self.estimates)


if __name__ == "__main__":
    unittest.main()
