# Bioindustrial-Park: BioSTEAM's Premier Biorefinery Models and Results
# Copyright (C) 2026-, Yu Zhou,
#                      Yalin Li <mailto.yalin.li@gmail.com>
#
# This module is under the UIUC open-source license. See
# github.com/BioSTEAMDevelopmentGroup/biosteam/blob/master/LICENSE.txt
# for license details.

"""ATT thermochemistry: the C1 aqueous enthalpy reference.

C1 phase-consistent standard-state reference (used by
units/_att.CausticizationReactor): standard aqueous-ion formation enthalpy
values at 298.15 K (CRC, approximate rounded entries). Does NOT model
concentrated-solution excess/mixing enthalpy, temperature-dependent
activities, or validate chemical solubility.

Concentrated-solution limitation (bounded, not modelled; see att.yaml
``c1_energy_basis_status``): relative enthalpies of 25 wt% Na2CO3(aq) and
17.6 wt% NaOH(aq), the solution heat capacity and the reaction heat-capacity
change together shift the baseline C1 process duty (1700 kJ/h) by about
-40 to +300 kJ/h, i.e. -0.2 to +1.2 % of total plant heating. The molten-salt
phase offset BioSTEAM assigns to dissolved salts nets to ~1 kJ/h, so the
infinite-dilution Hf is not double-counted with a fusion enthalpy.

All C1 numbers and units explicitly in kJ/kmol, kmol/h and kJ/h.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

__all__ = (
    "ReferenceCorrection",
    "correct_reaction_enthalpy",
    "from_reactor_streams",
)


# ==========================================================================
# C1 causticization: standard aqueous-ion enthalpy reference
# ==========================================================================

# Rounded conventional standard formation enthalpies (kJ/kmol, 298.15 K):
# Na+(aq) -240.1 kJ/mol, OH-(aq) -230.0 kJ/mol, CO3--(aq) -677.1 kJ/mol.
# CRC Handbook of Chemistry and Physics, aqueous ions table (2015).
ION_HF_KJ_PER_KMOL = {'Na+': -240100.0, 'OH-': -230000.0, 'CO3--': -677100.0}
AQUEOUS_SALT_HF_KJ_PER_KMOL = {
    'NaOH': ION_HF_KJ_PER_KMOL['Na+'] + ION_HF_KJ_PER_KMOL['OH-'],
    'Na2CO3': 2 * ION_HF_KJ_PER_KMOL['Na+'] + ION_HF_KJ_PER_KMOL['CO3--'],
}
REFERENCE_SCOPE = '298.15_K_INFINITE_DILUTION_AQUEOUS_IONS__CONCENTRATED_SOLUTION_ENTHALPY_BOUNDED_NOT_MODELLED'

@dataclass(frozen=True)
class ReferenceCorrection:
    inlet_correction_kJph: float
    outlet_correction_kJph: float
    delta_correction_kJph: float
    uncorrected_Hnet_delta_kJph: float
    phase_reference_corrected_delta_kJph: float
    reaction_formation_delta_kJph: float
    provenance: str = REFERENCE_SCOPE


def correct_reaction_enthalpy(*, inlet_Hnet_kJph: float, outlet_Hnet_kJph: float,
                              inlet_kmolph: dict, outlet_kmolph: dict,
                              chemical_Hf_kJ_per_kmol: dict) -> ReferenceCorrection:
    """Replace native NaOH and Na2CO3 Hf by standard aqueous reference Hf.

    The two salt components must represent dissolved liquor; Ca(OH)2 and
    CaCO3 remain solid. Physical concentrations/heat-of-mixing are NOT solved.
    """
    for v in (inlet_Hnet_kJph, outlet_Hnet_kJph):
        if not isfinite(float(v)):
            raise ValueError('Non-finite Hnet')
    def correction(mols):
        result=0.
        for chem, target_hf in AQUEOUS_SALT_HF_KJ_PER_KMOL.items():
            n=float(mols.get(chem,0.))
            source_hf=float(chemical_Hf_kJ_per_kmol[chem])
            if n < -1e-12 or not all(map(isfinite,(n,source_hf))):
                raise ValueError(f'Invalid {chem} amount/reference')
            result+=n*(target_hf-source_hf)
        return result
    ins=correction(inlet_kmolph)
    outs=correction(outlet_kmolph)
    uncorrected=float(outlet_Hnet_kJph)-float(inlet_Hnet_kJph)
    delta=outs-ins
    n2delta=(float(outlet_kmolph.get('NaOH',0))-float(inlet_kmolph.get('NaOH',0)))
    cdelta=(float(outlet_kmolph.get('Na2CO3',0))-float(inlet_kmolph.get('Na2CO3',0)))
    # Only change in aqueous-standard formation term, not sensible or solid lime/calcite reference.
    return ReferenceCorrection(ins,outs,delta,uncorrected,uncorrected+delta,
                               n2delta*AQUEOUS_SALT_HF_KJ_PER_KMOL['NaOH']+cdelta*AQUEOUS_SALT_HF_KJ_PER_KMOL['Na2CO3'])


def from_reactor_streams(carbonate_solution, lime, slurry):
    """Read actual native BioSTEAM streams, no change to material compositions."""
    if float(carbonate_solution.imass['Water']) <= 0 or float(slurry.imass['Water']) <= 0:
        raise ValueError('C1 aqueous reference requires liquid water at inlet and outlet')
    species=('NaOH','Na2CO3')
    inlet={k:float(carbonate_solution.imol[k])+float(lime.imol[k]) for k in species}
    outlet={k:float(slurry.imol[k]) for k in species}
    hf={k:float(slurry.chemicals[k].Hf) for k in species}
    return correct_reaction_enthalpy(inlet_Hnet_kJph=float(carbonate_solution.Hnet + lime.Hnet),
                                    outlet_Hnet_kJph=float(slurry.Hnet),
                                    inlet_kmolph=inlet,outlet_kmolph=outlet,chemical_Hf_kJ_per_kmol=hf)
