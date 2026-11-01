"""CaCO3 sales and carbonate storage accounting (ATT S1, washing on): the LCA follows the TEA disposition of the
cakes, sold CaCO3 never earns a storage credit, the inherited credit stays available as a comparison, and the
carbon of the plant closes."""
import unittest
import warnings

from biorefineries.ATT.analyses.att import inventory as inv
from biorefineries.ATT.analyses.att import lca
from biorefineries.ATT.analyses.att import scenarios as scen
from biorefineries.ATT.analyses.att import tea as tea_mod
from biorefineries.ATT.analyses.att.breakdown import build_att_breakdown

C_PER_CACO3 = 12.011 / 100.0869


class TestCarbonateAccounting(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        warnings.filterwarnings("ignore")
        cls.sys = scen.create(scen.ATT_S1)
        cls.s = inv._streams(cls.sys)
        cls.h2 = float(cls.s["h2_product"].imass["H2"])
        cls.sold = build_att_breakdown("att_s1", sys=cls.sys)["summary"]
        cls.kept = build_att_breakdown("att_s1", sys=cls.sys, f2_sales=False)["summary"]
        build_att_breakdown("att_s1", sys=cls.sys)                       # leave the baseline applied

    def caco3_C(self, ID):
        return float(self.s[ID].imass["CaCO3"]) * C_PER_CACO3

    def test_baseline_is_conservative(self):
        self.assertEqual(lca._LCA["carbon_storage"]["carbonate_storage_accounting"], "conservative")
        self.assertEqual(self.sold["carbonate_storage_accounting"], "conservative")

    def test_sold_caco3_has_no_storage_credit(self):
        # optimistic sales: F2 and F3 CaCO3 all sold -> nothing landfilled is credited (Na2CO3 is not credited)
        self.assertAlmostEqual(lca._stored_carbon_kgph(self.sys), 0.0, places=12)
        self.assertEqual(self.sold["GWP_stored_carbon_credit_in_net_kgCO2e_per_kg_H2"], 0.0)
        # no F2 sales: exactly the F2 CaCO3 carbon is landfilled and credited; the sold F3 CaCO3 is not
        sales = scen.tea_config(f2_sales=False)["caco3_sales"]
        self.assertAlmostEqual(lca._stored_carbon_kgph(self.sys, caco3_sales=sales), self.caco3_C("caco3_cake"), places=9)
        self.assertAlmostEqual(self.kept["GWP_stored_carbon_credit_in_net_kgCO2e_per_kg_H2"],
                               -self.caco3_C("caco3_cake") * 44.0095 / 12.011 / self.h2, places=9)
        # nothing sold at all: all landfilled CaCO3 credited, still no soluble carbonate
        self.assertAlmostEqual(lca._stored_carbon_kgph(self.sys, caco3_sales=None),
                               self.caco3_C("caco3_cake") + self.caco3_C("scrubber_cake"), places=9)

    def test_tea_and_lca_use_the_same_sold_amount(self):
        total = self.caco3_C("caco3_cake") + self.caco3_C("scrubber_cake")
        for f2 in (True, False):
            sales = scen.tea_config(f2_sales=f2)["caco3_sales"]
            acc = tea_mod.caco3_sales_accounting(self.sys, **sales)
            for ID in ("caco3_cake", "scrubber_cake"):
                self.assertAlmostEqual(acc[ID]["sold_caco3_kgph"],
                                       lca.caco3_saleable_fraction(ID, sales) * float(self.s[ID].imass["CaCO3"]), places=12)
            # every CaCO3 carbon is either sold (revenue, no credit) or landfilled (credit), never both
            sold_C = sum(r["sold_caco3_kgph"] for r in acc.values()) * C_PER_CACO3
            self.assertAlmostEqual(sold_C + lca._stored_carbon_kgph(self.sys, caco3_sales=sales), total, places=9)

    def test_inherited_comparison_is_preserved(self):
        # the earlier treatment: all non-residue carbon of the landfilled cakes, sold or not
        expected = sum(float(self.s[ID].get_atomic_flow("C")) * 12.011
                       for ID in ("caco3_cake", "scrubber_cake", "ash_residue_cake")) - sum(
            float(self.s["ash_residue_cake"].imol[r]) * self.s["ash_residue_cake"].chemicals[r].atoms["C"] * 12.011
            for r in lca._LCA["carbon_storage"]["provisional_residue_species"] if r in self.s["ash_residue_cake"].chemicals)
        self.assertAlmostEqual(lca._stored_carbon_kgph(self.sys, accounting="inherited"), expected, places=9)
        for s in (self.sold, self.kept):        # independent of the disposition, as before
            self.assertAlmostEqual(s["GWP_inherited_carbonate_credit_kgCO2e_per_kg_H2"], 14.243019, delta=1e-6)
            self.assertAlmostEqual(s["GWP_kgCO2e_per_kg_H2"] - s["GWP_stored_carbon_credit_in_net_kgCO2e_per_kg_H2"],
                                   s["GWP_without_storage_credit_kgCO2e_per_kg_H2"], places=12)
        self.assertAlmostEqual(self.sold["GWP_kgCO2e_per_kg_H2"],
                               14.243019 - self.sold["GWP_inherited_stored_carbon_credit_kgCO2e_per_kg_H2"], delta=1e-6)

    def test_physical_flows_and_msp_unchanged_by_accounting(self):
        self.assertAlmostEqual(self.sold["H2_t_per_yr"], 2953.563, delta=1e-3)
        self.assertAlmostEqual(self.sold["MSP_USD_per_kg_H2"], 3.229398, delta=1e-6)
        self.assertAlmostEqual(self.kept["MSP_USD_per_kg_H2"], 5.326657, delta=1e-6)
        dry = float(self.s["caco3_cake"].F_mass - self.s["caco3_cake"].imass["Water"])
        self.assertAlmostEqual(float(self.s["caco3_cake"].imass["CaCO3"]) / dry, 0.82545, delta=1e-5)

    def test_carbon_closes_and_wash_carbonate_is_not_credited(self):
        rows = inv.get_att_carbon_fate(self.sys)
        inp = sum(r["kg_C_per_h_at_sim_basis"] for r in rows if r["direction"] == "input")
        out = sum(r["kg_C_per_h_at_sim_basis"] for r in rows if r["direction"] == "output")
        self.assertAlmostEqual(out, inp, delta=1e-6 * inp)
        feed = self.s["att_sargassum_feed"]
        self.assertEqual(float(feed.imol["CaCO3"]) if "CaCO3" in feed.chemicals else 0.0, 0.0)   # all carbonate is biogenic
        self.assertNotIn("f2_wash_liquor", lca._LCA["waste_management"]["landfill_streams"])
        self.assertGreater(float(self.s["f2_wash_liquor"].imass["Na2CO3"]), 0.0)


if __name__ == "__main__":
    unittest.main()
