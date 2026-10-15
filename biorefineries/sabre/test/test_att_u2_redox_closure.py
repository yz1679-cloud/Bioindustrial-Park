"""U2 element/redox closure: H2-priority baseline and uniform-scaling comparison."""
import unittest
import warnings

from biorefineries.sabre.systems._att_system import create_att_system
from biorefineries.sabre.units._att import _ATT


class TestU2RedoxClosure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        warnings.filterwarnings("ignore")
        cls.sys = create_att_system(dry_sargassum_kgph=1.0, u2_gas_closure="uniform_redox_scaling")
        cls.sys.set_tolerance(mol=1e-9, rmol=1e-9, T=1e-5, rT=1e-5,
                              maxiter=200, method="fixedpoint")
        cls.sys.simulate()
        cls.U2 = cls.sys.flowsheet.unit.U2

    def test_all_elements_and_mass_close(self):
        feed = self.U2.ins[0]
        gas, residue = self.U2.outs
        for element in ("C", "H", "O", "N", "S", "Na", "Ca"):
            inlet = float(feed.get_atomic_flow(element))
            outlet = float(gas.get_atomic_flow(element) + residue.get_atomic_flow(element))
            self.assertAlmostEqual(outlet, inlet, delta=1e-12 + 1e-10 * abs(inlet), msg=element)
        self.assertLess(abs(self.U2._mass_balance_error_kgph), 1e-6)

    def test_available_electrons_close(self):
        redox = self.U2._redox_balance_kmol_e_per_h
        self.assertAlmostEqual(
            redox["model_gases"] + redox["char"], redox["feed_organics"], places=12)
        # The measured absolute yields exceed the feed's reducing power.
        self.assertGreater(redox["measured_gases"], redox["feed_organics"])

    def test_measured_composition_kept_and_data_unchanged(self):
        s = self.U2._gas_scale_factor
        self.assertTrue(0.55 < s < 0.65, s)
        measured = _ATT["cases"]["Ni-CatATT"]["gas_yield_mmol_per_g_daf"]
        self.assertEqual(measured["H2"], 66.72842505487348)
        for ID, y in measured.items():
            self.assertAlmostEqual(
                self.U2._model_gas_yield_mmol_per_g_daf[ID], s * y, places=12)
        gas = self.U2.outs[0]
        self.assertAlmostEqual(
            gas.imol["H2"] / gas.imol["CH4"], measured["H2"] / measured["CH4"], places=9)

    def test_products_physical(self):
        gas, residue = self.U2.outs
        self.assertGreater(residue.imol["Char"], 0.0)
        self.assertGreater(gas.imol["Water"], 0.0)
        self.assertEqual(float(residue.imol["NaOH"]), 0.0)  # 100% conversion
        for ID in ("Glucan", "OtherSolids", "Protein", "Alginate", "Fucoidan", "Mannitol"):
            self.assertEqual(float(residue.imol[ID]), 0.0, ID)

    def test_heat_duty_is_hnet_balance(self):
        U2 = self.U2
        self.assertAlmostEqual(
            U2._heat_duty_kJph, U2._outlet_Hnet_kJph - U2._inlet_Hnet_kJph, places=6)
        self.assertAlmostEqual(
            U2._heat_duty_kJph,
            U2._feed_heating_duty_kJph + U2._reaction_and_product_state_kJph, places=6)
        # NaOH carbonation makes the reaction term exothermic.
        self.assertLess(U2._reaction_and_product_state_kJph, 0.0)
        self.assertGreater(U2._heat_duty_kJph, 0.0)

    def test_feasible_gas_data_is_rejected_not_scaled_up(self):
        U2 = self.U2
        original = dict(U2.reported_gas_yield_mmol_per_g_daf)
        try:
            U2.reported_gas_yield_mmol_per_g_daf = {k: 0.3 * v for k, v in original.items()}
            with self.assertRaises(RuntimeError):
                U2._run()
        finally:
            U2.reported_gas_yield_mmol_per_g_daf = original
            U2._run()



class TestU2H2PriorityClosure(unittest.TestCase):
    """Comparison closure: measured H2 kept, closure CO2 + char + water."""

    @classmethod
    def setUpClass(cls):
        warnings.filterwarnings("ignore")
        cls.sys = create_att_system(dry_sargassum_kgph=1.0, u2_gas_closure="h2_priority")
        cls.sys.set_tolerance(mol=1e-11, rmol=1e-11, T=1e-5, rT=1e-5,
                              maxiter=200, method="fixedpoint")
        cls.sys.simulate()
        cls.U2 = {u.ID: u for u in cls.sys.units}["U2"]

    def test_baseline_method_and_measured_h2_kept(self):
        U2 = self.U2
        self.assertEqual(U2.gas_closure_method, "h2_priority")
        measured = _ATT["cases"]["Ni-CatATT"]["gas_yield_mmol_per_g_daf"]
        y = U2._model_gas_yield_mmol_per_g_daf
        self.assertAlmostEqual(y["H2"], measured["H2"], places=10)
        self.assertEqual(y["CH4"], 0.0)
        self.assertEqual(y["CO"], 0.0)
        self.assertGreater(y[U2.closure_gas_ID], 0.0)
        self.assertNotEqual(U2._gas_scale_factor, U2._gas_scale_factor)  # nan: no s

    def test_elements_and_electrons_close(self):
        feed = self.U2.ins[0]
        gas, residue = self.U2.outs
        for element in ("C", "H", "O", "N", "S", "Na", "Ca"):
            inlet = float(feed.get_atomic_flow(element))
            outlet = float(gas.get_atomic_flow(element) + residue.get_atomic_flow(element))
            self.assertAlmostEqual(outlet, inlet, delta=1e-12 + 1e-10 * abs(inlet), msg=element)
        redox = self.U2._redox_balance_kmol_e_per_h
        self.assertAlmostEqual(redox["model_gases"] + redox["char"], redox["feed_organics"], places=12)
        self.assertGreater(self.U2.outs[1].imol["Char"], 0.0)

    def test_reduced_closure_species_are_infeasible(self):
        # The electron budget left after the measured H2 cannot hold the
        # remaining carbon as CH4 or CO: the char amount turns negative.
        U2 = self.U2
        original = U2.closure_gas_ID
        try:
            for ID in ("CH4", "CO"):
                U2.closure_gas_ID = ID
                with self.assertRaises(RuntimeError):
                    U2._run()
        finally:
            U2.closure_gas_ID = original
            U2._run()



