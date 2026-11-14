"""Checks for the self-contained current-scenario technical report."""
import csv
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


class ComprehensiveReportTests(unittest.TestCase):
    def test_git_provenance_reports_clean_and_untracked_changes(self):
        from biorefineries.ATT.analyses.att_comprehensive_report import git_provenance
        with tempfile.TemporaryDirectory() as d:
            def git(*args):
                return subprocess.check_output(['git', '-C', d, *args], text=True).strip()
            git('init', '-q')
            git('-c', 'user.name=Test', '-c', 'user.email=test@example.com',
                'commit', '--allow-empty', '-qm', 'initial')
            clean = git_provenance(Path(d))
            self.assertEqual(clean['commit'], git('rev-parse', 'HEAD'))
            self.assertEqual(clean['working_tree_state'], 'clean')
            self.assertFalse(clean['working_tree_status'])
            (Path(d) / 'new.txt').write_text('untracked')
            dirty = git_provenance(Path(d))
            self.assertEqual(dirty['working_tree_state'], 'dirty')
            self.assertIn('?? new.txt', dirty['working_tree_status'])
            self.assertIn('uncommitted', dirty['note'].lower())

    def test_storage_credit_components_reconcile(self):
        from biorefineries.ATT.analyses.att_comprehensive_report import carbon_credit_breakdown
        from biorefineries.ATT.analyses import scenarios, lca
        system = scenarios.create(scenarios.ATT_S1, ree_recovery=True)
        credits = carbon_credit_breakdown(system)
        self.assertAlmostEqual(sum(credits.values()), lca.get_att_stored_carbon_credit(system), places=8)
        self.assertLess(credits['caco3_cakes'], 0.)
        self.assertLess(credits['char_residue'], 0.)

    def test_export_covers_cases_and_preserves_accounting(self):
        from biorefineries.ATT.analyses.att_comprehensive_report import collect, write_report
        data = collect()
        self.assertEqual(len(data['ree_tea']['cases']), 6)
        self.assertEqual(len(data['ree_tea']['increments']), 3)
        self.assertFalse(any('legacy_heat_duty' in r['parameter'] or 'nd_soak_data' in r['parameter']
                             or 'psa_cost' in r['parameter'] for r in data['assumptions']))
        self.assertTrue(any('pump_efficiency' in r['parameter'] for r in data['inactive_parameters']))
        self.assertEqual(len(data['scientific_notes']), 16)
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / 'report'
            write_report(out, data)
            html = (out / 'ATT_S1_S2_S3_Comprehensive_Report.html').read_text(encoding='utf-8')
            self.assertIn('Unresolved Organic Matter and Carbon Fate', html)
            self.assertNotIn('<script src=', html)
            self.assertNotIn('<link rel="stylesheet" href=', html)
            with (out / 'functional_unit_comparison.csv').open(encoding='utf-8', newline='') as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), 12)
            self.assertEqual({r['scenario'] for r in rows}, {'S1', 'S2', 'S3'})
            for r in rows:
                self.assertAlmostEqual(float(r['net_gwp_kg_co2e']),
                    float(r['gross_gwp_kg_co2e']) + float(r['credit_gwp_kg_co2e']))
                self.assertAlmostEqual(float(r['annual_net_treatment_cost_usd']),
                    float(r['annual_operating_cost_usd']) + float(r['annual_capital_charge_usd'])
                    - float(r['annual_coproduct_revenue_usd']), places=5)
            with (out / 'scenario_comparison.csv').open(encoding='utf-8', newline='') as f:
                comparison = list(csv.DictReader(f))
            self.assertEqual(len(comparison), 6)
            for c in comparison:
                self.assertGreater(float(c['h2_product_gas_kgph']), float(c['h2_component_kgph']))
                self.assertGreater(float(c['h2_mol_fraction']), 0.)
                self.assertLess(float(c['h2_mol_fraction']), 1.)
                self.assertGreater(float(c['wet_feed_kgph']), float(c['dry_feed_kgph']))
                self.assertGreater(float(c['external_heating_kW']), 0.)
                self.assertIn('waste_heat_delivered_kW', c)
                self.assertIn('caco3_cake_total_kgph', c)
                self.assertIn('caco3_impurity_disposal_kgph', c)
            self.assertIn('sixCaseOverview', html)
            self.assertIn('annualCostChart', html)
            self.assertIn('reeIncrementChart', html)
            self.assertIn('Annualized screening-cost breakdown', html)
            self.assertIn('DCF MSP is displayed separately', html)
            self.assertIn('pending further product-yield information from UCLA', html)
            self.assertNotIn('inherited sink issue', html)
            self.assertNotIn('inherited U3D steam-inventory discrepancy', html)
            with (out / 'report_qc.json').open(encoding='utf-8') as f:
                qc = json.load(f)
            self.assertEqual(qc['failed'], 0)
            self.assertGreater(qc['passed'], 100)
            self.assertEqual({r['case'].split()[0] for r in qc['checks']}, {'All','S1','S2','S3'})
            with (out / 'annual_cost_breakdown.csv').open(encoding='utf-8', newline='') as f:
                costs = list(csv.DictReader(f))
            self.assertEqual(len(costs), 6)
            for c in costs:
                reference = next(r for r in rows if r['basis']=='per_kg_h2'
                                 and r['scenario']==c['scenario'] and r['ree_enabled']==c['ree_enabled'])
                self.assertAlmostEqual(float(c['gross_opex_usd_per_year']),float(reference['annual_operating_cost_usd']),places=4)
                self.assertAlmostEqual(float(c['net_treatment_cost_usd_per_year']),float(reference['annual_net_treatment_cost_usd']),places=4)
            with (out / 'lca_breakdown.csv').open(encoding='utf-8', newline='') as f:
                lca = list(csv.DictReader(f))
            for case in (r for r in rows if r['basis'] == 'per_kg_h2'):
                parts = [float(x['kgCO2e_per_kg_H2']) for x in lca
                         if x['scenario'] == case['scenario'] and x['ree_enabled'] == case['ree_enabled']]
                self.assertAlmostEqual(sum(parts), float(case['net_gwp_kg_co2e']), places=7)
            for case in (r for r in rows if r['basis'] == 'per_tonne_wet'):
                other = next(r for r in rows if r['scenario'] == case['scenario']
                             and r['ree_enabled'] == case['ree_enabled'] and r['basis'] == 'per_kg_h2')
                self.assertAlmostEqual(float(case['net_gwp_kg_co2e']),
                    float(other['net_gwp_kg_co2e']) * float(case['hydrogen_kg']), places=7)
            with self.assertRaises(FileExistsError):
                write_report(out, data)

if __name__ == '__main__': unittest.main()
