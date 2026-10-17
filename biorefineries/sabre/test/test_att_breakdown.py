"""The ATT MSP / CAPEX / OPEX / GWP breakdown adds up to the totals it explains."""
import unittest
import warnings

from biorefineries.sabre.analyses.att.breakdown import build_att_breakdown, COST_TYPES


class TestATTBreakdown(unittest.TestCase):
    """Scenario 2 (recycled lime, PSA); the other scenarios of analyses/att/scenarios.py subclass it."""
    case = "s2"
    psa = True

    @classmethod
    def setUpClass(cls):
        warnings.filterwarnings("ignore")
        cls.t = build_att_breakdown(cls.case)
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
        # the PSA tail gas replaces natural gas inside the natural gas lines: no separate offset line
        g = self.t["GWP_by_contributor"]
        self.assertFalse(g["contributor"].str.startswith("Natural gas displaced").any())
        self.assertTrue(g["contributor"].str.startswith("Natural gas U2").any())


class TestATTBreakdownBaseline(TestATTBreakdown):
    """Scenario 1: all Ca(OH)2 is bought and the CaCO3 cake is disposed of (TEA Case A)."""
    case = "s1"

    def test_cake_disposal_is_costed_and_no_kiln(self):
        self.assertNotIn("Lime kiln (K1)", set(self.t["CAPEX_by_area"]["area"]))
        groups = self.t["OPEX_by_group"].set_index("group")["MUSD_per_yr"]
        self.assertGreater(groups["CaCO3 cake disposal"], 0.0)
        self.assertGreater(groups["Ca(OH)2"], 0.0)


class TestATTBreakdownWasteLime(TestATTBreakdown):
    """Scenario 3: free waste lime replaces all the lime (no kiln, cake disposed), at the waste scale."""
    case = "s3"

    def test_waste_lime_is_free_and_burden_free(self):
        self.assertNotIn("Lime kiln (K1)", set(self.t["CAPEX_by_area"]["area"]))
        groups = self.t["OPEX_by_group"].set_index("group")["MUSD_per_yr"]
        self.assertEqual(groups.get("Ca(OH)2", 0.0), 0.0)
        g = self.t["GWP_by_contributor"].set_index("contributor")["kgCO2e_per_kg_H2"]
        self.assertEqual(g["Ca(OH)2"], 0.0)
        self.assertLess(self.s["dry_feed_t_per_day"], 300.0)
        self.assertLessEqual(self.s["Ca_OH_2_used_t_per_yr"], 92.6e3)


class TestATTBreakdownFullCapture(TestATTBreakdownWasteLime):
    """Scenario 4: NaOH for full CO2 capture, no PSA, same waste-lime supply and scale as scenario 3."""
    case = "s4"
    psa = False

    def test_no_psa_and_the_whole_supply_is_used(self):
        self.assertNotIn("PSA (U3P)", set(self.t["CAPEX_by_area"]["area"]))
        self.assertAlmostEqual(self.s["Ca_OH_2_used_t_per_yr"], 92.5e3, delta=0.2e3)
        self.assertEqual(self.s["NaOH_kg_per_kg_daf"], 2.995)


class TestATTBreakdownScrubber(TestATTBreakdownWasteLime):
    """Scenario 5: NaOH 1 g/g, no PSA, the gas CO2 fixed in a waste-lime scrubber (cake dewatered in F3)."""
    case = "s5"
    psa = False

    def test_scrubber_fixes_the_co2_within_the_supply(self):
        area = "CO2 scrubber and filter (SCRUB, F3)"
        self.assertIn(area, set(self.t["CAPEX_by_area"]["area"]))
        self.assertNotIn("PSA (U3P)", set(self.t["CAPEX_by_area"]["area"]))
        self.assertEqual(self.s["NaOH_kg_per_kg_daf"], 1.0)
        self.assertLessEqual(self.s["Ca_OH_2_used_t_per_yr"], 92.6e3)


class TestATTBreakdownFreshSargassum(TestATTBreakdown):
    """Scenario 6 (optional): the baseline chemistry with fresh Sargassum fed to the press P1 (a juice coproduct)."""
    case = "s6"

    def test_press_is_costed(self):
        self.assertIn("Feed dewatering (P1)", set(self.t["CAPEX_by_area"]["area"]))
        self.assertNotIn("Feed dewatering (P1)", set(build_att_breakdown("s1")["CAPEX_by_area"]["area"]))


if __name__ == "__main__":
    unittest.main()
