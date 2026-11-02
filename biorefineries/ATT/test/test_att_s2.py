"""ATT Scenario 2 (shipboard ATT with marine WHR): same process as S1; WHR heat bounded by sources and sinks and
counted once; floating CAPEX and labor multipliers applied as specified; S1 unaffected."""
import unittest
import warnings

from biorefineries.ATT.analyses import marine_tea as mt
from biorefineries.ATT.analyses import marine_whr as mw
from biorefineries.ATT.analyses import scenarios as scen
from biorefineries.ATT.analyses.breakdown import build_att_breakdown

ALL = ("jacket", "scavenge", "exhaust")


class TestATTS2(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        warnings.filterwarnings("ignore")
        cls.sys = scen.create(scen.ATT_S2)
        cls.whr = mw.evaluate_whr(cls.sys)
        cls.ref = mt.land_reference(cls.sys)

    def test_same_process_as_s1(self):
        s1, s2 = scen.ATT_S1, scen.ATT_S2
        for key in ("configuration", "psa", "scrubber", "lime", "dry_feed_kgph", "naoh_kg_per_kg_dry",
                    "gas_yield_mmol_per_g_daf"):
            self.assertEqual(s1[key], s2[key], key)
        self.assertTrue(s2["marine"])
        self.assertNotIn("att_s2", scen.SCENARIOS)                     # not a land-based standard scenario
        with self.assertRaises(ValueError):
            build_att_breakdown("att_s2", sys=self.sys)               # needs the floating TEA hooks
        U2 = {u.ID: u for u in self.sys.units}["U2"]
        y = {ID: float(U2.outs[0].imol[ID]) * 1e3 / U2._daf_sargassum_kgph for ID in ("H2", "CH4", "CO", "CO2")}
        for ID, v in {"H2": 54.15, "CH4": 0.60, "CO": 0.0, "CO2": 0.77}.items():
            self.assertAlmostEqual(y[ID], v, places=9)

    def test_whr_accounting_checks(self):
        for r in mw.check_whr(self.whr):
            self.assertEqual(r["status"], "PASS", r["check"])

    def test_sinks_are_post_hxn_purchased_steam(self):
        # the S1 HXN savings are not offered again: the steam sinks add up to the system's net purchased LP steam
        steam = sum(k["purchased_kW"] for k in self.whr["sinks"] if "steam" in k["utility"])
        net = sum(hu.duty for hu in self.sys.heat_utilities if hu.agent.ID == "low_pressure_steam") / 3600.0
        self.assertAlmostEqual(steam, net, delta=1e-6 * net)
        sinks = {k["unit"]: k for k in self.whr["sinks"]}
        self.assertEqual(sinks["U2 (500 C reaction heat, fired)"]["assigned_kW"], 0.0)
        self.assertFalse(sinks["U2 (500 C reaction heat, fired)"]["eligible"])

    def test_temperature_feasibility(self):
        dT = float(mw.load_whr_config()["sinks"]["min_approach_K"])
        src = {s["source"]: s for s in self.whr["sources"]}
        sinks = {k["unit"]: k for k in self.whr["sinks"]}
        for a in self.whr["assignments"]:
            s, k = src[a["source"]], sinks[a["sink"]]
            self.assertGreaterEqual(s["T_return_C"] - dT, k["T_in_C"] - 1e-9, a)
            self.assertGreater(mw._reach(s, k, dT), 0.0, a)

    def test_no_heat_at_low_load(self):
        w = mw.evaluate_whr(self.sys, load=0.15)
        self.assertEqual(w["utilized_kW"], 0.0)
        self.assertEqual(sum(s["gross_kW"] for s in w["sources"]), 0.0)

    def test_floating_multipliers(self):
        a, _ = mt.evaluate_case(self.sys, self.ref, "x1.25", sources=ALL, labor_multiplier=1.0)
        b, _ = mt.evaluate_case(self.sys, self.ref, "x1.25 labor2", sources=ALL, labor_multiplier=2.0)
        # labor multiplier: only the labor line changes, by exactly the S1 labor
        labor_s1 = self.ref["row"]["labor_OPEX_USD_per_yr"]
        self.assertAlmostEqual(b["labor_OPEX_USD_per_yr"] - a["labor_OPEX_USD_per_yr"], labor_s1, places=3)
        self.assertAlmostEqual(b["AOC_net_USD_per_yr"] - a["AOC_net_USD_per_yr"], labor_s1, places=3)
        for key in ("FCI_USD", "materials_USD_per_yr", "energy_OPEX_USD_per_yr", "CaCO3_revenue_USD_per_yr"):
            self.assertAlmostEqual(a[key], b[key], places=3, msg=key)
        # CAPEX multiplier: process capital only, WHR added once (not multiplied)
        self.assertAlmostEqual(b["FCI_USD"], 1.25 * self.ref["FCI_USD"] + b["WHR_CAPEX_USD"], delta=1e-6 * b["FCI_USD"])
        c, _ = mt.evaluate_case(self.sys, self.ref, "x1.4", sources=ALL, capex_multiplier=1.4)
        self.assertAlmostEqual(c["WHR_CAPEX_USD"], b["WHR_CAPEX_USD"], places=3)

    def test_operating_hours_scale_production(self):
        a, _ = mt.evaluate_case(self.sys, self.ref, "A", sources=ALL, hours=7920.0)
        b, _ = mt.evaluate_case(self.sys, self.ref, "B", sources=ALL, hours=2640.0)
        self.assertAlmostEqual(b["H2_t_per_yr"], a["H2_t_per_yr"] * 2640.0 / 7920.0, places=6)
        self.assertGreater(b["MSP_USD_per_kg_H2"], a["MSP_USD_per_kg_H2"])

    def test_s1_reference_unchanged(self):
        # the land-based S1 TEA through the same code path (hooks neutral) equals the plain S1 breakdown
        plain = build_att_breakdown("att_s1", sys=self.sys)["summary"]
        self.assertAlmostEqual(self.ref["row"]["MSP_USD_per_kg_H2"], plain["MSP_USD_per_kg_H2"], places=9)
        self.assertAlmostEqual(self.ref["FCI_USD"], plain["FCI_MUSD"] * 1e6, places=3)


if __name__ == "__main__":
    unittest.main()
