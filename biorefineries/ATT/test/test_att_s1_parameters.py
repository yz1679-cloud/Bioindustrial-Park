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

    def test_residual_carbon_in_lumped_residue(self):
        # Residual carbon -> lumped residual product CH0.5O_b (assumed surrogate), b solved by U2; no Char, no
        # extra gas CO2; nonnegative flows and product water.
        U2 = self.u["U2"]
        res = U2.outs[1]
        self.assertEqual(U2.residual_carbon_fate, "lumped")
        self.assertEqual(float(res.imass["Char"]), 0.0)
        flows = [float(res.imol[ID]) for ID in U2.lumped_residue_IDs]
        self.assertTrue(all(f >= 0.0 for f in flows) and sum(flows) > 0.0)
        self.assertGreaterEqual(float(U2.outs[0].imol["Water"]), 0.0)
        f = U2._residual_product_formula
        self.assertAlmostEqual(f["H"], 0.5, places=12)
        self.assertTrue(0.0 <= f["O"] <= 2.0)
        self.assertEqual(U2._unresolved_element_kmolph, {})

    def test_c1_conversion(self):
        C1 = self.u["C1"]
        self.assertEqual(C1.conversion, 0.88)
        n_in = float(C1.ins[0].imol["Na2CO3"] + C1.ins[1].imol["Na2CO3"])
        self.assertAlmostEqual(1.0 - float(C1.outs[0].imol["Na2CO3"]) / n_in, 0.88, places=9)
        self.assertAlmostEqual(float(C1.ins[1].imol["CaOH2"]), 1.1 * n_in, places=9)

    def test_no_sabre_import(self):
        self.assertEqual([m for m in sys.modules if m.startswith("biorefineries.sabre")], [])

    def test_flowsheet_unchanged(self):
        # ATT Scenario 1 flowsheet of commit 76fc5527 (units in path order, boundary streams)
        self.assertEqual([u.ID for u in self.sys.units],
                         ["D0", "M1", "U2", "U3HX", "U3C", "SCRUB", "F3", "U3D", "U3K", "RC1", "W3", "SW", "D1", "F1",
                          "C1", "F2", "SP1", "EC1"])
        self.assertEqual(sorted(s.ID for s in self.sys.feeds),
                         ["att_sargassum_feed", "dissolution_water", "dryer_air", "dryer_backup_fuel", "fresh_naoh_solid",
                          "lime", "scrubber_lime", "scrubber_makeup_water", "u3_tail_gas"])
        self.assertEqual(sorted(s.ID for s in self.sys.products),
                         ["ash_residue_cake", "caco3_cake", "dryer_emissions", "dryer_exhaust", "excess_condensate",
                          "h2_product", "liquor_purge", "scrubber_cake", "u3_dryer_removed_water"])
        self.assertEqual(scen.dry_feed_kgph(), 5029.17)

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

    def test_residue_carbon_not_in_net_storage_credit(self):
        from biorefineries.ATT.analyses.att import inventory as inv, lca
        s = inv._streams(self.sys)
        cake = s["ash_residue_cake"]
        char_C = sum(float(cake.imol[ID]) * cake.chemicals[ID].atoms["C"]
                     for ID in lca._LCA["carbon_storage"]["provisional_residue_species"]) * 12.011
        self.assertGreater(char_C, 0.0)
        self.assertAlmostEqual(lca._stored_carbon_kgph(self.sys, include_char=True) - lca._stored_carbon_kgph(self.sys),
                               char_C, places=12)
        self.assertFalse(lca._LCA["carbon_storage"]["credit_char_carbon"])


if __name__ == "__main__":
    unittest.main()
