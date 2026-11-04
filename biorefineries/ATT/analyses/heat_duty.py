# Bioindustrial-Park: BioSTEAM's Premier Biorefinery Models and Results
# Copyright (C) 2026-, Yu Zhou,
#                      Yalin Li <mailto.yalin.li@gmail.com>
#
# This module is under the UIUC open-source license. See
# github.com/BioSTEAMDevelopmentGroup/biosteam/blob/master/LICENSE.txt
# for license details.

"""
Heating duties of the ATT plant by unit operation and by physical origin (heating duties before heat integration,
per kg dry seaweed), split into low-grade (<= 100 C) and high-grade heat, in the format of the UCLA energy slides.
Used by the reference comparison of inventory.get_att_utility_consistency_check.
"""
import biosteam as bst

from biorefineries.ATT.analyses import inventory as inv
from biorefineries.ATT.units._att import _SARGASSUM_DRY_IDS

__all__ = ("get_heat",)
LOW_GRADE_T_K = 373.15            # <= 100 C = low-grade (waste-heat usable), as in the slides


def _u2_low_share(U2):
    """Share of U2's feed-heating duty that is needed at <= 100 C (liquid heating, vaporization at 100 C, solids to 100 C)."""
    feed = U2.ins[0]
    T_in = float(feed.T)
    st = U2._make_thermal_state
    w_low = float(st(feed, ("Water",), "g", LOW_GRADE_T_K).H - st(feed, ("Water",), "l", T_in).H)
    sensible = [(_SARGASSUM_DRY_IDS, "s"), (("NaOH",), "l")]
    s_low = sum(float(st(feed, ids, ph, LOW_GRADE_T_K).H - st(feed, ids, ph, T_in).H) for ids, ph in sensible)
    return w_low, s_low


def get_heat(sys):
    """Heating duties [kJ/h] by unit and by physical origin, utility basis (incl. the 5 % heat-loss allowance)."""
    u = inv._units(sys)
    dry = inv._dry_feed_kgph(sys)
    water = bst.settings.chemicals["Water"]
    U2, C1, EC1, D0, U3D = u["U2"], u["C1"], u["EC1"], u["D0"], u["U3D"]

    def heating(unit):
        return sum(hu.duty for hu in unit.heat_utilities if hu.duty > 0.0)

    unit_heat = {"D0": heating(D0), "U2": heating(U2), "C1": heating(C1), "EC1": heating(EC1), "U3D": heating(U3D)}
    cake_dryers = [u[ID] for ID in ("D2", "D3") if ID in u]        # CaCO3 cake dryers (downstream.caco3_drying)
    for D in cake_dryers:
        unit_heat[D.ID] = heating(D)
    if "K1" in u:
        unit_heat["K1"] = heating(u["K1"])        # lime kiln (lime recycle): natural gas, high-grade
    loss = {"U2": float(U2._heat_loss_kJph), "C1": float(C1._heat_loss_kJph), "EC1": float(EC1._heat_loss_kJph)}
    # D0: latent heat of the evaporated water; the rest is sensible (solids, air)
    d0_latent = float(D0.design_results["Evaporation"]) * float(water.Hvap(D0.T)) / float(water.MW)
    d0_sensible = unit_heat["D0"] - d0_latent
    cake_latent = sum(float(D.design_results["Evaporation"]) * float(water.Hvap(D.T)) / float(water.MW) for D in cake_dryers)
    cake_sensible = sum(unit_heat[D.ID] for D in cake_dryers) - cake_latent
    # U2 breakdown
    aq = float(U2._aqueous_feed_correction_kJph)
    u2_rxn_all = float(U2._reaction_and_product_state_kJph)
    naoh_solution = -aq                               # NaOH heat of solution released in M1, not recovered
    reaction = u2_rxn_all - naoh_solution             # reaction + product state (+ feed Hf re-referenced to the HHV)
    u2_water = float(U2._water_heating_duty_kJph)
    u2_sens = float(U2._dry_sargassum_heating_duty_kJph + U2._naoh_heating_duty_kJph + U2._other_heating_duty_kJph)
    w_low, s_low = _u2_low_share(U2)
    u2_process = float(U2._heat_duty_kJph)
    u2_low_proc = w_low + s_low
    u2_low_share = u2_low_proc / u2_process
    c1_process, ec1_process = float(C1._heat_duty_kJph), float(EC1._heat_duty_kJph)
    u3d_heat = unit_heat["U3D"]

    origin = {   # step -> (kJ/h, low-grade kJ/h)
        "Reaction enthalpy (U2)": (reaction, 0.0),
        "NaOH heat of solution (not recovered)": (naoh_solution, 0.0),
        "Water heating and vaporization (U2)": (u2_water, w_low),
        "Sensible heat of solids and NaOH (U2)": (u2_sens, s_low),
        "Water evaporation, feed dryer (D0)": (d0_latent, d0_latent),
        "Sensible heat in the dryer (D0)": (d0_sensible, d0_sensible),
        **({"Water evaporation, CaCO3 cake dryers (D2, D3)": (cake_latent, cake_latent),
            "Sensible heat in the CaCO3 cake dryers (D2, D3)": (cake_sensible, cake_sensible)} if cake_dryers else {}),
        "Causticizing (C1)": (c1_process, c1_process),
        "Water evaporation, NaOH concentrator (EC1)": (ec1_process, ec1_process),
        "Gas-drying regeneration (U3D)": (u3d_heat, 0.0),
        **({"Lime kiln: calcination and cake drying (K1)": (unit_heat["K1"], 0.0)} if "K1" in unit_heat else {}),
        "Heat losses": (sum(loss.values()),
                        loss["U2"] * u2_low_share + loss["C1"] + loss["EC1"]),
    }
    # Informational, not in the model's energy balance: Na2CO3 heat of solution (-26.7 kJ/mol) in D1
    na2co3_kmol = float(u["D1"].ins[0].imol["Na2CO3"])
    dissolution_estimate = -26.7e3 * na2co3_kmol                    # kJ/kmol x kmol/h = kJ/h
    total = sum(v for v, _ in origin.values())
    assert abs(total - sum(unit_heat.values())) < 1e-6 * total, (total, sum(unit_heat.values()))
    low = sum(l for _, l in origin.values())
    return dict(unit=unit_heat, origin=origin, total=total, dissolution_estimate_kJph=dissolution_estimate, low=low, high=total - low, dry=dry,
                water_handling=sum(origin[k][0] for k in origin if k.startswith("Water")) )

