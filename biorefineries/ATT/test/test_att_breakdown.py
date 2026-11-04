"""The ATT MSP / CAPEX / OPEX / GWP breakdown adds up to the totals it explains (ATT Scenario 1)."""
import unittest
import warnings

from biorefineries.ATT.analyses.breakdown import build_att_breakdown, COST_TYPES


class TestATTBreakdown(unittest.TestCase):
    """ATT Scenario 1: presscake, NaOH 1 kg/kg dry, waste-lime CO2 scrubber, no PSA, waste lime."""
    case = "att_s1"

    @classmethod
    def setUpClass(cls):
        warnings.filterwarnings("ignore")
        cls.t = build_att_breakdown(cls.case)
        cls.s = cls.t["summary"]


    def test_breakdowns_add_up(self):
        self.assertAlmostEqual(self.t["MSP_by_type"]["USD_per_kg_H2"].sum(), self.s["MSP_USD_per_kg_H2"], delta=1e-6)
        self.assertAlmostEqual(self.t["MSP_by_type"]["share_of_MSP"].sum(), 1.0, delta=1e-6)
        self.assertTrue(set(self.t["MSP_by_group"]["group"]) <= set(COST_TYPES))
        self.assertAlmostEqual(self.t["CAPEX_by_equipment"]["installed_MUSD"].sum(), self.s["FCI_MUSD"], delta=1e-6)
        self.assertAlmostEqual(self.t["CAPEX_by_area"]["installed_MUSD"].sum(), self.s["FCI_MUSD"], delta=1e-6)
        self.assertNotIn("Other", set(self.t["CAPEX_by_area"]["area"]))
        self.assertAlmostEqual(self.t["CAPEX_by_area"]["capital_related_MSP_USD_per_kg_H2"].sum(),
                               self.s["capital_related_MSP_USD_per_kg_H2"], delta=1e-9)


if __name__ == "__main__":
    unittest.main()
