"""Offline regression tests: no BioSTEAM required."""
from __future__ import annotations
import unittest

from biorefineries.sabre.analyses._att_c1_aqueous_reference import (
    AQUEOUS_SALT_HF_KJ_PER_KMOL, correct_reaction_enthalpy)

class AqueousReferenceTests(unittest.TestCase):
    def test_ionic_reference(self):
        self.assertEqual(AQUEOUS_SALT_HF_KJ_PER_KMOL['NaOH'],-470100.)
        self.assertEqual(AQUEOUS_SALT_HF_KJ_PER_KMOL['Na2CO3'],-1157300.)

    def test_c1_reaction_state_correction(self):
        x=.014800965388108156
        r=correct_reaction_enthalpy(
            inlet_Hnet_kJph=0,outlet_Hnet_kJph=839.2147375057393,
            inlet_kmolph={'Na2CO3':x,'NaOH':0},
            outlet_kmolph={'Na2CO3':0,'NaOH':2*x},
            chemical_Hf_kJ_per_kmol={'NaOH':-425800.,'Na2CO3':-1130700.})
        self.assertAlmostEqual(r.delta_correction_kJph,-62000*x,7)
        self.assertAlmostEqual(r.phase_reference_corrected_delta_kJph,839.2147375057393-62000*x,7)

    def test_no_reaction_no_correction(self):
        kw={'Na2CO3':.1,'NaOH':.01}
        r=correct_reaction_enthalpy(inlet_Hnet_kJph=-20,outlet_Hnet_kJph=0,
                inlet_kmolph=kw,outlet_kmolph=kw,
                chemical_Hf_kJ_per_kmol={'NaOH':-425800.,'Na2CO3':-1130700.})
        self.assertAlmostEqual(r.delta_correction_kJph,0)
        self.assertAlmostEqual(r.phase_reference_corrected_delta_kJph,20)

    def test_invalid_input(self):
        with self.assertRaises(ValueError):
            correct_reaction_enthalpy(inlet_Hnet_kJph=1,outlet_Hnet_kJph=2,
                                     inlet_kmolph={'NaOH':-1},outlet_kmolph={},
                                     chemical_Hf_kJ_per_kmol={'NaOH':-425800.,'Na2CO3':-1130700.})


if __name__=='__main__':unittest.main()
