import unittest


class TargetedATTTests(unittest.TestCase):
    def test_reagent_factors_and_legacy_override(self):
        from biorefineries.ATT.analyses import lca, scenarios, inventory
        system = scenarios.create(scenarios.ATT_S1, ree_recovery=True)
        streams = inventory._streams(system)
        legacy = dict(scenarios.lca_overrides(), HCl_31=0., oxalic_acid=0.)
        applied0 = lca.apply_att_gwp(system, overrides=legacy)
        before = system.get_net_impact(lca.KEY)
        applied = lca.apply_att_gwp(system, overrides=scenarios.lca_overrides())
        after = system.get_net_impact(lca.KEY)
        expected = (float(streams['fresh_hcl'].imass['HCl']) / .31 * applied['factors']['HCl_31']
                    + float(streams['fresh_oxalic_acid'].imass['OxalicAcid']) * applied['factors']['oxalic_acid']) * system.operating_hours
        self.assertAlmostEqual(after - before, expected, places=4)
        contributions = lca.get_att_gwp_contributions(system, applied)
        self.assertEqual(sum(r['item'] == 'HCl (31% solution)' for r in contributions), 1)
        self.assertEqual(sum(r['item'] == 'Oxalic acid' for r in contributions), 1)
        self.assertGreater(after, before)

    def test_product_revenues_and_lime_overrides(self):
        from biorefineries.ATT.analyses import scenarios, inventory, tea
        system = scenarios.create(scenarios.ATT_S1, ree_recovery=True)
        result = tea.evaluate_att_tea(system)
        streams = inventory._streams(system)
        self.assertEqual(scenarios.tea_config(scenarios.ATT_S1)['price_overrides']['CaOH2'], 0.)
        self.assertEqual(scenarios.tea_config(scenarios.ATT_S2)['price_overrides']['CaOH2'], 0.)
        self.assertEqual(scenarios.lca_overrides(scenarios.ATT_S1)['CaOH2_limestone'], 0.)
        self.assertEqual(scenarios.lca_overrides(scenarios.ATT_S2)['CaOH2_limestone'], 0.)
        for ID, row in result['caco3_sales'].items():
            self.assertAlmostEqual(row['sold_caco3_kgph'], float(streams[ID].imass['CaCO3']))
            self.assertAlmostEqual(row['disposed_kgph'], float(streams[ID].F_mass) - row['sold_caco3_kgph'])
            self.assertAlmostEqual(row['revenue_usd_ph'], row['sold_caco3_kgph'] * .1)
        product = streams['ree_product']
        grade = float(product.imass['REO']) / float(product.F_mass)
        self.assertAlmostEqual(grade, .0131, delta=1e-6)
        self.assertAlmostEqual(product.price * float(product.F_mass), 35 * float(product.imass['REO']))

    def test_h3_area_uses_extracted_heat_and_actual_pinch(self):
        from biorefineries.ATT.analyses.att_targeted_review import h3_screen
        case = dict(sources=[dict(source="H3", available_kW=100., T_in_C=300., T_out_C=100.)],
                    source_details=[dict(source="H3", extracted_kW=75., steam_kW=67.5)],
                    steam_agent=dict(temperature_C=130.))
        r = h3_screen(case)
        import math
        self.assertAlmostEqual(r['hot_out_C'], 150.)
        self.assertAlmostEqual(r['lmtd_K'], (170.-20.)/math.log(170./20.))
        self.assertAlmostEqual(r['area_at_U_50_W_m2_K_m2'], 75000 / (50*r['lmtd_K']))
        self.assertAlmostEqual(r['area_at_U_15_W_m2_K_m2'], 75000 / (15*r['lmtd_K']))

    def test_fee_is_charged_once_and_dcf_scenarios_reconcile(self):
        from biorefineries.ATT.analyses.att_targeted_review import evaluate
        rows = evaluate(disposal_usd_per_kg=0.04)
        self.assertEqual(len(rows), 6)
        for r in rows:
            self.assertAlmostEqual(r['fee_usd_per_year'], r['residue_kg_per_h'] * r['hours_per_year'] * .04)
            self.assertAlmostEqual(r['treatment_cost_delta_usd_per_t_wet'],
                                   r['fee_usd_per_year'] / r['wet_tonnes_per_year'])
            self.assertGreater(r['msp_fee_usd_per_kg_H2'], r['msp_original_usd_per_kg_H2'])
            self.assertAlmostEqual(r['net_gwp_updated_per_kg_H2']-r['net_gwp_original_per_kg_H2'],
                                   r['hcl_gwp_per_kg_H2']+r['oxalic_gwp_per_kg_H2'])
            if not r['ree_enabled']:
                self.assertEqual(r['hcl_gwp_per_kg_H2'],0.)
                self.assertEqual(r['oxalic_gwp_per_kg_H2'],0.)

if __name__ == '__main__': unittest.main()
