# Bioindustrial-Park: BioSTEAM's Premier Biorefinery Models and Results
# Copyright (C) 2026-, Yu Zhou,
#                      Yalin Li <mailto.yalin.li@gmail.com>
#
# This module is under the UIUC open-source license. See
# github.com/BioSTEAMDevelopmentGroup/biosteam/blob/master/LICENSE.txt
# for license details.
"""
ATT: alkaline thermal treatment of Sargassum to H2 (independent project).

Started from a copy of the ATT model of biorefineries/sabre (Scenario 5, branch
sabre at 17c75376); it imports nothing from biorefineries.sabre. The baseline is
ATT Scenario 1 (analyses/scenarios.py, key "att_s1"); see IMPLEMENTATION_NOTES.md.

Submodules are imported explicitly, e.g.::

    from biorefineries.ATT.analyses import scenarios
    sys = scenarios.create(scenarios.ATT_S1)
"""
