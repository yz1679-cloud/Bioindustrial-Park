"""REE recovery from the ATT char (att.yaml downstream.ree_recovery, switch default on): HCl leach and oxalate precipitation of the washed
char cake (LC1), roast of the oxalate precipitate into the REE product (RO1), spent leachate recycled to the dissolver D1. S2 inherits it from S1."""
import unittest
import warnings

from biorefineries.ATT.analyses import inventory as inv
from biorefineries.ATT.analyses import scenarios as scen
from biorefineries.ATT.analyses import tea as tea_mod


class TestREERecovery(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        warnings.filterwarnings("ignore")
        cls.sys = scen.create(ree_recovery=True)
        cls.u, cls.s = inv._units(cls.sys), inv._streams(cls.sys)
        cls.dry = inv._dry_feed_kgph(cls.sys)

    def test_default_is_on_and_can_be_switched_off(self):
        default = scen.create()
        self.assertIn("LC1", [x.ID for x in default.units])
        self.assertIn("ree_product", inv._streams(default))
        base = scen.create(ree_recovery=False)
        self.assertNotIn("LC1", [x.ID for x in base.units])
        self.assertNotIn("ree_product", inv._streams(base))
        self.assertEqual(float(inv._streams(base)["att_sargassum_feed"].imass["REO"]), 0.0)

    def test_seaweed_ree_is_carved_out_of_the_insoluble_ash(self):
        feed = self.s["att_sargassum_feed"]
        reo = float(feed.imass["REO"])
        self.assertAlmostEqual(reo / self.dry, 737.0e-6 * 1.169, places=9)
        ash = float(feed.imass["Ash"] + feed.imass["NaCl"] + feed.imass["KCl"] + feed.imass["REO"])
        self.assertAlmostEqual(ash / self.dry, 0.3207, places=6)                          # the ash of the presscake is unchanged

    def test_reagent_doses_follow_the_lab_per_g_of_char(self):
        LC1 = self.u["LC1"]
        cake = LC1.ins[0]
        solids = sum(float(cake.imass[c.ID]) for c in cake.chemicals if c.ID not in ("Water", "Na2CO3", "NaOH", "NaCl", "KCl"))
        self.assertAlmostEqual(float(self.s["fresh_hcl"].imol["HCl"]), 0.5e-3 * solids, places=9)            # 5 mL of 0.1 M HCl per g
        self.assertAlmostEqual(float(self.s["fresh_hcl"].imass["HCl"] / self.s["fresh_hcl"].F_mass), 0.31, places=9)
        self.assertAlmostEqual(float(self.s["fresh_oxalic_acid"].imol["OxalicAcid"]), 0.042e-3 * solids, places=9)
        liquor = float(self.s["fresh_hcl"].F_mass) + LC1.water_demand_kgph(solids) - 0.42 * solids              # leach liquor
        self.assertAlmostEqual(liquor, 5.0 * solids, places=6)

    def test_product_is_60_percent_of_the_wastewater_ree_at_the_target_grade(self):
        product, residue = self.s["ree_product"], self.s["ash_residue_cake"]
        reo_water = 1.4 / 2.5 * 1e-3 * self.dry * 1.169                                  # 1.4 mg TREE/L at 2.5 g seaweed/L, as REO
        self.assertAlmostEqual(float(product.imass["REO"]), 0.6 * reo_water, places=9)
        self.assertAlmostEqual(float(product.imass["REO"] / product.F_mass), 0.0131, places=6)
        self.assertLess(0.6, self.u["LC1"]._stoich_ceiling)                              # the oxalate dose does not limit it
        cake_reo = float(self.u["LC1"].ins[0].imass["REO"])
        self.assertAlmostEqual(float(product.imass["REO"] + residue.imass["REO"]), cake_reo, places=9)    # the rest stays in the leached char
        self.assertEqual(float(self.s["spent_leachate"].imass["REO"]), 0.0)

    def test_plant_balances_of_k_and_cl_still_close(self):
        for element in ("K", "Cl"):
            fed = sum(float(s.get_atomic_flow(element)) for s in self.sys.feeds)
            out = sum(float(s.get_atomic_flow(element)) for s in self.sys.products)
            self.assertAlmostEqual(out, fed, delta=1e-6 * fed, msg=element)               # the HCl chloride leaves in the salt cake

    def test_leachate_is_recycled_and_uses_the_surplus_condensate(self):
        self.assertNotIn(self.s["spent_leachate"], self.sys.products)
        self.assertIs(self.u["D1"].ins[-1], self.s["spent_leachate"])
        self.assertAlmostEqual(float(self.s["leach_water"].F_mass), 0.0, places=6)         # the condensate is used first
        self.assertGreater(float(self.s["condensate_to_leach"].F_mass), 0.0)

    def test_roaster_burns_only_the_oxalate_precipitate(self):
        feed, product, exhaust = self.u["RO1"].ins[0], self.u["RO1"].outs[0], self.u["RO1"].outs[1]
        self.assertEqual(float(feed.imass["Char"] + feed.imass["CharN"]), 0.0)           # the leached char is not roasted
        self.assertEqual(float(product.imass["OxalicAcid"] + product.imass["Water"]), 0.0)
        self.assertAlmostEqual(float(exhaust.get_atomic_flow("C") + product.get_atomic_flow("C")), float(feed.get_atomic_flow("C")), places=9)
        self.assertAlmostEqual(float(product.imass["REO"]), float(feed.imass["REO"]), places=9)

    def test_leached_char_is_the_residue_product(self):
        self.assertIn(self.s["ash_residue_cake"], self.sys.products)
        self.assertGreater(float(self.s["ash_residue_cake"].imass["Char"]), 0.0)

    def test_product_is_sold_on_its_reo_content(self):
        tea_mod.evaluate_att_tea(self.sys, inv.get_att_cost_estimates(self.sys), **scen.tea_config())
        product = self.s["ree_product"]
        self.assertAlmostEqual(product.price, 35.0 * float(product.imass["REO"]) / float(product.F_mass), places=9)
        self.assertGreater(self.s["fresh_hcl"].price, 0.0)

    def test_s2_inherits_it(self):
        s2 = scen.create(scen.ATT_S2, ree_recovery=True)
        self.assertIn("LC1", [x.ID for x in s2.units])
        self.assertIn("RO1", [x.ID for x in s2.units])


if __name__ == "__main__":
    unittest.main()
