"""ATT Scenario 1 parameters reach the model (1 kg/h dry basis): NaOH on the dry feed, gas yields on the daf feed,
measured CO2 kept (no override, no CO2 closure), C1 conversion 0.88, residual carbon to char, no SaBRe import."""
import unittest
import warnings

from biorefineries.ATT.analyses import scenarios as scen


class TestATTScenario1Parameters(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        warnings.filterwarnings("ignore")
        cls.sys = scen.create(scen.ATT_S1, dry_kgph=1.0, hxn=False, washing="washing_off", f1_wash=False, caco3_dry=False, ash_salts=False, char_yield=0.0, ree_recovery=False)
        cls.u = {unit.ID: unit for unit in cls.sys.units}


    def test_u2_elemental_diagnostics(self):
        # Existing standards, unchanged: C, H, O, electrons and mass close with the lumped residue; the U2 duty
        # stays PROVISIONAL because it rests on the assumed residue composition and thermo.
        rows = {r["check"]: r for r in self.u["U2"].balance_checks()}
        for check in ("Elemental residual C, products - feed [mmol C/g daf]",
                      "Elemental residual O, products - feed [mmol O/g daf]",
                      "H residual, identified products - feed (+ = excess, unresolved) [mmol H/g daf]",
                      "Electron residual, gases + residual product - feed organics [mmol e-/g daf]",
                      "Mass balance error / inlet"):
            self.assertEqual(rows[check]["status"], "PASS", check)
        self.assertTrue(rows["U2 process heat duty [MJ/kg dry]"]["status"].startswith("PROVISIONAL"))
        U2 = self.u["U2"]
        out = {e: 0.0 for e in ("C", "H", "O", "N", "S", "Na")}
        inn = dict(out)
        for stream, acc in ((U2.ins[0], inn), (U2.outs[0], out), (U2.outs[1], out)):
            for c in stream.chemicals:
                n = float(stream.imol[c.ID])
                for e in acc:
                    acc[e] += n * c.atoms.get(e, 0.0)
        for e in inn:
            self.assertAlmostEqual(out[e], inn[e], delta=1e-9 * max(1.0, inn[e]), msg=e)


if __name__ == "__main__":
    unittest.main()
