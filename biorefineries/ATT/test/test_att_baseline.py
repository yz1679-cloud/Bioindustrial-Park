"""
Key metrics of the ATT scenarios (S1, S2; add S3 and later ones as new entries below).

Baseline assumptions (data/*.yaml): presscake feed, NaOH 1 kg/kg dry, Ni-CatATT 1:1 gas yields, lumped residue (ATT
char), 88 % causticization, F2 washing with the wash liquor recycled to the dissolver, free waste carbide lime of an
acetylene plant (a paste with CaCO3 and inert mineral impurities), waste-lime CO2 scrubber, no PSA, CaCO3 cakes DISPOSED
(no CaCO3 sales), and the storage credit for the Sargassum carbon in landfilled solids (CaCO3, Na2CO3, the residue).

Values: BioSTEAM 2.54.0, relative tolerance 1e-5. The earlier S1 baseline (no washing, pure Ca(OH)2 lime) was
cross-checked to 9 digits against an independent model of the same process (SaBRe Scenario 5); the wash recycle and the
lime paste are ATT-only changes. If a deliberate model change moves a value, update it in the same commit and say why.
"""
import unittest
import warnings

from biorefineries.ATT.analyses import marine_tea as mt
from biorefineries.ATT.analyses import marine_whr as mw
from biorefineries.ATT.analyses import scenarios as scen
from biorefineries.ATT.analyses.breakdown import build_att_breakdown

RTOL = 1e-5
ALL_WHR = ("jacket", "scavenge", "exhaust")

# ---- S1 (analyses/breakdown.build_att_breakdown("att_s1")) ----------------------------------------------------
S1_METRICS = {
    "MSP_USD_per_kg_H2": 5.19851150,
    "GWP_kgCO2e_per_kg_H2": 7.19824771,
    "FCI_MUSD": 12.8759836,
    "AOC_MUSD_per_yr": 13.68545,
    "H2_t_per_yr": 2953.56307,
    "fresh_NaOH_t_per_yr": 7065.4161,
    "Ca_OH_2_used_t_per_yr": 43059.0100,
    "U2_heat_duty_MJ_per_kg_dry": 9.14913814,
    "dry_feed_t_per_day": 120.7001,
}
S1_STORED_CARBON_CREDIT = -15.2096585        # kg CO2e per kg H2, in the net GWP
S1_GWP_WITHOUT_CREDIT = 22.4079062

# ---- S2 (analyses/marine_tea.evaluate_case; the S1 process with the S2 TEA and heat-recovery accounting) -------
S2_WHR_UTILIZED_KW = 1857.84623353
# (mode key, engine sources, MSP, GWP, FCI [USD]); mode A: 7920 h underway, mode B: 2640 h (8 h/d underway)
S2_CASES = {
    ("A", "no WHR"): (5.44968219, 7.19824771, 16094979.5),
    ("A", "all WHR"): (5.39264905, 5.80784142, 17103095.8),
    ("B", "no WHR"): (7.43072558, 7.19824771, 16094979.5),
    ("B", "all WHR"): (7.47561709, 5.80784142, 17103095.8),
}


def close(test, value, expected, msg=""):
    test.assertAlmostEqual(value / expected, 1.0, delta=RTOL, msg=f"{msg}: {value} vs {expected}")


class TestATTS1(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        warnings.filterwarnings("ignore")
        cls.t = build_att_breakdown("att_s1")
        cls.s = cls.t["summary"]

    def test_key_metrics(self):
        for key, expected in S1_METRICS.items():
            close(self, self.s[key], expected, key)

    def test_caco3_is_disposed_not_sold(self):
        self.assertEqual(self.s["CaCO3_sold_t_per_yr"], 0.0)
        self.assertGreater(self.s["CaCO3_cake_disposal_USD_per_yr"], 0.0)

    def test_all_landfilled_carbon_is_credited(self):
        g = self.t["GWP_by_contributor"]
        credit = float(g.loc[g["stage"] == "Stored biogenic carbon", "kgCO2e_per_kg_H2"].sum())
        close(self, credit, S1_STORED_CARBON_CREDIT, "stored carbon credit")
        close(self, self.s["GWP_kgCO2e_per_kg_H2"] - credit, S1_GWP_WITHOUT_CREDIT, "GWP without the credit")

    def test_u2_balance_and_residue(self):
        self.assertEqual(self.s["U2_balance_status"], "PASS")
        self.assertTrue(self.s["U2_residual_product"].startswith("lumped: CH0.5O1.19"), self.s["U2_residual_product"])


class TestATTS2(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        warnings.filterwarnings("ignore")
        cls.system = scen.create(scen.ATT_S2)
        cls.ref = mt.land_reference(cls.system)

    def test_reference_is_s1(self):
        close(self, self.ref["row"]["MSP_USD_per_kg_H2"], S1_METRICS["MSP_USD_per_kg_H2"], "MSP")
        close(self, self.ref["row"]["GWP_kgCO2e_per_kg_H2"], S1_METRICS["GWP_kgCO2e_per_kg_H2"], "GWP")
        close(self, self.ref["row"]["H2_t_per_yr"], S1_METRICS["H2_t_per_yr"], "H2")

    def test_waste_heat_recovery(self):
        close(self, mw.evaluate_whr(self.system)["utilized_kW"], S2_WHR_UTILIZED_KW, "utilized WHR")

    def test_s2_cases(self):
        modes = {m[0][:1]: m for m in mt.operating_modes()}
        for (mode, name), (msp, gwp, fci) in S2_CASES.items():
            _, hours, load = modes[mode]
            sources = ALL_WHR if name == "all WHR" else ()
            row, _ = mt.evaluate_case(self.system, self.ref, f"S2 {name}", sources=sources, hours=hours, load=load)
            close(self, row["MSP_USD_per_kg_H2"], msp, f"{mode} {name} MSP")
            close(self, row["GWP_kgCO2e_per_kg_H2"], gwp, f"{mode} {name} GWP")
            close(self, row["FCI_USD"], fci, f"{mode} {name} FCI")


if __name__ == "__main__":
    unittest.main()
