"""NaOH(aq) property model and the EC1 evaporator / M2 makeup mixer."""
import unittest
import warnings

import biosteam as bst
from scipy.optimize import brentq

from biorefineries.sabre import _naoh_properties as naoh
from biorefineries.sabre.systems._att_system import create_att_system
from biorefineries.sabre.units._att import NaOHEvaporator


class TestNaOHProperties(unittest.TestCase):
    def test_pure_water_vapor_pressure_matches_steam_tables(self):
        self.assertAlmostEqual(naoh.water_vapor_pressure_Pa(0.0, 373.15) / 101418.0, 1.0, delta=0.005)
        self.assertAlmostEqual(naoh.water_vapor_pressure_Pa(0.0, 363.15) / 70182.0, 1.0, delta=0.005)

    def test_50wt_boiling_point_at_1_atm(self):
        Tb = brentq(lambda T: naoh.water_vapor_pressure_Pa(0.5, T) - 101325.0, 380.0, 470.0)
        self.assertTrue(413.15 < Tb < 423.15, Tb - 273.15)  # handbooks: ~145-147 C

    def test_heat_of_dilution_matches_oxychem_table_12(self):
        h = naoh.solution_enthalpy_kJ_per_kg
        T = 293.15
        for x, table in ((0.40, (114.2 - 1.18) * 2.326), (0.44, (151.7 - 1.18) * 2.326)):
            released = -(h(0.02, T) / 0.02 - h(x, T) / x - (1 / 0.02 - 1 / x) * h(0.0, T))
            self.assertAlmostEqual(released / table, 1.0, delta=0.10)

    def test_solid_naoh_anchor_matches_oxychem_table_11(self):
        h = naoh.solution_enthalpy_kJ_per_kg
        T = 293.15
        for r, q_cal in ((3, 179.7), (25, 257.0)):
            w = r * 18.015 / 39.997
            x = 1 / (1 + w)
            released = naoh.solid_naoh_enthalpy_kJ_per_kg(T) + w * h(0.0, T) - (1 + w) * h(x, T)
            self.assertAlmostEqual(released / (q_cal * 4.184), 1.0, delta=0.03)

    def test_na2co3_solubility_reproduces_wu_2020_points(self):
        for m, expected, solid in ((0.0, 4.14, "Na2CO3.H2O"), (5.96, 1.44, "Na2CO3"), (24.08, 0.10, "Na2CO3")):
            value, phase = naoh.na2co3_solubility_mol_per_kg_water(m, 363.15)
            self.assertAlmostEqual(value, expected, places=9)
            self.assertEqual(phase, solid)

    # ---- Validation against independent data -----------------------------
    def test_pure_water_limit_over_20_to_150C(self):
        water = bst.Chemical("Water")
        for T_C in (20, 40, 60, 80, 90, 100, 120, 150):
            T = T_C + 273.15
            self.assertAlmostEqual(naoh.water_vapor_pressure_Pa(0.0, T) / water.Psat(T), 1.0, delta=0.01)

    def test_boiling_points_match_independent_data(self):
        def Tb(x):
            return brentq(lambda T: naoh.water_vapor_pressure_Pa(x, T) - 101325.0, 373.0, 470.0) - 273.15
        # Supplier SDS: 25 % 112 C, 33 % 118 C, 50 % 145 C.
        for x, T_ref in ((0.25, 112.0), (0.33, 118.0), (0.50, 145.0)):
            self.assertAlmostEqual(Tb(x), T_ref, delta=3.0)
        # ASSDA boiling curve (digitized fit T = 69 + 24.46 exp(0.02332 wt%)).
        import math
        for x in (0.20, 0.30, 0.40, 0.45, 0.50):
            self.assertAlmostEqual(Tb(x), 69 + 24.46 * math.exp(2.332 * x), delta=2.5)

    def test_vapor_pressure_and_enthalpy_are_thermodynamically_consistent(self):
        # Water vaporization enthalpy from Clausius-Clapeyron on P(x, T) vs
        # h_vap - partial specific enthalpy of water from h(x, T).
        import math
        water = bst.Chemical("Water")
        h = naoh.solution_enthalpy_kJ_per_kg
        R = 8.314462618e-3 / 0.01801528
        for x in (0.176, 0.30, 0.40, 0.438, 0.50):
            for T_C in (80.0, 90.0, 100.0):
                T, dT, dx = T_C + 273.15, 0.05, 1e-4
                dlnp = (math.log(naoh.water_vapor_pressure_Pa(x, T + dT))
                        - math.log(naoh.water_vapor_pressure_Pa(x, T - dT)))
                L_cc = -R * dlnp / (1 / (T + dT) - 1 / (T - dT))
                hbar_w = h(x, T) - x * (h(x + dx, T) - h(x - dx, T)) / (2 * dx)
                L_h = h(0.0, T) + water.Hvap(T) / water.MW - hbar_w
                with self.subTest(x=x, T_C=T_C):
                    self.assertAlmostEqual(L_h / L_cc, 1.0, delta=0.015)

    def test_heat_capacity_matches_oxychem_table_3(self):
        h = naoh.solution_enthalpy_kJ_per_kg
        table = {0.10: {120: 0.916, 160: 0.920, 200: 0.923}, 0.30: {120: 0.862, 160: 0.868, 200: 0.869},
                 0.50: {80: 0.771, 120: 0.768, 160: 0.765, 200: 0.764}}   # BTU/lb/F
        for x, row in table.items():
            for F, cp_ref in row.items():
                T = (F - 32) / 1.8 + 273.15
                cp = (h(x, T + 0.5) - h(x, T - 0.5)) / 4.1868
                with self.subTest(x=x, F=F):
                    self.assertAlmostEqual(cp / cp_ref, 1.0, delta=0.025)

    def test_na2co3_pure_water_solubility_matches_handbook(self):
        # 45.62 g/100 g at 60 C and 43.6 g/100 g at 100 C -> ~44.1 g/100 g at 90 C.
        m, solid = naoh.na2co3_solubility_mol_per_kg_water(0.0, 363.15)
        g_per_100g = m * 105.988 / 10.0
        self.assertAlmostEqual(g_per_100g, 45.62 + (43.6 - 45.62) * 30 / 40, delta=1.0)
        self.assertEqual(solid, "Na2CO3.H2O")

    def test_out_of_range_inputs_raise(self):
        with self.assertRaises(ValueError):
            naoh.water_vapor_pressure_Pa(0.75, 363.15)
        with self.assertRaises(ValueError):
            naoh.na2co3_solubility_mol_per_kg_water(10.0, 333.15)


