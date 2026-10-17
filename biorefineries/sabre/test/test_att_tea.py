"""Preliminary ATT TEA (att.tea): MSP accounting and consistency."""
import unittest
import warnings

from biorefineries.sabre.analyses.att import inventory as inv
from biorefineries.sabre.analyses.att import tea as tea_mod


class TestATTTEA(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        warnings.filterwarnings("ignore")
        cls.sys = tea_mod.create_att_tea_system()
        cls.fingerprint = [float(x) for st in (*cls.sys.feeds, *cls.sys.products) for x in st.mass]
        cls.estimates = inv.get_att_cost_estimates(cls.sys)
        cls.result = tea_mod.evaluate_att_tea(cls.sys, cls.estimates)
        cls.h2_yr = float(inv._streams(cls.sys)["h2_product"].F_mass) * cls.sys.operating_hours

    def test_checks_pass(self):
        for r in tea_mod._checks(self.sys, self.result, self.fingerprint):
            self.assertEqual(r["status"], "PASS", r["check"])

    def test_msp_breakdown_sums(self):
        rows = tea_mod._opex_table(self.sys, self.result)
        parts = sum(r["USD_per_kg_H2"] for r in rows if r["category"] != "total")
        self.assertAlmostEqual(parts, self.result["msp"], places=9)

    def test_deductible_cost_passes_through(self):
        # A change in a deductible annual cost moves the MSP by cost / H2.
        lime = float(inv._streams(self.sys)["lime"].F_mass) * self.sys.operating_hours
        high = tea_mod.evaluate_att_tea(self.sys, self.estimates, price_overrides={"CaOH2": 0.35})["msp"]
        tea_mod.evaluate_att_tea(self.sys, self.estimates)
        self.assertAlmostEqual(high - self.result["msp"], (0.35 - 0.24) * lime / self.h2_yr, places=4)

    def test_no_coproduct_revenue_and_capital_items(self):
        s = inv._streams(self.sys)
        self.assertEqual(s["u3_tail_gas"].price, 0.0)
        self.assertEqual(s["caco3_cake"].price, 0.0)
        # the PSA and the compressor are costed inside U3P and U3K, not added by the TEA
        units = inv._units(self.sys)
        self.assertGreater(units["U3P"].installed_cost, 0.0)
        self.assertEqual(type(units["U3K"]).__name__, "ATTCompressor")
        self.assertEqual(units["U3K"].compressor_type, "Reciprocating")


    def test_caco3_case_b_dcf_matches_cash_change(self):
        # The CaCO3 cake is a disposed or sold coproduct only without the lime recycle (otherwise it feeds the kiln).
        self.sys = tea_mod.create_att_tea_system(lime_recycle=False)
        self.estimates = inv.get_att_cost_estimates(self.sys)
        self.h2_yr = float(inv._streams(self.sys)["h2_product"].F_mass) * self.sys.operating_hours
        self.result = tea_mod.evaluate_att_tea(self.sys, self.estimates)
        s = inv._streams(self.sys)
        hours = self.sys.operating_hours
        case_a = tea_mod.evaluate_att_tea(self.sys, self.estimates, caco3=dict(fraction=0.0))["msp"]
        case_b = tea_mod.evaluate_att_tea(self.sys, self.estimates, caco3=dict(
            fraction=0.5, price_usd_per_t=250.0, handling_usd_per_t=0.0))["msp"]
        tea_mod.evaluate_att_tea(self.sys, self.estimates)
        sold = 0.5 * float(s["caco3_cake"].imass["CaCO3"]) * 0.25 * hours          # only CaCO3 content priced
        avoided = 0.5 * float(s["caco3_cake"].F_mass) * 0.04 * hours                  # disposal no longer paid
        self.assertAlmostEqual(case_a - case_b, (sold + avoided) / self.h2_yr, places=4)
        self.assertGreater(case_a, self.result["msp"])                                # disposal added in Case A

    def test_updated_lime_price(self):
        lime = float(inv._streams(self.sys)["lime"].F_mass) * self.sys.operating_hours
        msp = tea_mod.evaluate_att_tea(self.sys, self.estimates, price_overrides={"CaOH2": 0.28})["msp"]
        tea_mod.evaluate_att_tea(self.sys, self.estimates)
        self.assertAlmostEqual(msp - self.result["msp"], 0.04 * lime / self.h2_yr, places=4)


if __name__ == "__main__":
    unittest.main()
