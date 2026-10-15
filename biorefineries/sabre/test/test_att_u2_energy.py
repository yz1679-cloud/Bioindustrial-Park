"""U2 gas basis, Hess-path energy breakdown and uncertainty analysis."""
import unittest
import warnings

from biorefineries.sabre.analyses.att.thermodynamics import (
    get_att_u2_gas_basis, evaluate_att_u2_variant,
    get_att_u2_energy_breakdown, get_att_u2_energy_uncertainty,
)
from biorefineries.sabre.systems._att_system import create_att_system
from biorefineries.sabre.units._att import _ATT


class TestU2Energy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        warnings.filterwarnings("ignore")
        # Reconciled comparison closure (the 2026-10-09 sensitivity range).
        cls.sys = create_att_system(dry_sargassum_kgph=1.0, u2_gas_closure="uniform_redox_scaling")
        cls.sys.set_tolerance(mol=1e-11, rmol=1e-11, T=1e-5, rT=1e-5,
                              maxiter=300, method="fixedpoint")
        cls.sys.simulate()
        cls.U2 = {u.ID: u for u in cls.sys.units}["U2"]

    def test_gas_basis_separates_measured_and_reconciled(self):
        g = get_att_u2_gas_basis(self.sys)
        measured = _ATT["cases"]["Ni-CatATT"]["gas_yield_mmol_per_g_daf"]
        self.assertEqual(g["measured_yield_mmol_per_g_daf"], measured)
        self.assertIn("NOT experimental", g["status"])
        s = g["scale_factor_s"]
        self.assertLess(s, 1.0)
        for k, y in measured.items():
            self.assertAlmostEqual(g["model_yield_mmol_per_g_daf"][k], s * y, places=12)
        self.assertAlmostEqual(g["H2_in_U2_gas_kgph"]["model"],
                               s * g["H2_in_U2_gas_kgph"]["measured"], places=12)

    def test_variant_evaluator_reproduces_u2(self):
        r = evaluate_att_u2_variant(self.sys)
        self.assertAlmostEqual(r["process_duty_kJph"], self.U2._heat_duty_kJph, delta=1e-6 * self.U2._heat_duty_kJph)
        self.assertAlmostEqual(r["scale_factor_s"], self.U2._gas_scale_factor, places=12)
        self.assertAlmostEqual(r["external_heating_kJph"], self.U2._utility_heat_duty_kJph, delta=1e-3)

    def test_breakdown_sums_to_duty(self):
        b = get_att_u2_energy_breakdown(self.sys)
        t = b["terms_kJph"]
        self.assertAlmostEqual(t["feed_to_25C_kJph"] + t["reaction_enthalpy_25C_H2O_liquid_kJph"]
                               + t["products_25C_to_T_kJph"], self.U2._heat_duty_kJph,
                               delta=1e-6 * self.U2._heat_duty_kJph)
        self.assertAlmostEqual(t["  of_which_NaOH_carbonation_kJph"]
                               + t["  of_which_organic_conversion_to_gases_CO2_char_kJph"],
                               t["reaction_enthalpy_25C_H2O_liquid_kJph"], places=6)
        n = self.U2.outs[1].imol["Na2CO3"] - self.U2.ins[0].imol["Na2CO3"]
        per_mol = t["  of_which_NaOH_carbonation_kJph"] / n / 1000.0
        # 2 NaOH(aq) + CO2 -> Na2CO3(s) + H2O(l): -83 kJ/mol at infinite
        # dilution, more exothermic for concentrated NaOH(aq).
        self.assertTrue(-130.0 < per_mol < -80.0, per_mol)
        self.assertGreater(t["  of_which_organic_conversion_to_gases_CO2_char_kJph"], 0.0)

    def test_uncertainty_interval_and_nh3_scenario(self):
        un = get_att_u2_energy_uncertainty(self.sys)
        Q0 = un["baseline"]["process_duty_kJph"]
        for key in ("primary_sensitivity_range_kJph", "secondary_sensitivity_range_literature_HHV_kJph"):
            lo, hi = un[key]["process_duty"]
            self.assertLess(lo, Q0)
            self.assertGreater(hi, Q0)
        cc = un["primary_sensitivity_range_kJph"]["process_duty"]
        lit = un["secondary_sensitivity_range_literature_HHV_kJph"]["process_duty"]
        self.assertIn("not a statistical confidence", un["range_status"])
        self.assertGreaterEqual(cc[0], lit[0])
        self.assertLessEqual(cc[1], lit[1])
        nh3 = un["nh3_unverified_scenario"]
        self.assertTrue(all("UNVERIFIED" in r["case"] for r in nh3))
        self.assertLess(nh3[-1]["scale_factor_s"], un["baseline"]["scale_factor_s"])



class TestU2EnergyH2Priority(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        warnings.filterwarnings("ignore")
        cls.sys = create_att_system(dry_sargassum_kgph=1.0, u2_gas_closure="h2_priority")
        cls.sys.set_tolerance(mol=1e-11, rmol=1e-11, T=1e-5, rT=1e-5,
                              maxiter=300, method="fixedpoint")
        cls.sys.simulate()
        cls.U2 = {u.ID: u for u in cls.sys.units}["U2"]

    def test_variant_and_breakdown_reproduce_u2(self):
        r = evaluate_att_u2_variant(self.sys)
        self.assertAlmostEqual(r["process_duty_kJph"], self.U2._heat_duty_kJph,
                               delta=1e-6 * self.U2._heat_duty_kJph)
        self.assertAlmostEqual(r["H2_kgph"], float(self.U2.outs[0].imass["H2"]), places=12)
        g = get_att_u2_gas_basis(self.sys)
        self.assertIn("H2_PRIORITY", g["status"])
        self.assertAlmostEqual(g["H2_in_U2_gas_kgph"]["model"],
                               g["H2_in_U2_gas_kgph"]["measured"], places=12)
        un = get_att_u2_energy_uncertainty(self.sys)
        self.assertIn("H2-priority", un["range_status"])
        lo, hi = un["primary_sensitivity_range_kJph"]["process_duty"]
        self.assertLess(lo, self.U2._heat_duty_kJph)
        self.assertGreater(hi, self.U2._heat_duty_kJph)


if __name__ == "__main__":
    unittest.main()
