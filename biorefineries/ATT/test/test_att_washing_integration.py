"""Native F2 washing and the two requested boundary/check regressions."""
import unittest
import warnings
import numpy as np
import biosteam as bst
from biorefineries.ATT.analyses import scenarios as scen, inventory as inv, lca, tea
from biorefineries.ATT.analyses import marine_tea as mt, marine_whr as mw, reporting
from biorefineries.ATT.analyses.att_washing import washing_checks
from biorefineries.ATT.test._options import sales_option


class TestNativeF2Washing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        warnings.filterwarnings("ignore")
        cls.off = scen.create(washing="washing_off", f1_wash=False, caco3_dry=False, ash_salts=False, char_yield=0.0)                    # the F1 wash is tested below
        cls.on = scen.create(washing="washing_on", wash_recycle=False, wash_condensate=False, f1_wash=False, caco3_dry=False, ash_salts=False, char_yield=0.0)   # fresh water, liquor to wastewater
        cls.rec = scen.create(washing="washing_on", wash_condensate=False, f1_wash=False, caco3_dry=False, ash_salts=False, char_yield=0.0)    # wash liquor recycled to the dissolver
        cls.cond = scen.create(washing="washing_on", f1_wash=False, caco3_dry=False, ash_salts=False, char_yield=0.0)                          # and the excess condensate as wash water
        cls.u, cls.s = inv._units(cls.on), inv._streams(cls.on)
        cls.off_s = inv._streams(cls.off)

    def test_native_equipment_and_costs(self):
        self.assertIsInstance(self.u["W2"], bst.MixTank)
        self.assertIsInstance(self.u["F2R"], bst.RotaryVacuumFilter)
        for ID in ("W2", "F2R"):
            self.assertGreater(self.u[ID].purchase_cost, 0)
            self.assertGreater(self.u[ID].installed_cost, 0)
            self.assertGreater(self.u[ID].power_utility.rate, 0)

    def test_water_ratio_uses_all_original_dry_cake(self):
        feed = self.u["F2"].outs[0]
        dry = float(feed.F_mass - feed.imass["Water"])
        self.assertAlmostEqual(float(self.s["f2_wash_water"].F_mass), dry, places=7)
        self.assertAlmostEqual(self.s["f2_wash_water"].T, 298.15)

    def test_component_and_total_mass_balance(self):
        for row in washing_checks(self.on):
            self.assertEqual(row["status"], "PASS", row)
        inputs = self.u["F2"].outs[0].mass + self.s["f2_wash_water"].mass
        outputs = self.s["caco3_cake"].mass + self.s["f2_wash_liquor"].mass
        np.testing.assert_allclose(inputs, outputs, rtol=1e-12, atol=1e-8)

    def test_liquor_is_diluted_not_selectively_stripped(self):
        slurry = self.u["W2"].outs[0]
        cake, liquid = self.u["F2R"].outs
        for ID in ("NaOH", "Na2CO3"):
            ratio = float(slurry.imass[ID] / slurry.imass["Water"])
            self.assertAlmostEqual(float(cake.imass[ID] / cake.imass["Water"]), ratio, places=12)
            self.assertAlmostEqual(float(liquid.imass[ID] / liquid.imass["Water"]), ratio, places=12)
            self.assertGreater(float(cake.imass[ID]), 0)
            self.assertGreater(float(liquid.imass[ID]), 0)

    def test_calcium_solids_preserved(self):
        for ID in ("CaCO3", "CaOH2"):
            self.assertAlmostEqual(float(self.s["caco3_cake"].imass[ID]),
                                   float(self.u["F2"].outs[0].imass[ID]), places=8)
            self.assertEqual(float(self.s["f2_wash_liquor"].imass[ID]), 0)

    def test_purity_below_ideal_limit(self):
        cake, original = self.s["caco3_cake"], self.u["F2"].outs[0]
        purity = float(cake.imass["CaCO3"] / (cake.F_mass - cake.imass["Water"]))
        initial = float(original.imass["CaCO3"] / (original.F_mass - original.imass["Water"]))
        limit = float(cake.imass["CaCO3"] / (cake.imass["CaCO3"] + cake.imass["CaOH2"]))
        self.assertGreater(purity, initial)
        self.assertLess(purity, limit)
        self.assertLess(limit, .85)
        self.assertAlmostEqual(float(cake.imass["Water"] / cake.F_mass), .25, places=10)

    def test_reactor_recycle_and_f3_unchanged(self):
        for ID in ("scrubber_cake", "naoh_recycle", "fresh_naoh_solid", "h2_product"):
            np.testing.assert_allclose(self.s[ID].mass, self.off_s[ID].mass, rtol=1e-9, atol=1e-7)
        self.assertIs(self.u["SP1"].ins[0], self.u["F2"].outs[1])
        self.assertIn(self.s["f2_wash_liquor"], self.on.products)
        self.assertNotIn("W2", inv._units(self.off))
        self.assertEqual(self.u["C1"].conversion, .88)
        self.assertEqual(self.u["C1"].lime_equiv, 1.1)

    def test_wash_costs_and_lca_are_included(self):
        result = tea.evaluate_att_tea(self.on, **scen.tea_config())
        self.assertEqual(self.s["f2_wash_water"].price, result["prices"]["process_water"])
        self.assertEqual(self.s["f2_wash_liquor"].price, tea._PRICE["disposal_wastewater"]["baseline"])
        rows = tea._opex_table(self.on, result)
        self.assertEqual(sum(r["item"] == "Disposal: f2_wash_liquor" for r in rows), 1)
        self.assertTrue(any(r["item"] == "Process water (F2 washing)" for r in rows))
        lca.apply_att_gwp(self.on, overrides=scen.lca_overrides())
        neutral = sum(float(self.s[ID].imol["NaOH"] + self.s[ID].imol["Na2CO3"])
                      for ID in ("liquor_purge", "f2_wash_liquor")) * 98.07848 / 2
        self.assertAlmostEqual(lca._h2so4_kgph(self.on), neutral, places=8)
        self.assertGreater(lca._wastewater_m3ph(self.on), lca._wastewater_m3ph(self.off))
        self.assertGreater(self.s["f2_wash_water"].get_CF(lca.KEY), 0)

    def test_conservative_f2_sales_disposes_whole_cake(self):
        with sales_option():            # the CaCO3-sales option (the baseline disposes both cakes)
            result = tea.evaluate_att_tea(self.on, **scen.tea_config(f2_sales=False))
            f2, f3 = result["caco3_sales"]["caco3_cake"], result["caco3_sales"]["scrubber_cake"]
            self.assertEqual(f2["revenue_usd_ph"], 0)
            self.assertAlmostEqual(f2["disposed_kgph"], self.s["caco3_cake"].F_mass, places=8)
            self.assertGreater(f3["revenue_usd_ph"], 0)
            optimistic = tea.evaluate_att_tea(self.on, **scen.tea_config())
            self.assertGreater(result["msp"], optimistic["msp"])

    def test_washing_off_reference_values(self):
        ref = mt.s1_reference(self.off)
        self.assertAlmostEqual(ref["row"]["H2_t_per_yr"], 2953.563, delta=.001)
        self.assertAlmostEqual(ref["row"]["MSP_USD_per_kg_H2"], 3.102809, delta=1e-6)   # CaCO3 sold, no washing
        self.assertAlmostEqual(mw.evaluate_whr(self.off)["utilized_kW"], 1819.0580470, delta=1e-5)
        for hours, expected in ((7920., 3.280775), (2640., 5.254495)):
            row, _ = mt.evaluate_case(self.off, ref, "reference", hours=hours)
            self.assertAlmostEqual(row["MSP_USD_per_kg_H2"], expected, delta=1e-6)
            # baseline: inherited accounting with the residue credited, so the net GWP equals the inherited-credit GWP
            self.assertAlmostEqual(row["GWP_inherited_carbonate_credit_kgCO2e_per_kg_H2"], 7.213638, delta=1e-6)
            self.assertAlmostEqual(row["GWP_kgCO2e_per_kg_H2"], 7.213638, delta=1e-6)

    def test_wash_liquor_recycle_to_the_dissolver(self):
        rs, ru = inv._streams(self.rec), inv._units(self.rec)
        liquor = rs["f2_wash_liquor"]
        self.assertNotIn(liquor, self.rec.products)                     # an internal recycle, not wastewater
        self.assertIs(ru["F2R"].outs[1], liquor)
        self.assertIn(liquor, ru["D1"].ins)
        self.assertGreater(float(liquor.imass["NaOH"]), 0)
        # the dissolver still holds 3 kg water per kg of the Na2CO3 made in U2: the wash liquor water replaces condensate
        d1 = ru["D1"].outs[0]
        self.assertAlmostEqual(float(d1.imass["Water"]), 3.0 * float(ru["D1"].ins[0].imass["Na2CO3"]), places=6)
        # the recycled sodium cuts the fresh NaOH, and the neutralization sees only the purge
        self.assertLess(float(rs["fresh_naoh_solid"].F_mass), 0.8 * float(self.s["fresh_naoh_solid"].F_mass))
        self.assertAlmostEqual(lca._h2so4_kgph(self.rec),
                               float(rs["liquor_purge"].imol["NaOH"] + rs["liquor_purge"].imol["Na2CO3"]) * 98.07848 / 2,
                               places=8)
        rows = inv.get_att_external_flows(self.rec)
        self.assertNotIn("f2_wash_liquor", [r["stream"] for r in rows])
        error = sum(r["kg_per_h"] * (1 if r["direction"] == "input" else -1) for r in rows if r["component"] == "TOTAL")
        self.assertAlmostEqual(error, 0., delta=1e-5)

    def test_wash_water_is_the_excess_condensate(self):
        cs, cu = inv._streams(self.cond), inv._units(self.cond)
        rs = inv._streams(self.rec)
        original = cu["F2"].outs[0]
        dry = float(original.F_mass - original.imass["Water"])
        self.assertIn(cs["condensate_to_wash"], cu["W2"].ins)
        self.assertEqual(float(cs["f2_wash_water"].F_mass), 0.0)                  # no fresh water
        self.assertAlmostEqual(float(cs["condensate_to_wash"].F_mass), dry, places=4)
        # the same water, but taken from the wastewater: the excess condensate falls by the wash water
        self.assertAlmostEqual(float(rs["excess_condensate"].F_mass) - float(cs["excess_condensate"].F_mass), dry, places=3)
        np.testing.assert_allclose(cs["naoh_recycle"].mass, rs["naoh_recycle"].mass, rtol=1e-4, atol=1e-3)
        rows = inv.get_att_external_flows(self.cond)
        error = sum(r["kg_per_h"] * (1 if r["direction"] == "input" else -1) for r in rows if r["component"] == "TOTAL")
        self.assertAlmostEqual(error, 0., delta=1e-5)

    def test_f1_wash_of_the_residue_cake(self):
        base = scen.create()                                          # S1: F1 wash, condensate wash water, residue pays its disposal
        none = scen.create(f1_wash=False)
        u, s, ns = inv._units(base), inv._streams(base), inv._streams(none)
        self.assertEqual([i.ID for i in u["MC"].ins], ["f1_filtrate", "f1_wash_liquor"])
        self.assertIs(u["C1"].ins[0], u["MC"].outs[0])               # the wash liquor joins the carbonate solution
        self.assertNotIn(s["f1_wash_liquor"], base.products)         # not wastewater
        original = u["F1"].outs[0]
        dry = float(original.F_mass - original.imass["Water"])
        self.assertAlmostEqual(float(s["condensate_to_f1_wash"].F_mass) + float(s["f1_wash_water"].F_mass), dry, places=4)
        self.assertLess(float(s["ash_residue_cake"].imass["Na2CO3"]), 0.4 * float(ns["ash_residue_cake"].imass["Na2CO3"]))
        self.assertLess(float(s["fresh_naoh_solid"].F_mass), 0.9 * float(ns["fresh_naoh_solid"].F_mass))      # the cake is small at the 0.15 g/g char yield
        self.assertAlmostEqual(float(s["ash_residue_cake"].imass["Water"] / s["ash_residue_cake"].F_mass), 0.30, places=10)
        rows = inv.get_att_external_flows(base)
        error = sum(r["kg_per_h"] * (1 if r["direction"] == "input" else -1) for r in rows if r["component"] == "TOTAL")
        self.assertAlmostEqual(error, 0., delta=1e-5)

    def test_washed_residue_pays_its_disposal(self):
        for system, paid in ((scen.create(), True), (scen.create(f1_wash=False), False)):
            result = tea.evaluate_att_tea(system, **scen.tea_config())
            price = inv._streams(system)["ash_residue_cake"].price
            row = next(r for r in tea._opex_table(system, result) if r["item"] == "Disposal: ash_residue_cake")
            if paid:
                self.assertEqual(price, 0.0)
                self.assertEqual(row["USD_per_yr"], 0.0)
            else:
                self.assertEqual(price, tea._PRICE["disposal_solid"]["baseline"])      # unwashed: disposed
                self.assertGreater(row["USD_per_yr"], 0.0)

    def test_caco3_cakes_are_dried_before_sale(self):
        dried, wet = scen.create(), scen.create(caco3_dry=False)
        u, s, sw = inv._units(dried), inv._streams(dried), inv._streams(wet)
        for ID, dryer in (("caco3_cake", "D2"), ("scrubber_cake", "D3")):
            cake = s[ID]
            self.assertAlmostEqual(float(cake.imass["Water"] / cake.F_mass), 0.01, places=10)            # att.yaml caco3_drying
            self.assertAlmostEqual(float(sw[ID].imass["Water"] / sw[ID].F_mass), 0.25, places=10)        # undried: filter cake
            self.assertAlmostEqual(float(cake.imass["CaCO3"]), float(sw[ID].imass["CaCO3"]), places=8)    # only water leaves
            self.assertAlmostEqual(float(s[ID + "_wet"].F_mass), float(sw[ID].F_mass), places=6)
            self.assertGreater(sum(hu.duty for hu in u[dryer].heat_utilities), 0.0)                       # steam heated
            self.assertGreater(float(s[ID.split("_")[0] + "_dryer_exhaust"].imass["Water"]), 0.0)
        rows = inv.get_att_external_flows(dried)
        error = sum(r["kg_per_h"] * (1 if r["direction"] == "input" else -1) for r in rows if r["component"] == "TOTAL")
        self.assertAlmostEqual(error, 0., delta=1e-5)
        self.assertNotIn("D2", [x.ID for x in scen.create(caco3_dry=False).units])

    def test_waste_lime_is_a_carbide_lime_paste(self):
        for system in (self.off, self.on, self.rec, self.cond):
            s = inv._streams(system)
            for ID in ("lime", "scrubber_lime"):
                lime = s[ID]
                dry = float(lime.F_mass - lime.imass["Water"])
                self.assertAlmostEqual(float(lime.imass["CaOH2"]) / dry, 0.92, places=9)
                self.assertAlmostEqual(float(lime.imass["CaCO3"]) / dry, 0.04, places=9)
                self.assertAlmostEqual(float(lime.imass["LimeInerts"]) / dry, 0.04, places=9)
                self.assertAlmostEqual(float(lime.imass["Water"] / lime.F_mass), 0.40, places=9)

    def test_floating_capex_includes_washing_once(self):
        ref = mt.s1_reference(self.on)
        row, _ = mt.evaluate_case(self.on, ref, "washing_on")
        self.assertAlmostEqual(row["FCI_USD"], 1.25 * ref["FCI_USD"] + row["WHR_CAPEX_USD"], places=6)

    def test_zero_wash_and_sensitivity(self):
        zero = scen.create(washing="washing_on", wash_ratio=0., wash_recycle=False, wash_condensate=False, f1_wash=False, caco3_dry=False, ash_salts=False, char_yield=0.0)
        np.testing.assert_allclose(inv._streams(zero)["caco3_cake"].mass, inv._units(zero)["F2"].outs[0].mass,
                                   atol=1e-8, rtol=1e-10)
        more = scen.create(washing="washing_on", wash_ratio=2., wash_recycle=False, wash_condensate=False, f1_wash=False, caco3_dry=False, ash_salts=False, char_yield=0.0)
        self.assertLess(inv._streams(more)["caco3_cake"].imass["NaOH"], self.s["caco3_cake"].imass["NaOH"])
        with self.assertRaises(ValueError):
            scen.create(washing="washing_on", wash_ratio=-1., wash_recycle=False, wash_condensate=False, f1_wash=False, caco3_dry=False, ash_salts=False, char_yield=0.0)

    def test_empty_tail_gas_excluded_and_boundary_closed(self):
        rows = inv.get_att_external_flows(self.on)
        self.assertNotIn("u3_tail_gas", [r["stream"] for r in rows])
        self.assertIn("f2_wash_liquor", [r["stream"] for r in rows])
        totals = [r for r in rows if r["component"] == "TOTAL"]
        error = sum(r["kg_per_h"] * (1 if r["direction"] == "input" else -1) for r in totals)
        self.assertAlmostEqual(error, 0., delta=1e-5)

    def test_nonzero_tail_gas_feed_not_hidden(self):
        tail = self.s["u3_tail_gas"]
        try:
            tail.imass["H2"] = .1
            with self.assertRaisesRegex(ValueError, "system input"):
                inv.get_att_external_flows(self.on)
        finally:
            tail.empty()

    def test_documentation_register_uses_actual_feed_preparation_config(self):
        rows = reporting._yaml_register()
        self.assertNotIn("preprocessing.yaml", reporting.FILES)
        self.assertTrue(any(r["file"] == reporting.FILES["att.yaml"]
                            and r["key"] == "att.feed_preparation.presscake_feedstock_type" for r in rows))

    def test_scrubber_water_reporting_closes_without_changing_streams(self):
        for system in (self.off, self.on):
            streams = inv._streams(system)
            before = {ID: (st.mass.copy(), st.T, st.P) for ID, st in streams.items()}
            units = inv._units(system)
            scrubber = units["SCRUB"]
            captured = float(scrubber.ins[0].imol["CO2"] - scrubber.outs[0].imol["CO2"])
            expected = captured * float(scrubber.chemicals["Water"].MW) / inv._dry_feed_kgph(system)
            rows = {r["item"]: r for r in inv.get_att_water_balance(system)}
            self.assertAlmostEqual(rows["SCRUB water formation (carbonation)"]["kg_per_kg_dry"],
                                   expected, places=10)
            self.assertAlmostEqual(rows["inputs + formation - outputs"]["kg_per_kg_dry"], 0., delta=1e-8)
            for ID, (mass, temperature, pressure) in before.items():
                np.testing.assert_array_equal(streams[ID].mass, mass)
                self.assertEqual((streams[ID].T, streams[ID].P), (temperature, pressure))

    def test_actual_lime_accounting_and_consistency(self):
        cfg = scen.tea_config()
        result = tea.evaluate_att_tea(self.on, **cfg)
        applied = lca.apply_att_gwp(self.on, overrides=scen.lca_overrides())
        contributions = lca.get_att_gwp_contributions(self.on, applied)
        utilities = inv.get_att_purchased_utilities(self.on, [])
        row = next(r for r in reporting._consistency(self.on, [], result, contributions, utilities)
                   if r["check"].startswith("Ca(OH)2:"))
        expected = sum(float(self.s[ID].imass["CaOH2"]) for ID in ("lime", "scrubber_lime")) / inv._dry_feed_kgph(self.on)
        self.assertGreater(self.s["scrubber_lime"].F_mass, 0)
        self.assertEqual(row["status"], "PASS")
        self.assertAlmostEqual(row["TEA_or_model"], expected)
        self.assertAlmostEqual(row["LCA_or_reference"], expected)
        try:
            purchased = tea.evaluate_att_tea(self.on, **dict(cfg, price_overrides={"CaOH2": .24}))
            cost = sum(r["USD_per_yr"] for r in tea._opex_table(self.on, purchased) if r["item"] == "Ca(OH)2")
            self.assertAlmostEqual(cost, expected * inv._dry_feed_kgph(self.on) * .24 * self.on.operating_hours, places=5)
        finally:
            tea.evaluate_att_tea(self.on, **cfg)


if __name__ == "__main__":
    unittest.main()
