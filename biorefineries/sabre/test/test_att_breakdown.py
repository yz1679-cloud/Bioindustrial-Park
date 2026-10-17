"""The ATT MSP / CAPEX / OPEX / GWP breakdown adds up to the totals it explains."""
import unittest
import warnings

from biorefineries.sabre.analyses.att.breakdown import build_att_breakdown, COST_TYPES, CONFIGURATIONS


class TestATTBreakdown(unittest.TestCase):
    configuration = "att_only"
    lime_recycle = True

    @classmethod
    def setUpClass(cls):
        warnings.filterwarnings("ignore")
        cls.t = build_att_breakdown(cls.configuration, cls.lime_recycle)
        cls.s = cls.t["summary"]

    def test_u2_checks_pass(self):
        rows = cls_rows = self.t["U2_balance_checks"]
        status = rows["status"].dropna()
        self.assertFalse(status.str.startswith("FAIL").any(), rows.to_string())

    def test_msp_types_sum_to_msp(self):
        self.assertAlmostEqual(self.t["MSP_by_type"]["USD_per_kg_H2"].sum(), self.s["MSP_USD_per_kg_H2"], delta=1e-6)
        self.assertAlmostEqual(self.t["MSP_by_type"]["share_of_MSP"].sum(), 1.0, delta=1e-6)
        self.assertTrue(set(self.t["MSP_by_group"]["group"]) <= set(COST_TYPES))

    def test_capex_sums_to_fci_and_allocates_capital_msp(self):
        self.assertAlmostEqual(self.t["CAPEX_by_equipment"]["installed_MUSD"].sum(), self.s["FCI_MUSD"], delta=1e-6)
        self.assertAlmostEqual(self.t["CAPEX_by_area"]["installed_MUSD"].sum(), self.s["FCI_MUSD"], delta=1e-6)
        self.assertNotIn("Other", set(self.t["CAPEX_by_area"]["area"]))
        self.assertAlmostEqual(self.t["CAPEX_by_area"]["capital_related_MSP_USD_per_kg_H2"].sum(),
                               self.s["capital_related_MSP_USD_per_kg_H2"], delta=1e-9)

    def test_opex_sums_to_annual_operating_cost(self):
        opex = self.t["OPEX_by_group"]
        self.assertAlmostEqual(opex["MUSD_per_yr"].sum(), self.s["AOC_MUSD_per_yr"], delta=1e-6)
        waste = opex.loc[(opex["cost_type"] == "Waste treatment and disposal")
                         & (opex["group"] != "Neutralization (H2SO4)"), "MUSD_per_yr"].sum()
        # SaBReTEA books the disposal streams as negative sales, outside its VOC + FOC
        # (the H2SO4 for purge neutralization is a VOC item)
        self.assertAlmostEqual(self.s["TEA_VOC_plus_FOC_MUSD_per_yr"] + waste, self.s["AOC_MUSD_per_yr"], delta=1e-6)

    def test_gwp_sums_to_total(self):
        g = self.t["GWP_by_contributor"]
        self.assertAlmostEqual(g[g["counted_in_net"]]["kgCO2e_per_kg_H2"].sum(), self.s["GWP_kgCO2e_per_kg_H2"], delta=1e-6)
        # the landfill credit is a memo line: negative, listed, and not in the net
        memo = g[~g["counted_in_net"]]["kgCO2e_per_kg_H2"]
        self.assertEqual(len(memo), 1)
        self.assertLess(float(memo.iloc[0]), 0.0)
        # the landfill-CH4 credit replaces the stored-carbon credit (same carbon, different fate): not additive
        stored = g.loc[g["stage"] == "Stored biogenic carbon", "kgCO2e_per_kg_H2"].sum()
        self.assertAlmostEqual(self.s["GWP_with_landfill_credit_kgCO2e_per_kg_H2"],
                               self.s["GWP_kgCO2e_per_kg_H2"] - stored + float(memo.iloc[0]), delta=1e-9)
        self.assertAlmostEqual(self.t["GWP_by_stage"]["kgCO2e_per_kg_H2"].sum(), self.s["GWP_kgCO2e_per_kg_H2"], delta=1e-6)
        # no PSA, no tail gas: nothing displaces natural gas
        offset = self.t["GWP_by_contributor"]
        self.assertEqual(offset.loc[offset["contributor"].str.startswith("Natural gas displaced"), "kgCO2e_per_kg_H2"].iloc[0], 0.0)


class TestATTBreakdownIntegrated(TestATTBreakdown):
    configuration = "integrated"

    def test_no_press(self):
        self.assertNotIn("Feed dewatering (P1)", set(self.t["CAPEX_by_area"]["area"]))



class TestATTBreakdownFreshLime(TestATTBreakdown):
    """No lime recycle: all Ca(OH)2 is bought and the CaCO3 cake is disposed of (TEA Case A)."""
    configuration = "integrated"
    lime_recycle = False

    def test_cake_disposal_is_costed_and_no_kiln(self):
        self.assertNotIn("Lime kiln (K1)", set(self.t["CAPEX_by_area"]["area"]))
        groups = self.t["OPEX_by_group"].set_index("group")["MUSD_per_yr"]
        self.assertGreater(groups["CaCO3 cake disposal"], 0.0)


if __name__ == "__main__":
    unittest.main()
