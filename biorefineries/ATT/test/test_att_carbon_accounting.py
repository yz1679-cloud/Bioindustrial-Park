"""Carbon accounting of ATT S1.

Baseline (att_tea.yaml caco3_sales.enabled false; att_lca.yaml inherited accounting, char credited): the CaCO3 cakes are
disposed and ALL carbon in landfilled solids (CaCO3, Na2CO3, the lumped residue = ATT char) earns the storage credit.

Option (``sales_option()``): CaCO3 sales and the conservative accounting, where the LCA follows the TEA disposition of
the cakes, sold CaCO3 never earns a storage credit and soluble carbonate and the residue are not credited. The inherited
credit stays available as a comparison. In both, the carbon of the plant closes."""
import unittest
import warnings

from biorefineries.ATT.analyses import inventory as inv
from biorefineries.ATT.analyses import lca
from biorefineries.ATT.analyses import scenarios as scen
from biorefineries.ATT.analyses import tea as tea_mod
from biorefineries.ATT.analyses.breakdown import build_att_breakdown
from biorefineries.ATT.test._options import sales_option

C_PER_CACO3 = 12.011 / 100.0869
LIME_OF_CAKE = {"caco3_cake": "lime", "scrubber_cake": "scrubber_lime"}    # the lime whose CaCO3 a cake carries


def lime_carbon(streams, ID):
    """kg C/h of the waste-lime CaCO3 in cake ``ID`` (fossil / non-Sargassum carbon: never credited)."""
    lime = LIME_OF_CAKE.get(ID)
    return float(streams[lime].get_atomic_flow("C")) * 12.011 if lime in streams else 0.0


class TestBaselineAccounting(unittest.TestCase):
    """The baseline: cakes disposed, all landfilled carbon (incl. the residue) credited."""

    @classmethod
    def setUpClass(cls):
        warnings.filterwarnings("ignore")
        cls.sys = scen.create(scen.ATT_S1)
        cls.s = inv._streams(cls.sys)
        cls.h2 = float(cls.s["h2_product"].imass["H2"])
        cls.t = build_att_breakdown("att_s1", sys=cls.sys)["summary"]

    def test_baseline_is_inherited_with_the_residue_credited(self):
        self.assertEqual(lca._LCA["carbon_storage"]["carbonate_storage_accounting"], "inherited")
        self.assertTrue(lca._LCA["carbon_storage"]["credit_char_carbon"])
        self.assertEqual(self.t["carbonate_storage_accounting"], "inherited")
        self.assertEqual(self.t["CaCO3_sales"], "off")
        self.assertEqual(self.t["CaCO3_sold_t_per_yr"], 0.0)

    def test_credit_is_all_carbon_of_the_landfilled_solids(self):
        landfilled = sum(float(self.s[ID].get_atomic_flow("C")) * 12.011 - lime_carbon(self.s, ID)
                         for ID in lca._LCA["waste_management"]["landfill_streams"] if ID in self.s
                         and self.s[ID] in self.sys.products)       # Sargassum carbon only: not the lime's CaCO3
        self.assertAlmostEqual(lca._stored_carbon_kgph(self.sys), landfilled, places=9)
        self.assertAlmostEqual(self.t["GWP_stored_carbon_credit_in_net_kgCO2e_per_kg_H2"],
                               -landfilled * 44.0095 / 12.011 / self.h2, places=9)
        # the residue (ATT char) is credited: it is about half of the credited carbon
        residue = lca._stored_carbon_kgph(self.sys, include_char=True) - lca._stored_carbon_kgph(self.sys, include_char=False)
        self.assertGreater(residue, 0.4 * landfilled)
        self.assertLess(residue, 0.6 * landfilled)

    def test_carbon_closes(self):
        rows = inv.get_att_carbon_fate(self.sys)
        inp = sum(r["kg_C_per_h_at_sim_basis"] for r in rows if r["direction"] == "input")
        out = sum(r["kg_C_per_h_at_sim_basis"] for r in rows if r["direction"] == "output")
        self.assertAlmostEqual(out, inp, delta=1e-6 * inp)


