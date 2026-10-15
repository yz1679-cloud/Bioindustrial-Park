"""Side-by-side TEA/LCA contribution analysis of the gas-yield scenarios (reporting only)."""
import unittest
import warnings

from biorefineries.sabre.analyses._att_gas_scenarios import build_att_gas_scenario_tables


class TestATTGasScenarios(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        warnings.filterwarnings("ignore")
        cls.t = build_att_gas_scenario_tables()

    def test_all_qc_checks_pass(self):
        failed = [r for r in self.t["14_QC_Checks"] if r["status"] != "PASS"]
        self.assertEqual(failed, [])

    def test_headline_results(self):
        rows = {r["scenario"]: r for r in self.t["07_TEA_Ref_vs_Case_A"]}
        for sid, (msp, msp_a) in {"Gas-C": (15.99, 18.28), "Gas-Cprime": (12.83, 14.67), "Gas-A": (9.71, 11.09)}.items():
            self.assertAlmostEqual(rows[sid]["MSP_TEA_reference"], msp, delta=0.006)
            self.assertAlmostEqual(rows[sid]["MSP_TEA_CaseA_CaCO3_disposal"], msp_a, delta=0.006)

    def test_msp_components_sum_to_msp(self):
        for case in ("Reference", "TEA Case A"):
            for sid in ("Gas-C", "Gas-Cprime", "Gas-A"):
                parts = [r["USD_per_kg_H2"] for r in self.t["F1_MSP_Stack"]
                         if r["scenario"] == sid and r["TEA_case"] == case]
                total = next(r for r in self.t["06_MSP_Breakdown_DCF"] if r["scenario"] == sid
                             and r["TEA_case"].startswith(case) and r["group"] == "TOTAL")
                self.assertAlmostEqual(sum(parts), float(total["basis"].split("= ")[1]), places=6)

    def test_gwp_stack_sums_to_total(self):
        totals = {"Gas-C": 89.5, "Gas-Cprime": 72.4, "Gas-A": 55.0}
        for sid, gwp in totals.items():
            s = sum(r["kgCO2e_per_kg_H2"] for r in self.t["F2_GWP_Stack"] if r["scenario"] == sid)
            self.assertAlmostEqual(s, gwp, delta=0.06)


if __name__ == "__main__":
    unittest.main()
