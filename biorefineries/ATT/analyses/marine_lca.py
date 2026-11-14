# Bioindustrial-Park: BioSTEAM's Premier Biorefinery Models and Results
# Copyright (C) 2026-, Yu Zhou,
#                      Yalin Li <mailto.yalin.li@gmail.com>
#
# This module is under the UIUC open-source license. See
# github.com/BioSTEAMDevelopmentGroup/biosteam/blob/master/LICENSE.txt
# for license details.

"""
ATT Scenario 2: INCREMENTAL process GWP of marine waste heat recovery on top of the unchanged ATT S1 LCA
(analyses/lca.py, same factors and boundary). The recovered heat replaces purchased LP steam (natural-gas
boiler) and, for the U2 feed preheater, U2 furnace natural gas; the WHR pumps add electricity. The waste heat
itself carries no burden in this INCREMENTAL view: it is available from propulsion that happens anyway. This is
not a ship lifecycle footprint: propulsion fuel and its emissions are not allocated to ATT (no fuel-use data), and
no credit is taken for them.
"""
from biorefineries.ATT.analyses import inventory as inv
from biorefineries.ATT.analyses import lca

__all__ = ("whr_gwp_change",)


def whr_gwp_change(sys, whr, overrides=None):
    """Change of the ATT process GWP by WHR [kg CO2e per kg H2 and per hour]; negative = reduction."""
    f = lca._factors(overrides)
    eta = lca._LCA["natural_gas"]
    ng = f["natural_gas_combustion"] + f["natural_gas_upstream"]      # kg CO2e per MJ fuel
    steam_kW = sum(a["assigned_kW"] for a in whr["assignments"] if "steam" in a["sink_utility"])
    gas_kW = sum(a["assigned_kW"] for a in whr["assignments"] if "natural_gas" in a["sink_utility"])
    avoided_steam = steam_kW * 3.6 / eta["boiler_efficiency"] * ng           # kg CO2e/h (kW x 3.6 MJ/kWh)
    avoided_gas = gas_kW * 3.6 / eta["burner_efficiency"] * ng
    pumps = whr["pump_kW"] * f["electricity"]
    h2 = float(inv._streams(sys)["h2_product"].imass["H2"])
    delta = pumps - avoided_steam - avoided_gas
    return dict(avoided_steam_kgCO2e_per_h=avoided_steam, avoided_U2_gas_kgCO2e_per_h=avoided_gas,
                pump_electricity_kgCO2e_per_h=pumps, delta_kgCO2e_per_h=delta, delta_kgCO2e_per_kg_H2=delta / h2)
