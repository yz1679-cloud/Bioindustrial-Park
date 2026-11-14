"""REE recovery from the ATT char (att.yaml downstream.ree_recovery, switch default on): HCl leach and oxalate precipitation of the washed
char cake (LC1), roast of the oxalate precipitate into the REE product (RO1), spent leachate recycled to the dissolver D1. S2 inherits it from S1."""
import unittest
import warnings
import biosteam as bst

from biorefineries.ATT.analyses import inventory as inv
from biorefineries.ATT.analyses import scenarios as scen
from biorefineries.ATT.units._att import ATTReeLeach


class TestREERecovery(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        warnings.filterwarnings("ignore")
        cls.sys = scen.create(ree_recovery=True)
        cls.u, cls.s = inv._units(cls.sys), inv._streams(cls.sys)
        cls.dry = inv._dry_feed_kgph(cls.sys)


    def test_product_is_60_percent_of_the_wastewater_ree_at_the_target_grade(self):
        product, residue = self.s["ree_product"], self.s["att_char"]
        reo_water = 1.4 / 2.5 * 1e-3 * self.dry * 1.169                                  # 1.4 mg TREE/L at 2.5 g seaweed/L, as REO
        self.assertAlmostEqual(float(product.imass["REO"]), 0.6 * reo_water, places=9)
        self.assertAlmostEqual(float(product.imass["REO"] / product.F_mass), 0.0131, places=6)
        self.assertLess(0.6, self.u["LC1"]._stoich_ceiling)                              # the oxalate dose does not limit it
        cake_reo = float(self.u["LC1"].ins[0].imass["REO"])
        self.assertAlmostEqual(float(product.imass["REO"] + residue.imass["REO"]), cake_reo, places=9)    # the rest stays in the leached char
        self.assertEqual(float(self.s["spent_leachate"].imass["REO"]), 0.0)

    def test_hcl_adds_inlet_carbonate_neutralization_once(self):
        lc = self.u["LC1"]
        cake, hcl, ox, *_ = lc.ins
        solids = sum(float(cake.imass[c.ID]) for c in cake.chemicals if c.ID not in lc._DISSOLVED)
        experimental = lc.hcl_mol_per_kg_char * solids / 1000.0
        carbonate = float(cake.imol["Na2CO3"])
        self.assertAlmostEqual(float(hcl.imol["HCl"]), experimental + 2 * carbonate, places=8)
        self.assertAlmostEqual(float(self.s["leach_co2"].imol["CO2"]), carbonate, places=8)
        self.assertAlmostEqual(float(ox.imol["OxalicAcid"]), lc.oxalic_mol_per_kg_char * solids / 1000, places=8)
        self.assertAlmostEqual(float(hcl.imass["HCl"]) / hcl.F_mass, 0.31, places=8)

    def test_oxalic_solution_water_excludes_dissolved_acid(self):
        lc = self.u["LC1"]
        cake, hcl, ox, *_ = lc.ins
        solids = sum(float(cake.imass[c.ID]) for c in cake.chemicals if c.ID not in lc._DISSOLVED)
        expected = max(lc.leach_liquor_kg_per_kg_char * solids - float(hcl.F_mass), 0.0)
        expected += lc.oxalate_solution_kg_per_kg_char * solids - float(ox.F_mass)
        self.assertAlmostEqual(lc.water_demand_kgph(solids), expected, places=6)

    def test_oxalate_tank_proxy_does_not_add_solution_water_twice(self):
        lc = self.u["LC1"]
        self.assertAlmostEqual(float(lc.oxalate_tank.ins[0].imass["Water"]),
                               float(self.s["spent_leachate"].imass["Water"]), places=7)

    def test_hcl_tracks_changes_in_inlet_carbonate(self):
        with inv._scratch_flowsheet():
            cake = self.u["LC1"].ins[0].copy()
            cake.imol["Na2CO3"] = 0.0
            unit = ATTReeLeach(None, ins=(cake, *(bst.Stream(None) for _ in range(5))),
                               outs=tuple(bst.Stream(None) for _ in range(4)), dry_feed_kgph=lambda: self.dry)
            unit._run()
            original = float(unit.ins[1].imol["HCl"])
            cake.imol["Na2CO3"] = 0.25
            unit._run()
            self.assertAlmostEqual(float(unit.ins[1].imol["HCl"]) - original, 0.50, places=9)
            self.assertAlmostEqual(float(unit.outs[3].imol["CO2"]), 0.25, places=9)


if __name__ == "__main__":
    unittest.main()
