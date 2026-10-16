"""Verify C1 causticization duty registration after the minimal _att.py fix.

Place at: biorefineries/sabre/test_att_c1_utility.py
Run at project root: python -m biorefineries.sabre.test_att_c1_utility
Requires the project's installed BioSTEAM/ThermoSteam environment.
"""
from __future__ import annotations

import unittest


class TestC1HeatUtility(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from biorefineries.sabre.systems._att_system import create_att_system

        cls.sys = create_att_system(dry_sargassum_kgph=1.0)
        cls.sys.set_tolerance(
            mol=1e-9, rmol=1e-9, T=1e-5, rT=1e-5,
            maxiter=200, method="fixedpoint",
        )
        # Native equipment generates some utilities during design;
        # design_and_cost=False may give misleading zero duties.
        cls.sys.simulate()

    def _c1_heat_utility(self):
        c1 = self.sys.flowsheet.unit.C1
        active = [hu for hu in c1.heat_utilities if abs(float(hu.duty)) > 1e-9]
        self.assertEqual(
            len(active), 1,
            "Expected one nonzero C1 utility; verify _att.py was updated",
        )
        return c1, active[0]

    def test_c1_registered_with_correct_process_duty(self):
        c1, hu = self._c1_heat_utility()
        self.assertAlmostEqual(
            float(hu.unit_duty), float(c1._heat_duty_kJph),
            delta=1e-5,
        )
        self.assertAlmostEqual(
            float(hu.duty), float(c1._utility_heat_duty_kJph),
            delta=1e-5,
        )

    def test_loss_fraction_applied_exactly_once(self):
        c1, hu = self._c1_heat_utility()
        process = float(c1._heat_duty_kJph)
        utility = float(hu.duty)
        loss = float(c1._heat_loss_kJph)
        if process > 0:
            expected = process * (1.0 + float(c1.heat_loss_fraction))
            self.assertAlmostEqual(utility, expected, delta=1e-5)
            self.assertAlmostEqual(loss, utility - process, delta=1e-5)
        else:
            self.assertAlmostEqual(utility, process, delta=1e-5)
            self.assertAlmostEqual(loss, 0.0, delta=1e-5)

    def test_c1_heater_is_in_the_hxn(self):
        # C1's heating sits in a costed auxiliary exchanger with process streams.
        c1, hu = self._c1_heat_utility()
        self.assertTrue(hu.hxn_ok)
        self.assertGreater(c1.hxn_heater.installed_cost, 0.0)

    def test_repeat_simulation_does_not_duplicate_utility(self):
        c1, hu = self._c1_heat_utility()
        before = float(hu.duty)
        self.sys.simulate()
        c1, new_hu = self._c1_heat_utility()
        self.assertAlmostEqual(float(new_hu.duty), before, delta=1e-4)
        self.assertEqual(len(c1.heat_utilities), 1)

    @classmethod
    def tearDownClass(cls):
        cls.sys = None


if __name__ == "__main__":
    unittest.main(verbosity=2)
