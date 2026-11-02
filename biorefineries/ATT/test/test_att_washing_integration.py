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
        cls.off = scen.create(washing="washing_off")
        cls.on = scen.create(washing="washing_on")
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
        ref = mt.land_reference(self.off)
        self.assertAlmostEqual(ref["row"]["H2_t_per_yr"], 2953.563, delta=.001)
        self.assertAlmostEqual(ref["row"]["MSP_USD_per_kg_H2"], 5.206415, delta=1e-6)   # baseline: CaCO3 disposed
        self.assertAlmostEqual(mw.evaluate_whr(self.off)["utilized_kW"], 1857.8462335, delta=1e-5)
        for hours, expected in ((7920., 5.381386), (2640., 7.313186)):
            row, _ = mt.evaluate_case(self.off, ref, "reference", hours=hours)
            self.assertAlmostEqual(row["MSP_USD_per_kg_H2"], expected, delta=1e-6)
            # baseline: inherited accounting with the residue credited, so the net GWP equals the inherited-credit GWP
            self.assertAlmostEqual(row["GWP_inherited_carbonate_credit_kgCO2e_per_kg_H2"], 4.909519, delta=1e-6)
            self.assertAlmostEqual(row["GWP_kgCO2e_per_kg_H2"], 4.909519, delta=1e-6)

    def test_floating_capex_includes_washing_once(self):
        ref = mt.land_reference(self.on)
        row, _ = mt.evaluate_case(self.on, ref, "washing_on")
        self.assertAlmostEqual(row["FCI_USD"], 1.25 * ref["FCI_USD"] + row["WHR_CAPEX_USD"], places=6)

    def test_zero_wash_and_sensitivity(self):
        zero = scen.create(washing="washing_on", wash_ratio=0.)
        np.testing.assert_allclose(inv._streams(zero)["caco3_cake"].mass, inv._units(zero)["F2"].outs[0].mass,
                                   atol=1e-8, rtol=1e-10)
        more = scen.create(washing="washing_on", wash_ratio=2.)
        self.assertLess(inv._streams(more)["caco3_cake"].imass["NaOH"], self.s["caco3_cake"].imass["NaOH"])
        with self.assertRaises(ValueError):
            scen.create(washing="washing_on", wash_ratio=-1.)

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
