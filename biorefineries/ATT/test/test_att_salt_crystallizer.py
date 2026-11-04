"""The ash split, the char yield and the salt crystallizer of ATT S1 / S2 (att.yaml feed_preparation.ash_split, downstream.char and
downstream.salt_crystallizer): the seaweed ash is insoluble minerals + NaCl/KCl; the insoluble char is 0.15 g per g of dry feed; the
lumped residual carbon beyond the char leaves untracked; the salts leave in the salt cake of XL1."""
import unittest
import warnings

import numpy as np

from biorefineries.ATT.analyses import inventory as inv
from biorefineries.ATT.analyses import scenarios as scen
from biorefineries.ATT.analyses import tea as tea_mod
from biorefineries.ATT.units._att import _SARGASSUM_DRY_IDS


class TestAshCharSalt(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        warnings.filterwarnings("ignore")
        cls.sys = scen.create(ree_recovery=False)
        cls.u, cls.s = inv._units(cls.sys), inv._streams(cls.sys)
        cls.dry = inv._dry_feed_kgph(cls.sys)

    def test_ash_split_keeps_the_ash_and_adds_the_salts(self):
        feed = self.s["att_sargassum_feed"]
        ash = float(feed.imass["Ash"] + feed.imass["NaCl"] + feed.imass["KCl"])
        self.assertAlmostEqual(ash / self.dry, 0.3207, places=6)                       # the ash of the presscake is unchanged
        self.assertAlmostEqual(float(feed.imass["Ash"]) / ash, 0.3838, places=4)
        self.assertAlmostEqual(float(feed.get_atomic_flow("K")) / float(feed.get_atomic_flow("Na")), 9.06 / 7.26, delta=0.01)
        self.assertAlmostEqual(float(feed.get_atomic_flow("Cl")), float(feed.get_atomic_flow("Na") + feed.get_atomic_flow("K")), places=9)

    def test_na2co3_is_made_from_the_naoh_only(self):
        U2 = self.u["U2"]
        naoh_in = float(U2.ins[0].imol["NaOH"] + 2.0 * U2.ins[0].imol["Na2CO3"])
        made = float(U2.outs[1].imol["Na2CO3"] + 0.5 * U2.outs[1].imol["NaOH"])
        self.assertAlmostEqual(made, 0.5 * naoh_in, places=9)                           # NaCl sodium is not a NaOH source

    def test_insoluble_char_is_0_15_g_per_g_dry_feed(self):
        char = self.s["char_residue"] if "char_residue" in self.s else self.u["RS1"].outs[0]
        solids = sum(float(char.imass[ID]) for ID in ("Ash", "Char", "CharN", "CharS"))
        self.assertAlmostEqual(solids / self.dry, 0.15, places=9)
        self.assertEqual(float(char.imass["ResidueCH"] + char.imass["ResidueCHO"]), 0.0)

    def test_rs1_conserves_c_h_and_o(self):
        RS1 = self.u["RS1"]
        for element in ("C", "H", "O", "N", "S", "Na", "K", "Cl"):
            fed = float(RS1.ins[0].get_atomic_flow(element))
            out = sum(float(s.get_atomic_flow(element)) for s in RS1.outs)
            self.assertAlmostEqual(out, fed, places=9, msg=element)
        lost = self.s["untracked_organics"]
        self.assertGreater(float(lost.F_mass), 0.0)
        self.assertEqual(lost.price, 0.0)                                               # no revenue and no disposal cost
        self.assertNotIn("untracked_organics", [s.ID for s in self.sys.feeds])

    def test_salts_leave_in_the_salt_cake(self):
        feed = self.s["att_sargassum_feed"]
        cake = self.s["salt_cake"]
        for element in ("K", "Cl"):
            fed = float(feed.get_atomic_flow(element))
            out = sum(float(s.get_atomic_flow(element)) for s in self.sys.products)
            self.assertAlmostEqual(out, fed, delta=1e-6 * fed, msg=element)           # the plant balance of K and Cl closes
        salt_in = float(feed.imass["NaCl"] + feed.imass["KCl"])
        salt_out = float(cake.imass["NaCl"] + cake.imass["KCl"])
        self.assertGreater(salt_out, 0.85 * salt_in)                                    # most of the salt leaves in the cake (99 % per pass)
        self.assertAlmostEqual(float(cake.F_mass) - salt_out - float(cake.imass["Water"] + cake.imass["NaOH"] + cake.imass["Na2CO3"]), 0.0, places=6)
        tea_mod.evaluate_att_tea(self.sys, inv.get_att_cost_estimates(self.sys), **scen.tea_config())      # sets the stream prices
        self.assertLess(cake.price, 0.0)                                                # disposed at the solid-waste price (a cost)
        self.assertEqual(self.s["untracked_organics"].price, 0.0)
        self.assertEqual(self.u["XL1"].outs[0], self.u["M1"].ins[1])
        self.assertGreater(float(self.u["XL1"].installed_cost), 0.0)

    def test_switches_off_reproduce_the_lumped_flowsheet(self):
        old = scen.create(ash_salts=False, char_yield=0.0, ree_recovery=False)
        ids = [x.ID for x in old.units]
        self.assertNotIn("RS1", ids)
        self.assertNotIn("XL1", ids)
        s = inv._streams(old)
        self.assertEqual(float(s["att_sargassum_feed"].imass["NaCl"]), 0.0)
        res = s["ash_residue_cake"]
        self.assertGreater(float(res.imass["ResidueCH"] + res.imass["ResidueCHO"]), 0.0)   # U2's lumped residue goes to F1 again

    def test_s2_inherits_the_crystallizer(self):
        s2 = scen.create(scen.ATT_S2, ree_recovery=False)
        self.assertIn("XL1", [x.ID for x in s2.units])
        self.assertIn("RS1", [x.ID for x in s2.units])
        np.testing.assert_allclose(float(inv._units(s2)["XL1"].installed_cost), float(self.u["XL1"].installed_cost), rtol=1e-6)


if __name__ == "__main__":
    unittest.main()
