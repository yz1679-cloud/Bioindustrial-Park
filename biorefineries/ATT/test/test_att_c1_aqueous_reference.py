"""Offline regression tests: no BioSTEAM required."""
from __future__ import annotations
import unittest

from biorefineries.ATT.analyses.thermodynamics import (
    correct_reaction_enthalpy)

class AqueousReferenceTests(unittest.TestCase):

    def test_c1_reaction_state_correction(self):
        x=.014800965388108156
        r=correct_reaction_enthalpy(
            inlet_Hnet_kJph=0,outlet_Hnet_kJph=839.2147375057393,
            inlet_kmolph={'Na2CO3':x,'NaOH':0},
            outlet_kmolph={'Na2CO3':0,'NaOH':2*x},
            chemical_Hf_kJ_per_kmol={'NaOH':-425800.,'Na2CO3':-1130700.})
        self.assertAlmostEqual(r.delta_correction_kJph,-62000*x,7)
        self.assertAlmostEqual(r.phase_reference_corrected_delta_kJph,839.2147375057393-62000*x,7)


if __name__=='__main__':unittest.main()
