"""The ATT MSP / CAPEX / OPEX / GWP breakdown adds up to the totals it explains (ATT Scenario 1)."""
import unittest
import warnings

from biorefineries.ATT.analyses.att.breakdown import build_att_breakdown, COST_TYPES
from biorefineries.ATT.analyses.att import scenarios as scen


class TestATTBreakdown(unittest.TestCase):
    """ATT Scenario 1: presscake, NaOH 1 kg/kg dry, waste-lime CO2 scrubber, no PSA, waste lime."""
    case = "att_s1"

    @classmethod
    def setUpClass(cls):
        warnings.filterwarnings("ignore")
        cls.t = build_att_breakdown(cls.case)
        cls.s = cls.t["summary"]

    def test_u2_checks_pass(self):
        # Known to FAIL for ATT Scenario 1: the measured gases + residual-carbon char hold more hydrogen than the
        # feed (unresolved balance, see IMPLEMENTATION_NOTES.md). Kept as is so that the issue stays visible.
        rows = self.t["U2_balance_checks"]
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
        # the extra avoided-CH4 credit is a memo line: negative, listed, and not in the net
        memo = g[~g["counted_in_net"]]["kgCO2e_per_kg_H2"]
        self.assertEqual(len(memo), 1)
        self.assertLess(float(memo.iloc[0]), 0.0)
        # avoided emission if rotted on the beach = the stored carbon (already in the net) + the extra CH4 credit
        stored = g.loc[g["stage"] == "Stored biogenic carbon", "kgCO2e_per_kg_H2"].sum()
        self.assertAlmostEqual(self.s["GWP_avoided_emission_total_kgCO2e_per_kg_H2"], stored + float(memo.iloc[0]), delta=1e-9)
        self.assertAlmostEqual(self.s["GWP_with_avoided_CH4_credit_kgCO2e_per_kg_H2"],
                               self.s["GWP_kgCO2e_per_kg_H2"] + float(memo.iloc[0]), delta=1e-9)
        self.assertAlmostEqual(self.t["GWP_by_stage"]["kgCO2e_per_kg_H2"].sum(), self.s["GWP_kgCO2e_per_kg_H2"], delta=1e-6)

    def test_waste_lime_scrubber_no_psa(self):
        self.assertNotIn("Lime kiln (K1)", set(self.t["CAPEX_by_area"]["area"]))
        self.assertNotIn("PSA (U3P)", set(self.t["CAPEX_by_area"]["area"]))
        self.assertIn("CO2 scrubber and filter (SCRUB, F3)", set(self.t["CAPEX_by_area"]["area"]))
        groups = self.t["OPEX_by_group"].set_index("group")["MUSD_per_yr"]
        self.assertEqual(groups.get("Ca(OH)2", 0.0), 0.0)
        g = self.t["GWP_by_contributor"].set_index("contributor")["kgCO2e_per_kg_H2"]
        self.assertEqual(g["Ca(OH)2"], 0.0)

    def test_capacity_and_dose(self):
        self.assertAlmostEqual(self.s["dry_feed_t_per_day"], 5029.17 * 24 / 1e3, delta=1e-6)
        self.assertEqual(self.s["NaOH_kg_per_kg_dry"], 1.0)
        # waste-lime supply check (C1 lime + scrubber lime)
        self.assertLessEqual(self.s["Ca_OH_2_used_t_per_yr"] * 1e3, scen.WASTE_LIME_KG_PER_YR)


if __name__ == "__main__":
    unittest.main()