class TestEC1M2Flowsheet(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        warnings.filterwarnings("ignore")
        cls.sys = create_att_system(dry_sargassum_kgph=1.0)
        cls.sys.set_tolerance(mol=1e-9, rmol=1e-9, T=1e-5, rT=1e-5,
                              maxiter=300, method="fixedpoint")
        cls.sys.simulate()
        cls.u = cls.sys.flowsheet.unit

    def test_evaporates_only_excess_water(self):
        EC1, M2 = self.u.EC1, self.u.M2
        gross = M2._required_gross_naoh_kgph
        self.assertAlmostEqual(EC1.outs[0].imass["Water"], gross, places=9)  # 50 %: water = NaOH
        recycle = M2.outs[0]
        x = recycle.imass["NaOH"] / (recycle.imass["NaOH"] + recycle.imass["Water"])
        self.assertAlmostEqual(x, 0.5, places=12)
        self.assertAlmostEqual(recycle.imass["NaOH"], gross, places=9)

    def test_operating_pressure_is_electrolyte_vapor_pressure(self):
        EC1 = self.u.EC1
        P = naoh.water_vapor_pressure_Pa(EC1._outlet_naoh_wt_frac_naoh_water, EC1.T)
        self.assertAlmostEqual(EC1._operating_pressure_Pa, P, places=6)
        self.assertLess(P, 0.5 * bst.Chemical("Water").Psat(EC1.T))
        self.assertGreater(EC1.T - EC1._condensation_temperature_K, 20.0)

    def test_carbonate_crystallizes_and_species_conserved(self):
        EC1, M2 = self.u.EC1, self.u.M2
        feed, conc, cond = EC1.ins[0], EC1.outs[0], EC1.outs[1]
        for ID in ("Water", "NaOH", "Na2CO3"):
            self.assertAlmostEqual(conc.imass[ID] + cond.imass[ID], feed.imass[ID], places=10)
        self.assertGreater(conc.imass["s", "Na2CO3"], 0.0)
        self.assertEqual(float(conc.imass["s", "NaOH"]), 0.0)
        out = M2.outs[0]
        self.assertAlmostEqual(out.imass["NaOH"], conc.imass["NaOH"] + M2.ins[1].imass["NaOH"], places=10)

    def test_ec1_duty_closes_enthalpy_balance(self):
        EC1 = self.u.EC1
        h = naoh.solution_enthalpy_kJ_per_kg
        feed, conc = EC1.ins[0], EC1.outs[0]
        N, Wi, Wo = feed.imass["NaOH"], feed.imass["Water"], conc.imass["Water"]
        Water = feed.chemicals["Water"]
        expected = ((N + Wo) * h(N / (N + Wo), EC1.T)
                    + (Wi - Wo) * (h(0.0, EC1.T) + Water.Hvap(EC1.T) / Water.MW)
                    - (N + Wi) * h(N / (N + Wi), feed.T)
                    + EC1._crystallization_heat_kJph)
        self.assertAlmostEqual(EC1._heat_duty_kJph, expected, delta=1.0)
        self.assertAlmostEqual(EC1._utility_heat_duty_kJph, 1.05 * EC1._heat_duty_kJph, delta=1e-6)

    def test_m2_is_adiabatic(self):
        M2 = self.u.M2
        h = naoh.solution_enthalpy_kJ_per_kg
        liquor, fresh = M2.ins
        out = M2.outs[0]
        W = liquor.imass["Water"]
        N1, N2 = liquor.imass["NaOH"], out.imass["NaOH"]
        H_in = (N1 + W) * h(N1 / (N1 + W), liquor.T) + fresh.imass["NaOH"] * naoh.solid_naoh_enthalpy_kJ_per_kg(fresh.T)
        H_out = (N2 + W) * h(N2 / (N2 + W), out.T)
        carbonate = liquor.imass["Na2CO3"] / 105.988 * liquor.chemicals["Na2CO3"].Cn("s", 0.5 * (liquor.T + out.T)) * (out.T - liquor.T)
        crystallization = M2._na2co3_salted_out_kgph / 105.988 * 26.7e3   # kJ/h, endothermic
        self.assertAlmostEqual(H_out + carbonate + crystallization, H_in, delta=1e-3)

    def test_m2_salts_out_na2co3_to_saturation(self):
        M2 = self.u.M2
        out = M2.outs[0]
        self.assertTrue(M2._na2co3_equilibrated)
        self.assertGreater(M2._na2co3_salted_out_kgph, 0.0)
        W = out.imass["l", "Water"]
        m_naoh = out.imass["l", "NaOH"] / 39.997 * 1e3 / W
        m_sat, solid = naoh.na2co3_solubility_mol_per_kg_water(m_naoh, 363.15)
        self.assertEqual(solid, "Na2CO3")
        self.assertAlmostEqual(out.imass["l", "Na2CO3"], m_sat * W * 105.988 / 1e3, places=9)
        # EC1 feed liquor is undersaturated (no Na2CO3 crystallization upstream of EC1).
        feed = self.u.EC1.ins[0]
        m_feed = feed.imass["NaOH"] / 39.997 * 1e3 / feed.imass["Water"]
        m_sat_feed, _ = naoh.na2co3_solubility_mol_per_kg_water(m_feed, 363.15)
        self.assertLess(feed.imass["Na2CO3"] / 105.988 * 1e3 / feed.imass["Water"], m_sat_feed)

    def test_u2_feed_naoh_correction_is_applied(self):
        U2 = self.u.U2
        self.assertLess(U2._aqueous_feed_correction_kJph, 0.0)
        self.assertAlmostEqual(
            U2._inlet_Hnet_kJph,
            float(U2.ins[0].Hnet) + U2._feed_Hf_HHV_correction_kJph + U2._aqueous_feed_correction_kJph,
            places=6)


class TestEC1NoEvaporationCase(unittest.TestCase):
    def test_no_evaporation_when_water_is_already_low(self):
        warnings.filterwarnings("ignore")
        from biorefineries.sabre._chemicals import create_chemicals
        create_chemicals()
        feed = bst.Stream(Water=1.0, NaOH=0.9, Na2CO3=0.01, T=363.15, phase="l",
                          units="kg/hr")
        EC1 = NaOHEvaporator(None, ins=feed, T=363.15, heat_loss_fraction=0.05,
                             max_water_kgph=1.5)
        EC1.simulate()
        self.assertEqual(EC1._evaporated_water_kgph, 0.0)
        self.assertEqual(float(EC1.outs[1].F_mass), 0.0)
        self.assertAlmostEqual(EC1._heat_duty_kJph, 0.0, delta=1e-6)
        self.assertEqual(len([hu for hu in EC1.heat_utilities if hu.duty]), 0)


if __name__ == "__main__":
    unittest.main()