class TestCarbonateAccounting(unittest.TestCase):
    """The option: CaCO3 sales and conservative carbon accounting (values in BioSTEAM 2.54.0)."""

    @classmethod
    def setUpClass(cls):
        warnings.filterwarnings("ignore")
        cls._option = sales_option()
        cls._option.__enter__()
        cls.sys = scen.create(scen.ATT_S1)
        cls.s = inv._streams(cls.sys)
        cls.h2 = float(cls.s["h2_product"].imass["H2"])
        cls.sold = build_att_breakdown("att_s1", sys=cls.sys)["summary"]
        cls.kept = build_att_breakdown("att_s1", sys=cls.sys, f2_sales=False)["summary"]
        build_att_breakdown("att_s1", sys=cls.sys)                       # leave the option applied

    @classmethod
    def tearDownClass(cls):
        cls._option.__exit__(None, None, None)

    def caco3_C(self, ID):
        """Sargassum-derived CaCO3 carbon of cake ``ID`` [kg C/h] (the waste lime's CaCO3 carbon excluded)."""
        return float(self.s[ID].imass["CaCO3"]) * C_PER_CACO3 - lime_carbon(self.s, ID)

    def test_option_is_conservative(self):
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
            sold_C = sum(acc[ID]["sold_caco3_kgph"] * C_PER_CACO3 * self.caco3_C(ID)
                         / (float(self.s[ID].imass["CaCO3"]) * C_PER_CACO3) for ID in acc)
            self.assertAlmostEqual(sold_C + lca._stored_carbon_kgph(self.sys, caco3_sales=sales), total, places=9)

    def test_inherited_comparison_is_preserved(self):
        # the earlier treatment: all non-residue carbon of the landfilled cakes, sold or not
        expected = sum(float(self.s[ID].get_atomic_flow("C")) * 12.011 - lime_carbon(self.s, ID)
                       for ID in ("caco3_cake", "scrubber_cake", "ash_residue_cake")) - sum(
            float(self.s["ash_residue_cake"].imol[r]) * self.s["ash_residue_cake"].chemicals[r].atoms["C"] * 12.011
            for r in lca._LCA["carbon_storage"]["provisional_residue_species"] if r in self.s["ash_residue_cake"].chemicals)
        self.assertAlmostEqual(lca._stored_carbon_kgph(self.sys, accounting="inherited", include_char=False), expected,
                               places=9)
        for s in (self.sold, self.kept):        # independent of the disposition, as before
            self.assertAlmostEqual(s["GWP_inherited_carbonate_credit_kgCO2e_per_kg_H2"], 14.721765, delta=1e-6)
            self.assertAlmostEqual(s["GWP_kgCO2e_per_kg_H2"] - s["GWP_stored_carbon_credit_in_net_kgCO2e_per_kg_H2"],
                                   s["GWP_without_storage_credit_kgCO2e_per_kg_H2"], places=12)
        self.assertAlmostEqual(self.sold["GWP_kgCO2e_per_kg_H2"],
                               14.721765 - self.sold["GWP_inherited_stored_carbon_credit_kgCO2e_per_kg_H2"], delta=1e-6)

    def test_physical_flows_and_msp_unchanged_by_accounting(self):
        self.assertAlmostEqual(self.sold["H2_t_per_yr"], 2953.563, delta=1e-3)
        self.assertAlmostEqual(self.sold["MSP_USD_per_kg_H2"], 2.892374, delta=1e-6)
        self.assertAlmostEqual(self.kept["MSP_USD_per_kg_H2"], 5.097195, delta=1e-6)
        dry = float(self.s["caco3_cake"].F_mass - self.s["caco3_cake"].imass["Water"])
        self.assertAlmostEqual(float(self.s["caco3_cake"].imass["CaCO3"]) / dry, 0.80570, delta=1e-5)   # washed cake, with the lime impurities

    def test_carbon_closes_and_wash_carbonate_is_not_credited(self):
        rows = inv.get_att_carbon_fate(self.sys)
        inp = sum(r["kg_C_per_h_at_sim_basis"] for r in rows if r["direction"] == "input")
        out = sum(r["kg_C_per_h_at_sim_basis"] for r in rows if r["direction"] == "output")
        self.assertAlmostEqual(out, inp, delta=1e-6 * inp)
        feed = self.s["att_sargassum_feed"]
        self.assertEqual(float(feed.imol["CaCO3"]) if "CaCO3" in feed.chemicals else 0.0, 0.0)   # all carbonate is biogenic
        self.assertNotIn("f2_wash_liquor", lca._LCA["waste_management"]["landfill_streams"])
        self.assertGreater(float(self.s["f2_wash_liquor"].imass["Na2CO3"]), 0.0)     # dissolved carbonate, recycled


if __name__ == "__main__":
    unittest.main()
