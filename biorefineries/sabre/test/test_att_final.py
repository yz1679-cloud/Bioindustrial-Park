"""Final ATT results: experimental data intact, ratio-preserving baseline, lab LCA labeled."""
import os
import unittest
import warnings

from biorefineries.sabre.analyses.att import experiment as exp
from biorefineries.sabre.analyses.att.final import build_att_final_results


class TestATTExperiment(unittest.TestCase):

    def test_measured_yields_unchanged(self):
        d = exp.EXP["experimental_results"]["cases"]["Ni-CatATT"]
        self.assertEqual(d["H2"], 66.72842505487348)
        self.assertEqual(d["CH4"], 8.768738649553573)
        self.assertEqual(d["CO"], 0.1648486662946429)
        self.assertEqual(d["CO2"], 0.1865389341517857)

    def test_workbook_transcription(self):
        rows = exp.verify_att_experiment_workbook()
        if not os.path.exists(exp.EXP["source_workbook"]["local_path"]):
            self.skipTest("source workbook not available")
        self.assertTrue(all(r["status"] == "PASS" for r in rows))

    def test_lab_lca_is_labeled_screening(self):
        rows = exp.get_att_lab_screening_lca()
        results = [r for r in rows if r["category"] == "Result" and r["item"].startswith("Screening")]
        self.assertTrue(results and all("SCREENING" in r["status"] for r in results))
        self.assertTrue(any(r["status"] == "NOT REPORTED" for r in rows))


class TestATTFinal(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        warnings.filterwarnings("ignore")
        cls.t = build_att_final_results()

    def test_baseline_preserves_experimental_ratios(self):
        for r in self.t["D1_Gas_Yields_and_Ratios"][:4]:
            self.assertAlmostEqual(r["uniform_redox_scaling_ratio_to_H2"], r["experimental_ratio_to_H2"], places=12)
            self.assertAlmostEqual(r["uniform_redox_scaling_deviation"], self.t["D1_Gas_Yields_and_Ratios"][0][
                "uniform_redox_scaling_deviation"], places=12)

    def test_mass_and_element_audit(self):
        for r in self.t["C2_Mass_Element_Audit"]:
            self.assertLess(abs(r["value"]), 1e-8, r["item"])

    def test_scale_factor_is_maximal_at_full_conversion(self):
        rows = {r["assumption"]: r["s"] for r in self.t["D2_Scale_Factor_Feasibility"]}
        self.assertGreater(rows["char formula CH0.5O0.1 (baseline char)"], rows["NaOH -> Na2CO3 conversion 0.9"])


    def test_gas_yield_scenarios_sheet(self):
        rows = {r["closure"]: r for r in self.t["D7_Gas_Yield_Scenarios"]}
        base, mid, top = rows["uniform_redox_scaling"], rows["uniform_co2_free"], rows["h2_measured_ch4_max"]
        self.assertEqual(base["status"], "BASELINE")
        self.assertTrue(base["H2_product_kg_per_kg_dry"] < mid["H2_product_kg_per_kg_dry"]
                        < top["H2_product_kg_per_kg_dry"])
        self.assertTrue(base["MSP_TEA_reference_USD_per_kg_H2"] > mid["MSP_TEA_reference_USD_per_kg_H2"]
                        > top["MSP_TEA_reference_USD_per_kg_H2"])
        self.assertEqual([base["scenario"], mid["scenario"], top["scenario"]], ["Gas-C", "Gas-Cprime", "Gas-A"])
        self.assertAlmostEqual(base["char_carbon_kg_C_per_kg_dry"],
                               base["char_mass_kg_per_kg_dry"] * base["char_carbon_mass_fraction"], places=12)
        self.assertAlmostEqual(base["char_carbon_mass_fraction"], 0.851, places=3)
        for r in rows.values():
            self.assertTrue(r["offgas_fate"].startswith("UNRESOLVED"))
            self.assertLess(abs(r["mass_relative_error"]), 1e-8)
            self.assertLess(r["max_element_relative_error"], 1e-8)


if __name__ == "__main__":
    unittest.main()
