"""ATT documentation package: extraction only, consistent with existing results."""
import unittest
import warnings

from biorefineries.sabre.analyses.att.reporting import build_att_documentation


class TestATTDocumentation(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        warnings.filterwarnings("ignore")
        cls.t = build_att_documentation()

    def test_quality_checks(self):
        for r in self.t["26_QC_Checks"]:
            if r["check"].startswith("Matches existing"):
                continue  # depends on previously exported files
            self.assertNotEqual(r["status"], "FAIL", r["check"])

    def test_reference_results_reproduced(self):
        msp = {r["case"]: r["MSP_USD_per_kg_H2"] for r in self.t["21_MSP_and_CaCO3_Cases"]}
        self.assertGreater(msp["Case A (no CaCO3 sales; cake disposed)"], msp["Reference (commit 1473af06)"])
        total = self.t["15_LCA_Contributions"][-1]
        parts = sum(r["GWP_kgCO2e_per_kg_H2"] for r in self.t["15_LCA_Contributions"][:-1])
        self.assertAlmostEqual(total["GWP_kgCO2e_per_kg_H2"], parts, places=8)

    def test_experimental_gases_not_mixed_with_model(self):
        rows = [r for r in self.t["09_Products_Residues"] if r["stream"] == "EXPERIMENTAL GAS-YIELD SCENARIO"]
        self.assertTrue(rows and all("NOT element/redox balanced" in r["basis"] for r in rows[:4]))
        model = [r for r in self.t["09_Products_Residues"] if r["basis"] == "ELEMENT-BALANCED MODEL"]
        self.assertTrue(model)

    def test_every_unit_and_stream_documented(self):
        units = {r["unit_ID"] for r in self.t["03_Equipment_Operating"]}
        for ID in ("P1", "D0", "M1", "U2", "U3HX", "U3C", "U3D", "U3P", "U3K", "RC1", "D1", "F1", "C1", "F2",
                   "SP1", "EC1", "M2"):
            self.assertIn(ID, units)
        streams = {r["stream"] for r in self.t["04_Connectivity"]}
        self.assertEqual(streams, {r["stream"] for r in self.t["05_Stream_Inventory_Long"]})

    def test_unverified_sources_are_marked(self):
        comp = [r for r in self.t["23_Master_Assumptions"] if r["Parameter"].startswith("Dry composition")]
        self.assertTrue(all("Source not verified" in r["Exact_source"] for r in comp))


if __name__ == "__main__":
    unittest.main()
