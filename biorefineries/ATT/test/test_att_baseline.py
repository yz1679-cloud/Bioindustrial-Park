"""
Key metrics of the ATT scenarios (S1, S2; add S3 and later ones as new entries below).

Baseline assumptions (data/*.yaml): presscake feed, NaOH 1 kg/kg dry, Ni-CatATT 1:1 gas yields, lumped residue (ATT
char), 88 % causticization, F2 washing with the excess condensate as wash water and the wash liquor recycled to the
dissolver, F1 washing of the residue cake (1 kg water/kg dry cake, liquor combined with the carbonate solution; the
washed residue has a net price of 0, assumed to be taken as a sorbent), both CaCO3 cakes dried to 1 wt % moisture (D2, D3), free
waste carbide lime of an
acetylene plant (a paste with CaCO3 and inert mineral impurities), waste-lime CO2 scrubber, no PSA, both CaCO3 cakes
SOLD at 100 USD/t of CaCO3 (assumed; the non-CaCO3 mass is disposed), the REE recovery (HCl leach, oxalate precipitation,
roast; the REO is sold at 35 USD/kg, assumed) and the storage credit for the Sargassum carbon
in the solids (CaCO3 sold or landfilled, the residue); soluble Na2CO3 carbon is not credited.

Values: BioSTEAM 2.54.0 (biosteam a4f6d15, thermosteam d3d4c7f, hensmith 0.1.2 at 95e9362), relative tolerance 1e-5.
The heat integration comes from hensmith, and the version string alone does not tell its releases apart: the PyPI
hensmith 0.1.2 (with biosteam 5d3f9ba and thermosteam 88becb6) gave S1 MSP 1.76234374, S2 no WHR 2.05076332 and all WHR
1.98989299; the hensmith at 95e9362 (needed by the current thermosteam, whose network code moved there) gave 1.85390402,
2.14162503 and 2.08075470 for the same model.
The values below include Yu Zhou's 2026-11-14 model edits (units/_att.py, data/att.yaml, lca.yaml, tea.yaml and
analyses/lca.py, marine_whr.py, reporting.py, validation.py, ported from 0959679d): additional HCl at 2 mol per mol of
Na2CO3 entering the REE leach, the oxalic solute subtracted from the solution water, and the HXN water proxy kept liquid
above 1 atm. Her report (2026-11-07; her environment: biosteam 2.53.11, thermosteam 0.53.5) gives S1 MSP 1.85420646, GWP
17.15869700, AOC 3.56474176 and the same FCI, NaOH, Ca(OH)2, U2 duty and carbon credit as below: the process results
agree to every digit, and the cost and GWP differences come from the heat integration (hensmith) only.
The earlier S1 baseline (no washing, pure Ca(OH)2 lime) was cross-checked to 9 digits against an independent model of
the same process (SaBRe Scenario 5); the wash recycle and the lime paste are ATT-only changes. If a deliberate model
change moves a value, update it in the same commit and say why.
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
    "MSP_USD_per_kg_H2": 1.93007488,
    "GWP_kgCO2e_per_kg_H2": 18.13958167,
    "FCI_MUSD": 14.75175771,
    "AOC_MUSD_per_yr": 3.78882392,
    "H2_t_per_yr": 2953.56307,
    "fresh_NaOH_t_per_yr": 3982.37332,
    "Ca_OH_2_used_t_per_yr": 47072.38784,
    "U2_heat_duty_MJ_per_kg_dry": 9.15429210,
    "dry_feed_t_per_day": 120.7001,
}
S1_STORED_CARBON_CREDIT = -8.26366818        # kg CO2e per kg H2, in the net GWP
S1_GWP_WITHOUT_CREDIT = 26.40324985

# ---- S2 (analyses/marine_tea.evaluate_case; the S1 process with the S2 TEA and heat-recovery accounting) -------
S2_WHR_UTILIZED_KW = 1819.05804704
# (engine sources, MSP, GWP, FCI [USD]); 7920 h underway
S2_CASES = {
    "no WHR": (2.21783613, 18.13958167, 18439697.1),
    "all WHR": (2.15696580, 16.70733506, 19329471.6),
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
        cls.ref = mt.s1_reference(cls.system)


    def test_waste_heat_recovery(self):
        close(self, mw.evaluate_whr(self.system)["utilized_kW"], S2_WHR_UTILIZED_KW, "utilized WHR")

    def test_s2_cases(self):
        _, hours, load = mt.operating_mode()
        for name, (msp, gwp, fci) in S2_CASES.items():
            sources = ALL_WHR if name == "all WHR" else ()
            row, _ = mt.evaluate_case(self.system, self.ref, f"S2 {name}", sources=sources, hours=hours, load=load)
            close(self, row["MSP_USD_per_kg_H2"], msp, f"{name} MSP")
            close(self, row["GWP_kgCO2e_per_kg_H2"], gwp, f"{name} GWP")
            close(self, row["FCI_USD"], fci, f"{name} FCI")


if __name__ == "__main__":
    unittest.main()
