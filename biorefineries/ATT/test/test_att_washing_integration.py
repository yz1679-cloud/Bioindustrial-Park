"""The F2 wash conserves mass and calcium solids."""
import unittest
import warnings
import numpy as np
from biorefineries.ATT.analyses import scenarios as scen, inventory as inv
from biorefineries.ATT.analyses.att_washing import washing_checks


class TestNativeF2Washing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        warnings.filterwarnings("ignore")
        cls.on = scen.create(washing="washing_on", wash_recycle=False, wash_condensate=False, f1_wash=False, caco3_dry=False, ash_salts=False, char_yield=0.0, ree_recovery=False)   # fresh water, liquor to wastewater
        cls.u, cls.s = inv._units(cls.on), inv._streams(cls.on)


    def test_wash_conserves_mass_and_calcium_solids(self):
        for row in washing_checks(self.on):
            self.assertEqual(row["status"], "PASS", row)
        inputs = self.u["F2"].outs[0].mass + self.s["f2_wash_water"].mass
        outputs = self.s["caco3_cake"].mass + self.s["f2_wash_liquor"].mass
        np.testing.assert_allclose(inputs, outputs, rtol=1e-12, atol=1e-8)
        for ID in ("CaCO3", "CaOH2"):
            self.assertAlmostEqual(float(self.s["caco3_cake"].imass[ID]),
                                   float(self.u["F2"].outs[0].imass[ID]), places=8)
            self.assertEqual(float(self.s["f2_wash_liquor"].imass[ID]), 0)


if __name__ == "__main__":
    unittest.main()
