# Bioindustrial-Park: BioSTEAM's Premier Biorefinery Models and Results
# Copyright (C) 2026-, Yu Zhou,
#                      Yalin Li <mailto.yalin.li@gmail.com>
#
# This module is under the UIUC open-source license. See
# github.com/BioSTEAMDevelopmentGroup/biosteam/blob/master/LICENSE.txt
# for license details.

"""
ATT (alkaline thermal treatment) analyses: library modules and the run scripts (att_*.py).

Submodules are imported explicitly (nothing is imported here, so that
system.py and units/_att.py can use the process-level helpers
without loading the reporting stack):

Process-level helpers (called by the model itself)
    mass_energy      energy accounting; F2 cake wash balance (W2)
    thermodynamics   C1 aqueous enthalpy reference

Full-scale analyses (frozen BioSTEAM model)
    inventory        material/energy inventory, cost inputs
    heat_duty        heating duties by unit and origin (UCLA slides reference)
    tea              minimum H2 selling price (ATTTEA)
    lca              GWP100 (BioSTEAM impact framework)

Reporting
    reporting        consolidated results; master documentation package
    breakdown        MSP / CAPEX / OPEX / GWP breakdown of the ATT scenarios

Diagnostics (read-only audits)
    validation       1 kg/h mass/energy audit

Runners
    run              export steps and the full pipeline (python -m biorefineries.ATT.analyses.run)
    att_*.py         scenario, S2 and washing tables (results/tables)

Output locations
    paths            default result folders under biorefineries/ATT/results/
"""
