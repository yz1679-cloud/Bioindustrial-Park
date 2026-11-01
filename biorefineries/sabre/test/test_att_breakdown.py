"""The ATT MSP / CAPEX / OPEX / GWP breakdown adds up to the totals it explains."""
import unittest
import warnings

from biorefineries.sabre.analyses.att.breakdown import build_att_breakdown, COST_TYPES


class TestATTBreakdown(unittest.TestCase):
    """The baseline of analyses/att/scenarios.py (waste-lime CO2 scrubber, no PSA, F2 washing)."""
    case = "baseline"
    psa = False

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
    """Waste lime is free and burden-free; the CaCO3 cakes are disposed (no kiln, no CaCO3 revenue)."""

    def test_waste_lime_scrubber_and_washing(self):
        areas = set(self.t["CAPEX_by_area"]["area"])
        self.assertNotIn("Lime kiln (K1)", areas)
        self.assertNotIn("PSA (U3P)", areas)
        self.assertIn("CO2 scrubber and filter (SCRUB, F3)", areas)
        self.assertIn("F2 washing and refiltration", areas)
        groups = self.t["OPEX_by_group"].set_index("group")["MUSD_per_yr"]
        self.assertEqual(groups.get("Ca(OH)2", 0.0), 0.0)
        self.assertGreater(groups["CaCO3 cake disposal"], 0.0)
        g = self.t["GWP_by_contributor"].set_index("contributor")["kgCO2e_per_kg_H2"]
        self.assertEqual(g["Ca(OH)2"], 0.0)
        self.assertEqual(self.s["NaOH_kg_per_kg_dry"], 1.0)
        self.assertAlmostEqual(self.s["dry_feed_t_per_day"], 5029.17 * 24 / 1e3, delta=1e-3)
        self.assertLessEqual(self.s["Ca_OH_2_used_t_per_yr"], 92.5e3)

    def test_residue_carbon_is_credited(self):
        """The carbon of the lumped residue (ATT char) is carbon in a landfilled solid: it is credited."""
        g = self.t["GWP_by_contributor"]
        self.assertLess(g.loc[g["stage"] == "Stored biogenic carbon", "kgCO2e_per_kg_H2"].sum(), -10.0)


class TestATTBreakdownFreshSargassum(TestATTBreakdown):
    """Optional: the baseline chemistry with fresh Sargassum fed to the press P1 (a juice coproduct)."""
    case = "fresh_sargassum"

    def test_press_is_costed(self):
        self.assertIn("Feed dewatering (P1)", set(self.t["CAPEX_by_area"]["area"]))
        self.assertNotIn("Feed dewatering (P1)", set(build_att_breakdown("baseline")["CAPEX_by_area"]["area"]))


if __name__ == "__main__":
    unittest.main()
