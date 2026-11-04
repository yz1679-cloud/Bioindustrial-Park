"""REO grade sensitivity of the REE product (analyses/ree_sensitivity.py; the collaborators' 98 wt % REO case): only the grade changes,
the REO mass stays, the mineral filler shrinks."""
import unittest
import warnings

from biorefineries.ATT.analyses import inventory as inv
from biorefineries.ATT.analyses import ree_sensitivity as rs
from biorefineries.ATT.analyses import scenarios as scen


class TestREEGrade(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        warnings.filterwarnings("ignore")
        cls.default = inv._streams(scen.create())["ree_product"]
        cls.high = inv._streams(scen.create(ree_grade=0.98))["ree_product"]

    def test_default_grade_is_unchanged(self):
        self.assertAlmostEqual(float(self.default.imass["REO"] / self.default.F_mass), 0.0131, places=6)

    def test_98_percent_product_keeps_the_reo_and_drops_the_filler(self):
        self.assertAlmostEqual(float(self.high.imass["REO"] / self.high.F_mass), 0.98, places=4)
        self.assertAlmostEqual(float(self.high.imass["REO"]), float(self.default.imass["REO"]), places=9)      # the REO mass does not change
        self.assertLess(float(self.high.imass["Ash"]), 0.01 * float(self.default.imass["Ash"]))               # the mineral filler is gone

    def test_invalid_grade_is_rejected(self):
        for grade in (0.0, -0.1, 1.5):
            with self.assertRaises(ValueError):
                scen.create(ree_grade=grade)

    def test_concentrated_soak_gives_a_98_percent_product_of_60_percent_of_the_initial_ree(self):
        loading = 5.0                                                                      # mg TREE per g dry seaweed (an input, not a result)
        system = scen.create(ree_grade=0.98, ree_params=rs.concentrated_soak_params(loading))
        st = inv._streams(system)
        product = st["ree_product"]
        initial = loading * 1e-3 * inv._dry_feed_kgph(system) * 1.169                      # REO of the initial REE, kg/h
        self.assertAlmostEqual(float(product.imass["REO"]) / initial, 0.6, places=9)
        self.assertAlmostEqual(float(product.imass["REO"] / product.F_mass), 0.98, places=4)
        # the reagents follow the REE of the char (3 mol HCl and 1.5 mol oxalate per mol REE, x 1.2), not the lab doses per kg of char
        n_ree = float(system.flowsheet.unit.LC1.ins[0].imass["REO"]) / 1.169 / 149.1
        self.assertAlmostEqual(float(st["fresh_oxalic_acid"].imol["OxalicAcid"]), 1.5 * n_ree * 1.2, places=9)
        self.assertAlmostEqual(float(st["fresh_hcl"].imol["HCl"]), 3.0 * n_ree * 1.2, places=9)

    def test_collaborators_nd_soak_0p01M_case(self):
        loading, params, grade = rs.nd_soak_case("0.01 M")
        self.assertAlmostEqual(loading, 9.986 / 100.0 * 0.15 * 1e3, places=9)              # Nd wt % of the ATT residue x 0.15 g/g
        self.assertAlmostEqual(grade, 0.9882, places=6)
        system = scen.create(ree_grade=grade, ree_params=params)
        product = inv._streams(system)["ree_product"]
        nd_initial = loading * 1e-3 * inv._dry_feed_kgph(system)                           # kg Nd/h taken up (100 % capture)
        self.assertAlmostEqual(float(product.imass["REO"]) / (nd_initial * 336.48 / (2.0 * 144.242)), 0.603, places=9)
        self.assertAlmostEqual(float(product.imass["REO"] / product.F_mass), 0.9882, places=4)

    def test_unknown_ree_parameter_is_rejected(self):
        with self.assertRaises(KeyError):
            scen.create(ree_params={"no_such_parameter": 1.0})

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
