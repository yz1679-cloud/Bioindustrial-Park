"""Consolidated ATT results: TEA and LCA use the same activity data."""
import unittest
import warnings

from biorefineries.sabre.analyses._att_consolidated import build_att_consolidated_results


class TestATTConsolidated(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        warnings.filterwarnings("ignore")
        cls.tables = build_att_consolidated_results()

    def test_tea_lca_consistency(self):
        for r in self.tables["08_consistency_checks"]:
            if r["check"].startswith("Matches existing"):
                continue  # depends on previously exported files
            self.assertNotEqual(r["status"], "FAIL", r["check"])

    def test_collection_cost_is_linear_in_feed_cost(self):
        rows = [r for r in self.tables["07_collection_transport"]
                if r["analysis"] == "TEA" and r["case"] == "Case A" and r["parameter"] == "collection + transport cost"]
        d10 = rows[2]["result"] - rows[0]["result"]
        d50 = rows[4]["result"] - rows[0]["result"]
        self.assertAlmostEqual(d50, 5 * d10, places=4)

    def test_measured_and_model_yields_reported_separately(self):
        items = {r["item"]: r for r in self.tables["01_process_materials"]}
        self.assertAlmostEqual(items["CH4 yield, measured"]["value"], 8.768738649553573, places=12)
        self.assertIn("EXPERIMENTAL", items["CH4 yield, measured"]["basis"])
        self.assertIn("ENGINEERING PREDICTION", items["CH4 yield, model"]["basis"])
        ratio = items["CH4 yield, model"]["value"] / items["H2 yield, model"]["value"]
        self.assertAlmostEqual(ratio, 8.768738649553573 / 66.72842505487348, places=10)


if __name__ == "__main__":
    unittest.main()
