"""EC1 evaporator (simple model) and the fresh NaOH makeup in M1."""
import unittest
import warnings

import biosteam as bst

from biorefineries.sabre.systems._att_system import create_att_system
from biorefineries.sabre.utils import load_assumptions
from biorefineries.sabre.units._att import NaOHEvaporator, aqueous_naoh_enthalpy_correction_kJph

_DS = load_assumptions("att.yaml")["att"]["downstream"]


class TestEC1Flowsheet(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        warnings.filterwarnings("ignore")
        cls.sys = create_att_system(dry_sargassum_kgph=1.0)
        cls.sys.set_tolerance(mol=1e-9, rmol=1e-9, T=1e-5, rT=1e-5,
                              maxiter=300, method="fixedpoint")
        cls.sys.simulate()
        cls.u = cls.sys.flowsheet.unit

    def test_evaporates_only_excess_water(self):
        EC1, M1 = self.u.EC1, self.u.M1
        gross = M1._required_gross_naoh_kgph
        self.assertAlmostEqual(EC1.outs[0].imass["Water"], gross, places=9)  # 50 %: water = NaOH
        recycle, fresh = M1.ins[1], M1.ins[2]
        self.assertIs(recycle, EC1.outs[0])
        naoh_total = recycle.imass["NaOH"] + fresh.imass["NaOH"]
        x = naoh_total / (naoh_total + recycle.imass["Water"])
        self.assertAlmostEqual(x, 0.5, places=6)
        self.assertAlmostEqual(naoh_total, gross, places=6)
        self.assertAlmostEqual(M1.outs[0].imass["NaOH"], gross, places=6)

    def test_condensation_uses_constant_boiling_point_elevation(self):
        EC1 = self.u.EC1
        bpe = _DS["ec1_boiling_point_elevation_K"]
        self.assertAlmostEqual(EC1._condensation_temperature_K, EC1.T - bpe, places=9)
        self.assertAlmostEqual(EC1._operating_pressure_Pa,
                               bst.Chemical("Water").Psat(EC1.T - bpe), places=6)
        self.assertLess(EC1._operating_pressure_Pa, 0.5 * bst.Chemical("Water").Psat(EC1.T))  # vacuum

    def test_carbonate_crystallizes_and_species_conserved(self):
        EC1 = self.u.EC1
        feed, conc, cond = EC1.ins[0], EC1.outs[0], EC1.outs[1]
        for ID in ("Water", "NaOH", "Na2CO3"):
            self.assertAlmostEqual(conc.imass[ID] + cond.imass[ID], feed.imass[ID], places=10)
        self.assertGreater(conc.imass["s", "Na2CO3"], 0.0)
        self.assertEqual(float(conc.imass["s", "NaOH"]), 0.0)

    def test_dissolved_na2co3_fraction(self):
        EC1 = self.u.EC1
        feed, conc = EC1.ins[0], EC1.outs[0]
        f = _DS["ec1_na2co3_dissolved_fraction"]
        self.assertAlmostEqual(conc.imass["l", "Na2CO3"], f * feed.imass["Na2CO3"], places=10)
        self.assertAlmostEqual(conc.imass["s", "Na2CO3"], (1.0 - f) * feed.imass["Na2CO3"], places=10)
        self.assertAlmostEqual(EC1._na2co3_crystals_kgph, conc.imass["s", "Na2CO3"], places=12)

    def test_ec1_duty_is_latent_heat_of_evaporated_water(self):
        EC1 = self.u.EC1
        Water = bst.Chemical("Water")
        latent = EC1._evaporated_water_kgph * Water.Hvap(EC1.T) / Water.MW
        sensible = float(EC1.ins[0].C) * (EC1.T - EC1.ins[0].T)
        self.assertAlmostEqual(EC1._heat_duty_kJph, latent + sensible, delta=1e-6)
        self.assertAlmostEqual(EC1._utility_heat_duty_kJph, 1.05 * EC1._heat_duty_kJph, delta=1e-6)
        self.assertLess(EC1._condenser_duty_kJph, -latent)  # includes vapor desuperheating

    def test_fresh_naoh_makeup_closes_the_loop(self):
        M1, U2 = self.u.M1, self.u.U2
        recycle, fresh = M1.ins[1], M1.ins[2]
        self.assertGreater(fresh.imass["NaOH"], 0.0)
        self.assertEqual(float(fresh.F_mass), float(fresh.imass["NaOH"]))  # pure NaOH, no water
        self.assertAlmostEqual(recycle.imass["NaOH"] + fresh.imass["NaOH"], M1._required_gross_naoh_kgph, places=6)
        self.assertAlmostEqual(U2.ins[0].imass["NaOH"], M1._required_gross_naoh_kgph, places=6)

    def test_u2_feed_naoh_correction_is_applied(self):
        U2 = self.u.U2
        self.assertLess(U2._aqueous_feed_correction_kJph, 0.0)
        self.assertAlmostEqual(
            U2._aqueous_feed_correction_kJph,
            aqueous_naoh_enthalpy_correction_kJph(self.u.M1.ins[1]),
            delta=1e-3)
        self.assertAlmostEqual(
            U2._inlet_Hnet_kJph,
            float(U2.ins[0].Hnet) + U2._feed_Hf_HHV_correction_kJph + U2._aqueous_feed_correction_kJph,
            places=6)


class TestAqueousNaOHCorrection(unittest.TestCase):
    def test_correction_is_heat_of_solution_minus_native_fusion(self):
        warnings.filterwarnings("ignore")
        from biorefineries.sabre._chemicals import create_chemicals
        create_chemicals(include_att=True)
        stream = bst.Stream(Water=1.0, NaOH=2.0, T=363.15, phase="l", units="kg/hr")
        NaOH = stream.chemicals["NaOH"]
        native = 2.0 / 39.997 * (NaOH.H("l", 363.15) - NaOH.H("s", 363.15))
        expected = -2.0 * _DS["naoh_heat_of_solution_kJ_per_kg"] - native
        self.assertAlmostEqual(aqueous_naoh_enthalpy_correction_kJph(stream), expected, places=6)
        self.assertEqual(aqueous_naoh_enthalpy_correction_kJph(bst.Stream(Water=1.0, units="kg/hr")), 0.0)


class TestEC1NoEvaporationCase(unittest.TestCase):
    def test_no_evaporation_when_water_is_already_low(self):
        warnings.filterwarnings("ignore")
        from biorefineries.sabre._chemicals import create_chemicals
        create_chemicals(include_att=True)
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
