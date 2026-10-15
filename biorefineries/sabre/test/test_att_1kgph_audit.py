"""ATT 1 kg/h audit: actual small-scale simulation, closed balances, scale comparison."""
import unittest
import warnings

from biorefineries.sabre.analyses._att_1kgph_audit import build_att_1kgph_audit


class TestATT1kgphAudit(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        warnings.filterwarnings("ignore")
        cls.t = build_att_1kgph_audit()

    def test_checks_pass(self):
        for r in self.t["14_Limitations_Checks"]:
            self.assertNotEqual(r.get("status"), "FAIL", r.get("check"))

    def test_actual_1kgph_basis(self):
        m = {r["item"]: r["value"] for r in self.t["06_Mass_Balance_Summary"]}
        self.assertAlmostEqual(m["Dry Sargassum input"], 1.0, places=9)
        self.assertAlmostEqual(m["H2 before PSA"], 0.088068 * 0.5997969, places=6)
        self.assertAlmostEqual(m["NaOH gross into U2"], 1.3094, places=6)

    def test_material_and_heat_scale_independent(self):
        rows = {r["parameter"]: r for r in self.t["12_Compare_Full_Scale"]}
        for k in ("H2 product [kg/kg dry]", "Ca(OH)2 [kg/kg dry]", "U2 utility heat [kJ/kg dry]",
                  "EC1 utility heat [kJ/kg dry]", "LP steam [kg/kg dry]"):
            self.assertLess(abs(rows[k]["relative_difference"]), 1e-8, k)
        self.assertGreater(rows["D0 electricity [kWh/kg dry]"]["relative_difference"], 1.0)

    def test_experimental_gases_separate(self):
        b = {r["item"]: r for r in self.t["01_Basis_Experiment"]}
        self.assertAlmostEqual(b["CH4"]["UCLA_experiment"], 8.768738649553573, places=12)
        self.assertAlmostEqual(b["CH4"]["model_1kgph"] / b["H2"]["model_1kgph"],
                               b["CH4"]["UCLA_experiment"] / b["H2"]["UCLA_experiment"], places=10)


if __name__ == "__main__":
    unittest.main()
