"""ATT Scenario 2 (shipboard ATT with marine WHR): the recovered heat is bounded by sources and sinks, counted once and
thermally feasible."""
import unittest
import warnings

from biorefineries.ATT.analyses import marine_whr as mw
from biorefineries.ATT.analyses import scenarios as scen


class TestATTS2(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        warnings.filterwarnings("ignore")
        cls.sys = scen.create(scen.ATT_S2)
        cls.whr = mw.evaluate_whr(cls.sys)


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


if __name__ == "__main__":
    unittest.main()
