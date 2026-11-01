"""ATT Scenario 1 parameters reach the model (1 kg/h dry basis): NaOH on the dry feed, gas yields on the daf feed,
measured CO2 kept (no override, no CO2 closure), C1 conversion 0.88, residual carbon to char, no SaBRe import."""
import sys
import unittest
import warnings

from biorefineries.ATT.analyses.att import scenarios as scen


class TestATTScenario1Parameters(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        warnings.filterwarnings("ignore")
        cls.sys = scen.create(scen.ATT_S1, dry_kgph=1.0, hxn=False)
        cls.u = {unit.ID: unit for unit in cls.sys.units}

    def test_spec(self):
        s = scen.ATT_S1
        self.assertEqual((s["configuration"], s["psa"], s["scrubber"], s["lime"]), ("presscake", False, True, "waste"))
        self.assertEqual(s["naoh_kg_per_kg_dry"], 1.0)
        self.assertEqual(s["gas_yield_mmol_per_g_daf"], {"H2": 54.15, "CH4": 0.60, "CO": 0.0, "CO2": 0.77})
        self.assertEqual(s["dry_feed_kgph"], 5029.17)
        self.assertFalse(hasattr(scen, "dose"))

    def test_feed_and_d0(self):
        U2, D0 = self.u["U2"], self.u["D0"]
        self.assertAlmostEqual(U2._dry_sargassum_kgph, 1.0, places=9)
        self.assertAlmostEqual(U2._daf_sargassum_kgph, 1.0 - 0.3207, places=9)
        out = D0.outs[0]
        self.assertAlmostEqual(float(out.imass["Water"]) / float(out.F_mass), 0.5, places=6)
        self.assertNotIn("P1", self.u)

    def test_naoh_on_dry_basis(self):
        M1 = self.u["M1"]
        self.assertAlmostEqual(M1._required_gross_naoh_kgph, 1.0, places=9)
        self.assertAlmostEqual(M1._fresh_naoh_makeup_kgph + M1._recovered_naoh_kgph, 1.0, places=9)
        self.assertAlmostEqual(float(self.u["U2"].ins[0].imass["NaOH"]), 1.0, places=6)

    def test_gas_yields_on_daf_basis_and_co2_kept(self):
        U2 = self.u["U2"]
        y = {ID: float(U2.outs[0].imol[ID]) * 1e3 / U2._daf_sargassum_kgph for ID in ("H2", "CH4", "CO", "CO2")}
        for ID, v in {"H2": 54.15, "CH4": 0.60, "CO": 0.0, "CO2": 0.77}.items():
            self.assertAlmostEqual(y[ID], v, places=9)
        self.assertAlmostEqual(float(U2.outs[0].imol["H2"]) * 1e3, 54.15 * 0.6793, places=6)   # mmol per g dry check
        self.assertAlmostEqual(y["H2"] / sum(y.values()), 54.15 / 55.52, places=9)          # 97.53 mol %

    def test_residual_carbon_in_char(self):
        U2 = self.u["U2"]
        self.assertEqual(U2.residual_carbon_fate, "char")
        self.assertGreater(float(U2.outs[1].imass["Char"]), 0.0)
        self.assertNotIn("C", U2._unresolved_element_kmolph)

    def test_c1_conversion(self):
        C1 = self.u["C1"]
        self.assertEqual(C1.conversion, 0.88)
        n_in = float(C1.ins[0].imol["Na2CO3"] + C1.ins[1].imol["Na2CO3"])
        self.assertAlmostEqual(1.0 - float(C1.outs[0].imol["Na2CO3"]) / n_in, 0.88, places=9)
        self.assertAlmostEqual(float(C1.ins[1].imol["CaOH2"]), 1.1 * n_in, places=9)

    def test_no_sabre_import(self):
        self.assertEqual([m for m in sys.modules if m.startswith("biorefineries.sabre")], [])


if __name__ == "__main__":
    unittest.main()
