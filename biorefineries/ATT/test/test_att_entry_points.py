"""Authoritative ATT entry points: the standard TEA/LCA paths build ATT S1 at its capacity with its waste-lime and
CaCO3-sales assumptions (analyses/scenarios.py, the single source); the runner and the exports resolve one output
root; the S2 operating-mode engine load reaches the WHR calculation."""
import copy
import os
import subprocess
import sys
import tempfile
import unittest
import warnings
from pathlib import Path
from unittest import mock

from biorefineries.ATT.analyses import att_s2_marine
from biorefineries.ATT.analyses import inventory as inv
from biorefineries.ATT.analyses import lca
from biorefineries.ATT.analyses import marine_tea as mt
from biorefineries.ATT.analyses import marine_whr as mw
from biorefineries.ATT.analyses import paths
from biorefineries.ATT.test._options import sales_option
from biorefineries.ATT.analyses import scenarios as scen
from biorefineries.ATT.analyses import tea as tea_mod
from biorefineries.ATT.analyses.breakdown import build_att_breakdown
from biorefineries.ATT.analyses import run as run_att

ALL = ("jacket", "scavenge", "exhaust")


def _gas_yields(sys):
    U2 = inv._units(sys)["U2"]
    return {ID: float(U2.outs[0].imol[ID]) * 1e3 / U2._daf_sargassum_kgph for ID in ("H2", "CH4", "CO", "CO2")}