class TestU2ExperimentalFixedGases(unittest.TestCase):
    """All four measured gases fixed: C, H, N, S, Na close; O cannot close."""

    @classmethod
    def setUpClass(cls):
        warnings.filterwarnings("ignore")
        cls.sys = create_att_system(dry_sargassum_kgph=1.0, u2_gas_closure="experimental_fixed")
        cls.sys.set_tolerance(mol=1e-11, rmol=1e-11, T=1e-5, rT=1e-5, maxiter=200, method="fixedpoint")
        cls.sys.simulate()
        cls.U2 = {u.ID: u for u in cls.sys.units}["U2"]

    def test_all_measured_gases_kept(self):
        measured = _ATT["cases"]["Ni-CatATT"]["gas_yield_mmol_per_g_daf"]
        for ID, y in measured.items():
            self.assertAlmostEqual(self.U2._model_gas_yield_mmol_per_g_daf[ID], y, places=10, msg=ID)

    def test_only_oxygen_unresolved_and_reported(self):
        feed = self.U2.ins[0]
        gas, residue = self.U2.outs
        for element in ("C", "H", "N", "S", "Na", "Ca"):
            inlet = float(feed.get_atomic_flow(element))
            outlet = float(gas.get_atomic_flow(element) + residue.get_atomic_flow(element))
            self.assertAlmostEqual(outlet, inlet, delta=1e-12 + 1e-10 * abs(inlet), msg=element)
        self.assertEqual(set(self.U2._unresolved_element_kmolph), {"O"})
        dO = self.U2._unresolved_element_kmolph["O"]
        self.assertLess(dO, 0.0)
        self.assertAlmostEqual(self.U2._mass_balance_error_kgph, dO * 15.999, places=4)
        self.assertFalse(self.U2._elemental_balance_enforced)
        self.assertIn("NOT CLOSED", self.U2._elemental_balance_status)

    def test_deficit_equals_redox_excess(self):
        redox = self.U2._redox_balance_kmol_e_per_h
        excess = redox["model_gases"] + redox["char"] - redox["feed_organics"]
        self.assertAlmostEqual(-2.0 * self.U2._unresolved_element_kmolph["O"], excess, places=10)



class TestU2BoundScenarios(unittest.TestCase):
    """Gas-A / Gas-Cprime alternative scenarios (char = 0): closed, nonnegative, not the baseline."""

    def _u2(self, method):
        sys = create_att_system(dry_sargassum_kgph=1.0, u2_gas_closure=method)
        sys.set_tolerance(mol=1e-11, rmol=1e-11, T=1e-5, rT=1e-5, maxiter=200, method="fixedpoint")
        sys.simulate()
        return {u.ID: u for u in sys.units}["U2"]

    def _closed(self, U2):
        feed = U2.ins[0]
        gas, residue = U2.outs
        for element in ("C", "H", "O", "N", "S", "Na", "Ca"):
            inlet = float(feed.get_atomic_flow(element))
            outlet = float(gas.get_atomic_flow(element) + residue.get_atomic_flow(element))
            self.assertAlmostEqual(outlet, inlet, delta=1e-12 + 1e-10 * abs(inlet), msg=element)
        self.assertEqual(float(residue.imol["Char"]), 0.0)
        self.assertTrue(all(v >= 0.0 for v in U2._model_gas_yield_mmol_per_g_daf.values()))

    def test_h2_measured_ch4_max(self):
        U2 = self._u2("h2_measured_ch4_max")
        self._closed(U2)
        y, m = U2._model_gas_yield_mmol_per_g_daf, _ATT["cases"]["Ni-CatATT"]["gas_yield_mmol_per_g_daf"]
        self.assertAlmostEqual(y["H2"], m["H2"], places=10)
        self.assertAlmostEqual(y["CO"], m["CO"], places=10)
        self.assertAlmostEqual(y["CH4"], 2.345, places=2)

    def test_uniform_co2_free(self):
        U2 = self._u2("uniform_co2_free")
        self._closed(U2)
        y, m = U2._model_gas_yield_mmol_per_g_daf, _ATT["cases"]["Ni-CatATT"]["gas_yield_mmol_per_g_daf"]
        self.assertAlmostEqual(U2._gas_scale_factor, 0.748, places=3)
        self.assertAlmostEqual(y["CH4"] / y["H2"], m["CH4"] / m["H2"], places=10)

    def test_baseline_unchanged(self):
        self.assertEqual(_ATT["material_balance"]["gas_closure_method"], "uniform_redox_scaling")


if __name__ == "__main__":
    unittest.main()
