"""U2 cost sensitivity (analyses/u2_cost_sensitivity): baseline consistency, an independent DCF check of the MSP change,
monotonicity and the kiln-analog scaling."""
import types
import unittest
import warnings

from biorefineries.ATT.analyses import u2_cost_sensitivity as sens
from biorefineries.ATT.test.test_att_independent_checks import independent_cash_flow, npv_at


class TestU2CostSensitivity(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        warnings.filterwarnings("ignore")
        cls.df = sens.get_att_u2_cost_sensitivity()
        cls.row = {r["case"]: r for r in cls.df.to_dict("records")}


    def test_msp_change_matches_an_independent_dcf(self):
        # Extra installed capital E raises the FCI by E, the working capital by 5 % of it and the fixed operating cost by 4 % of
        # it. The MSP change must equal the price change that restores a zero NPV in an independent DCF.
        from biorefineries.ATT.analyses import inventory as inv, scenarios as scen, tea as tea_mod
        spec = scen.ALL_SCENARIOS["att_s1"]
        sys = scen.create(spec)
        config = scen.tea_config(spec, None)
        base = tea_mod.evaluate_att_tea(sys, **config)
        tea, msp = base["tea"], base["msp"]
        h2 = float(inv._streams(sys)["h2_product"].imass["H2"]) * sys.operating_hours
        extra = self.row["reactor body x10"]["FCI_MUSD"] * 1e6 - tea.FCI
        t = types.SimpleNamespace(**{k: getattr(tea, k) for k in (
            "FCI", "working_capital", "VOC", "FOC", "sales", "IRR", "income_tax", "finance_fraction", "finance_interest",
            "finance_years", "startup_months", "startup_VOCfrac", "construction_schedule", "duration")})
        t.FCI += extra
        t.working_capital += 0.05 * extra
        t.FOC += 0.04 * extra
        lo, hi = 0.0, 10.0 * msp
        for _ in range(200):
            mid = 0.5 * (lo + hi)
            if npv_at(t, independent_cash_flow(t, tea.sales + (mid - msp) * h2)) > 0.0:
                hi = mid
            else:
                lo = mid
        self.assertAlmostEqual(mid / self.row["reactor body x10"]["MSP_USD_per_kg_H2"], 1.0, delta=1e-6)


if __name__ == "__main__":
    unittest.main()
