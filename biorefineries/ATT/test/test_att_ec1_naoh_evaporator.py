"""EC1 evaporator (simple model) and the fresh NaOH makeup in M1."""
import unittest
import warnings

import biosteam as bst

from biorefineries.ATT.system import create_att_system
from biorefineries.ATT.utils import load_assumptions

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

    def test_naoh_loop_closes(self):
        EC1, M1 = self.u.EC1, self.u.M1
        gross = M1._required_gross_naoh_kgph
        self.assertAlmostEqual(EC1.outs[0].imass["Water"], gross, places=9)  # 50 %: water = NaOH
        recycle, fresh = M1.ins[1], M1.ins[2]
        self.assertIs(recycle, self.u.XL1.outs[0])          # the salt crystallizer XL1 follows EC1
        self.assertIs(self.u.XL1.ins[0], EC1.outs[0])
        naoh_total = recycle.imass["NaOH"] + fresh.imass["NaOH"]
        x = naoh_total / (naoh_total + recycle.imass["Water"])
        self.assertAlmostEqual(x, 0.5, delta=0.005)          # XL1 removes a little liquor with the salt cake
        self.assertAlmostEqual(naoh_total, gross, places=6)
        self.assertAlmostEqual(M1.outs[0].imass["NaOH"], gross, places=6)
        M1, U2 = self.u.M1, self.u.U2
        recycle, fresh = M1.ins[1], M1.ins[2]
        self.assertGreater(fresh.imass["NaOH"], 0.0)
        self.assertEqual(float(fresh.F_mass), float(fresh.imass["NaOH"]))  # pure NaOH, no water
        self.assertAlmostEqual(recycle.imass["NaOH"] + fresh.imass["NaOH"], M1._required_gross_naoh_kgph, places=6)
        self.assertAlmostEqual(U2.ins[0].imass["NaOH"], M1._required_gross_naoh_kgph, places=6)


    def test_carbonate_crystallizes_and_species_conserved(self):
        EC1 = self.u.EC1
        feed, conc, cond = EC1.ins[0], EC1.outs[0], EC1.outs[1]
        for ID in ("Water", "NaOH", "Na2CO3"):
            self.assertAlmostEqual(conc.imass[ID] + cond.imass[ID], feed.imass[ID], places=10)
        self.assertGreater(conc.imass["s", "Na2CO3"], 0.0)
        self.assertEqual(float(conc.imass["s", "NaOH"]), 0.0)


    def test_ec1_duty_is_latent_heat_of_evaporated_water(self):
        EC1 = self.u.EC1
        Water = bst.Chemical("Water")
        latent = EC1._evaporated_water_kgph * Water.Hvap(EC1.T) / Water.MW
        sensible = float(EC1.ins[0].C) * (EC1.T - EC1.ins[0].T)
        self.assertAlmostEqual(EC1._heat_duty_kJph, latent + sensible, delta=1e-6)
        self.assertAlmostEqual(EC1._utility_heat_duty_kJph, 1.05 * EC1._heat_duty_kJph, delta=1e-6)
        self.assertLess(EC1._condenser_duty_kJph, -latent)  # includes vapor desuperheating


if __name__ == "__main__":
    unittest.main()
