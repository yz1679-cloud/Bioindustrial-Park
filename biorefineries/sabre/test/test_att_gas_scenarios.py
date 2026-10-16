"""Side-by-side TEA/LCA contribution analysis of the gas-yield scenarios (reporting only)."""
import unittest
import warnings

from biorefineries.sabre.analyses.att.scenarios import build_att_gas_scenario_tables


# Relative tolerance on the expected headline values (results shift slightly between
# library versions and machines).
RTOL = 0.01


class TestATTGasScenarios(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        warnings.filterwarnings("ignore")
        cls.t = build_att_gas_scenario_tables()

    def test_all_qc_checks_pass(self):
        # The D7 cross-checks need comparison/D7 from run_att_final; without it they are NOT CHECKED, never PASS.
        qc = self.t["14_QC_Checks"]
        not_checked = [r for r in qc if r["status"].startswith("NOT CHECKED")]
        self.assertTrue(all(r["check"].startswith("Equals comparison/D7") for r in not_checked), not_checked)
        self.assertIn(len(not_checked), (0, 12))
        failed = [r for r in qc if r["status"] != "PASS" and r not in not_checked]
        self.assertEqual(failed, [])

    def test_headline_results(self):
        rows = {r["scenario"]: r for r in self.t["07_TEA_Ref_vs_Case_A"]}
        for sid, (msp, msp_a) in {"Gas-C": (15.62, 17.91), "Gas-Cprime": (12.47, 14.32), "Gas-A": (9.54, 10.93)}.items():
            self.assertAlmostEqual(rows[sid]["MSP_TEA_reference"], msp, delta=RTOL * msp)
            self.assertAlmostEqual(rows[sid]["MSP_TEA_CaseA_CaCO3_disposal"], msp_a, delta=RTOL * msp_a)

    def test_msp_components_sum_to_msp(self):
        for case in ("Reference", "TEA Case A"):
            for sid in ("Gas-C", "Gas-Cprime", "Gas-A"):
                parts = [r["USD_per_kg_H2"] for r in self.t["F1_MSP_Stack"]
                         if r["scenario"] == sid and r["TEA_case"] == case]
                total = next(r for r in self.t["06_MSP_Breakdown_DCF"] if r["scenario"] == sid
                             and r["TEA_case"].startswith(case) and r["group"] == "TOTAL")
                self.assertAlmostEqual(sum(parts), float(total["basis"].split("= ")[1]), places=5)

    def test_gwp_stack_sums_to_total(self):
        totals = {"Gas-C": 83.28, "Gas-Cprime": 66.33, "Gas-A": 52.30}
        for sid, gwp in totals.items():
            s = sum(r["kgCO2e_per_kg_H2"] for r in self.t["F2_GWP_Stack"] if r["scenario"] == sid)
            self.assertAlmostEqual(s, gwp, delta=RTOL * gwp)


if __name__ == "__main__":
    unittest.main()