class TestS1EntryPoints(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        warnings.filterwarnings("ignore")
        cls.s1 = build_att_breakdown("att_s1")["summary"]              # the authoritative S1 calculation
        cls.tea_sys = tea_mod.create_att_tea_system()
        cls.lca_sys = lca.create_att_lca_system()
        with tempfile.TemporaryDirectory() as d:
            cls.tea_tables = tea_mod.export_att_tea(d)
            cls.lca_tables = lca.export_att_lca(d)

    def test_systems_are_att_s1(self):
        spec = scen.ATT_S1
        for sys in (self.tea_sys, self.lca_sys):
            self.assertAlmostEqual(inv._dry_feed_kgph(sys), spec["dry_feed_kgph"], places=6)
            self.assertEqual(sys.operating_hours, 7920.0)
            for ID, v in spec["gas_yield_mmol_per_g_daf"].items():
                self.assertAlmostEqual(_gas_yields(sys)[ID], v, places=9, msg=ID)
            units = inv._units(sys)
            self.assertNotIn("K1", units)                              # waste lime: no kiln
            self.assertNotIn("U3P", units)                             # no PSA
            self.assertIn("SCRUB", units)                              # waste-lime CO2 scrubber
            h2 = float(inv._streams(sys)["h2_product"].imass["H2"]) * sys.operating_hours / 1e3
            self.assertAlmostEqual(h2, self.s1["H2_t_per_yr"], delta=1e-9 * h2)
        self.assertAlmostEqual(self.s1["H2_t_per_yr"], 2953.563, delta=0.01)   # not the legacy reference scale

    def test_single_source_of_scenario_assumptions(self):
        cfg = scen.tea_config(scen.ATT_S1)
        self.assertEqual(cfg["price_overrides"], {"CaOH2": 0.0})
        self.assertIsNone(cfg["caco3_sales"])                          # baseline: the CaCO3 cakes are disposed
        self.assertEqual(cfg["caco3"], dict(fraction=0.0))
        self.assertEqual(scen.lca_overrides(scen.ATT_S1), {"CaOH2_limestone": 0.0})
        self.assertEqual(scen.tea_config(scen.ATT_S2), cfg)            # S2 = the S1 process and S1 TEA basis
        self.assertEqual(scen.lca_overrides(scen.ATT_S2), scen.lca_overrides(scen.ATT_S1))
        with sales_option():                                           # the CaCO3-sales option
            cfg = scen.tea_config(scen.ATT_S1)
            self.assertEqual(cfg["caco3_sales"]["price_usd_per_metric_ton"], 100.0)
            self.assertEqual(list(cfg["caco3_sales"]["streams"]), ["caco3_cake", "scrubber_cake"])
            self.assertEqual(scen.tea_config(scen.ATT_S2), cfg)
            self.assertEqual(scen.tea_config(scen.ATT_S1, caco3_price=315.0)["caco3_sales"]["price_usd_per_metric_ton"], 315.0)
            self.assertEqual(scen.tea_config(scen.ATT_S1)["caco3_sales"]["price_usd_per_metric_ton"], 100.0)   # not mutated

    def test_tea_export_matches_s1(self):
        summary = {r["item"]: r["value"] for r in self.tea_tables["00_summary"]}
        self.assertAlmostEqual(summary["H2 MSP"], self.s1["MSP_USD_per_kg_H2"], places=9)
        self.assertAlmostEqual(summary["H2 production"], self.s1["H2_t_per_yr"], places=6)
        self.assertAlmostEqual(summary["Plant capacity"], self.s1["dry_feed_t_per_day"], places=9)
        self.assertAlmostEqual(summary["CaCO3 sales revenue"] * 1e6, self.s1["CaCO3_sales_revenue_USD_per_yr"], places=3)
        self.assertAlmostEqual(summary["Fixed capital investment (FCI)"], self.s1["FCI_MUSD"], places=9)
        for r in self.tea_tables["05_checks"]:
            self.assertEqual(r["status"], "PASS", r["check"])
        # the headline row is the S1 TEA; the SaBRe reference-treatment rows are labeled LEGACY
        legacy = [r for r in self.tea_tables["00_summary"] if "Reference" in r["item"] or "Case" in r["item"]]
        self.assertTrue(legacy and all(r["item"].startswith("LEGACY") for r in legacy))
        self.assertTrue(all("LEGACY" in r["basis"] for r in self.tea_tables["06_caco3_cases"]))
        self.assertTrue(all("LEGACY" in r["basis"] for r in self.tea_tables["07_lime_price_cases"]))

    def test_caco3_revenue_counted_once(self):
        rows = self.tea_tables["03_opex_and_msp_breakdown"]
        sales = -sum(r["USD_per_yr"] for r in rows if r["category"] == "CaCO3 sales")
        self.assertAlmostEqual(sales, self.s1["CaCO3_sales_revenue_USD_per_yr"], places=3)
        self.assertFalse(any("CaCO3" in r["item"] for r in rows if r["category"] in ("extra VOC", "waste disposal")))
        parts = sum(r["USD_per_kg_H2"] for r in rows if r["category"] != "total")
        self.assertAlmostEqual(parts, self.s1["MSP_USD_per_kg_H2"], places=9)

    def test_lca_export_matches_s1(self):
        summary = {r["item"]: r for r in self.lca_tables["01_summary"]}
        self.assertAlmostEqual(summary["GWP100 per kg H2"]["value"], self.s1["GWP_kgCO2e_per_kg_H2"], places=9)
        self.assertEqual(summary["Lime burden"]["value"], 0.0)                 # waste lime is burden-free
        lime = next(r for r in self.lca_tables["02_contributions_by_input"] if r["item"] == "Ca(OH)2")
        self.assertEqual(lime["GWP_kgCO2e_per_kg_H2"], 0.0)
        for r in self.lca_tables["08_checks"]:
            self.assertEqual(r["status"], "PASS", r["check"])
        base = next(r for r in self.lca_tables["06_scenarios_and_sensitivity"] if r["scenario"] == "Baseline")
        self.assertAlmostEqual(base["GWP_kgCO2e_per_kg_H2"], self.s1["GWP_kgCO2e_per_kg_H2"], places=9)

    def test_legacy_reference_is_never_silent(self):
        with self.assertRaises(ValueError):
            tea_mod.create_att_tea_system("presscake")               # the old positional configuration argument
        with self.assertRaises(ValueError):
            lca.create_att_lca_system("fresh_sargassum")
        with self.assertRaises(ValueError):
            tea_mod.create_att_tea_system(lime_recycle=True)          # contradicts att_s1 (waste lime)
        with self.assertRaises(KeyError):
            tea_mod.export_att_tea(scenario="att_s2")                 # marine: floating TEA in att_s2_marine.py
        self.assertGreater(inv.get_att_reference_scale()["dry_feed_kgph"], 5 * scen.ATT_S1["dry_feed_kgph"])


class TestOutputDirectory(unittest.TestCase):

    def test_default_root(self):
        with mock.patch.dict(os.environ):
            os.environ.pop(paths.RESULTS_ENV, None)
            self.assertEqual(paths.results_root(), paths.ATT_ROOT / "results")
            self.assertEqual(paths.output_dir("tables"), paths.ATT_ROOT / "results" / "tables")

    def test_runner_and_exports_resolve_the_same_root(self):
        code = ("from biorefineries.ATT.analyses.paths import output_dir\n"
                "from biorefineries.ATT.analyses import att_s2_marine, att_caco3_sales\n"
                "print(output_dir('tea')); print(output_dir('summary')); print(att_s2_marine.OUT); print(att_caco3_sales.OUT)")
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve()
            env = run_att.step_env(root)
            self.assertEqual(env[paths.RESULTS_ENV], str(root))
            out = subprocess.run([sys.executable, "-c", code], env=env, cwd=d, capture_output=True, text=True,
                                 check=True).stdout.split("\n")
            self.assertEqual([Path(x) for x in out[:4]],
                             [root / "full_scale" / "tea", root / "full_scale" / "summary", root / "tables", root / "tables"])

    def test_sabre_variable_is_not_read(self):
        with mock.patch.dict(os.environ, {"ATT_OUTPUTS_DIR": "elsewhere"}):
            os.environ.pop(paths.RESULTS_ENV, None)
            self.assertEqual(paths.results_root(), paths.ATT_ROOT / "results")


class TestS2EngineLoad(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        warnings.filterwarnings("ignore")
        cls.sys = scen.create(scen.ATT_S2)
        cls.ref = mt.land_reference(cls.sys)

    def test_default_modes(self):
        self.assertEqual(mt.operating_modes(), (("A: 7920 h underway (idealized)", 7920.0, 0.75),
                                                ("B: 2640 h (8 h/d underway)", 2640.0, 0.75)))

    def test_engine_load_changes_heat(self):
        ref = mw.evaluate_whr(self.sys)                                # 0.75 MCR reference
        for load in (0.5, 1.0):
            w = mw.evaluate_whr(self.sys, load=load)
            for key in ("gross_kW", "recoverable_kW", "delivered_kW"):
                a, b = sum(s[key] for s in w["sources"]), sum(s[key] for s in ref["sources"])
                self.assertTrue(a < b if load < 0.75 else a > b, (load, key))
            self.assertTrue(w["utilized_kW"] < ref["utilized_kW"] if load < 0.75 else w["utilized_kW"] > ref["utilized_kW"])

    def test_mode_load_reaches_evaluate_case(self):
        cfg = copy.deepcopy(mw.load_whr_config())
        cfg["operating_modes"]["A_underway_reference"]["engine_load"] = 0.5
        cfg["operating_modes"]["B_operational_profile"]["engine_load"] = 0.15     # below min_load_for_recovery
        rows = att_s2_marine.mode_tea_cases(self.sys, self.ref, cfg)
        full = {r["mode"]: r for r in rows if r["whr_sources"] == "+".join(ALL)}
        a, b = full["A: 7920 h underway (idealized)"], full["B: 2640 h (8 h/d underway)"]
        self.assertEqual((a["engine_load"], b["engine_load"]), (0.5, 0.15))
        self.assertAlmostEqual(a["WHR_utilized_kW"], mw.evaluate_whr(self.sys, load=0.5)["utilized_kW"], places=9)
        self.assertLess(a["WHR_utilized_kW"], mw.evaluate_whr(self.sys)["utilized_kW"])
        self.assertEqual(b["WHR_utilized_kW"], 0.0)                  # no validated usable heat at low load
        default = {r["mode"]: r for r in att_s2_marine.mode_tea_cases(self.sys, self.ref)
                   if r["whr_sources"] == "+".join(ALL)}
        for mode, r in default.items():                              # the published defaults: 0.75 MCR in both modes
            self.assertEqual(r["engine_load"], 0.75)
            self.assertAlmostEqual(r["WHR_utilized_kW"], mw.evaluate_whr(self.sys)["utilized_kW"], places=9)
        self.assertGreater(default["A: 7920 h underway (idealized)"]["MSP_USD_per_kg_H2"], 0.0)
        self.assertNotAlmostEqual(a["MSP_USD_per_kg_H2"], default["A: 7920 h underway (idealized)"]["MSP_USD_per_kg_H2"],
                                  places=6)


if __name__ == "__main__":
    unittest.main()
