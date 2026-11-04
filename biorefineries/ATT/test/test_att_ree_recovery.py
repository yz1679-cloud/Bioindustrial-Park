"""REE recovery from the ATT char (att.yaml downstream.ree_recovery, switch default on): HCl leach and oxalate precipitation of the washed
char cake (LC1), roast of the oxalate precipitate into the REE product (RO1), spent leachate recycled to the dissolver D1. S2 inherits it from S1."""
import unittest
import warnings

from biorefineries.ATT.analyses import inventory as inv
from biorefineries.ATT.analyses import scenarios as scen


class TestREERecovery(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        warnings.filterwarnings("ignore")
        cls.sys = scen.create(ree_recovery=True)
        cls.u, cls.s = inv._units(cls.sys), inv._streams(cls.sys)
        cls.dry = inv._dry_feed_kgph(cls.sys)


    def test_product_is_60_percent_of_the_wastewater_ree_at_the_target_grade(self):
        product, residue = self.s["ree_product"], self.s["ash_residue_cake"]
        reo_water = 1.4 / 2.5 * 1e-3 * self.dry * 1.169                                  # 1.4 mg TREE/L at 2.5 g seaweed/L, as REO
        self.assertAlmostEqual(float(product.imass["REO"]), 0.6 * reo_water, places=9)
        self.assertAlmostEqual(float(product.imass["REO"] / product.F_mass), 0.0131, places=6)
        self.assertLess(0.6, self.u["LC1"]._stoich_ceiling)                              # the oxalate dose does not limit it
        cake_reo = float(self.u["LC1"].ins[0].imass["REO"])
        self.assertAlmostEqual(float(product.imass["REO"] + residue.imass["REO"]), cake_reo, places=9)    # the rest stays in the leached char
        self.assertEqual(float(self.s["spent_leachate"].imass["REO"]), 0.0)


if __name__ == "__main__":
    unittest.main()
