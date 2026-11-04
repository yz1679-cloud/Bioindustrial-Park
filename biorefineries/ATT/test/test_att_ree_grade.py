"""REO grade sensitivity of the REE product (analyses/ree_sensitivity.py; the collaborators' 98 wt % REO case): only the grade changes,
the REO mass stays, the mineral filler shrinks."""
import unittest

from biorefineries.ATT.analyses import ree_sensitivity as rs


class TestREEGrade(unittest.TestCase):


    def test_sensitivity_table_and_breakeven(self):
        df = rs.get_att_ree_grade_sensitivity(grades=(0.0131, 0.98), prices=(65.0,))
        off = df[~df["REE_recovery"]].iloc[0]
        on = df[df["REE_recovery"]]
        self.assertEqual(len(on), 4)                                                                         # 2 grades x (35, 65)
        base = on[(on["REO_grade"] == 0.0131) & (on["REO_price_usd_per_kg"] == 35.0)].iloc[0]
        high = on[(on["REO_grade"] == 0.98) & (on["REO_price_usd_per_kg"] == 35.0)].iloc[0]
        self.assertAlmostEqual(base["S1_MSP"] / 1.69003955, 1.0, delta=1e-5)                                 # the baseline pin
        self.assertAlmostEqual(off["S1_MSP"] / 1.75246213, 1.0, delta=1e-5)
        self.assertLess(high["S1_MSP"], base["S1_MSP"])                                                      # a smaller roaster and filter
        self.assertLess(high["RO1_MUSD"], 0.2 * base["RO1_MUSD"])
        be = rs.breakeven_prices(df).set_index("REO_grade")
        self.assertLess(be.loc[0.98, "S1_breakeven"], be.loc[0.0131, "S1_breakeven"])
        self.assertAlmostEqual(be.loc[0.0131, "S1_breakeven"], 23.2, delta=0.1)


if __name__ == "__main__":
    unittest.main()
