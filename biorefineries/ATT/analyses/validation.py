# Bioindustrial-Park: BioSTEAM's Premier Biorefinery Models and Results
# Copyright (C) 2026-, Yu Zhou,
#                      Yalin Li <mailto.yalin.li@gmail.com>
#
# This module is under the UIUC open-source license. See
# github.com/BioSTEAMDevelopmentGroup/biosteam/blob/master/LICENSE.txt
# for license details.

"""ATT diagnostic audits (read-only; never used by the process model).

- 1 kg/h process mass and energy audit: runs the frozen ATT model
  (create_att_system, active U2 closure) at exactly 1 kg/h dry feed in its
  own flowsheet registry and extracts streams, balances and energy flows with
  the existing inventory and reporting helpers. A full-scale (ATT S1
  capacity) run is used only for the comparison sheet. Writes
  results/baseline_1kg/. Nothing is written elsewhere and no model,
  LCA or TEA setting is changed.
- Sodium (Na) ledger: per-unit Na balances and the external Na balance
  across the actual graph of ``sys.units``. Run only after convergence.
"""
from __future__ import annotations

import os
import re
import warnings


from biorefineries.ATT.analyses import inventory as inv
from biorefineries.ATT.analyses import reporting as rep
from biorefineries.ATT.utils import load_assumptions

__all__ = (
    "simulate_att_1kgph",
    "build_att_1kgph_audit",
    "export_att_1kgph_audit",
)


# ==========================================================================
# 1 kg/h process mass and energy audit
# ==========================================================================

WORKBOOK = "ATT_1kgph_Process_Mass_Energy_Audit.xlsx"
_ATT = load_assumptions("att.yaml")["att"]
_LCA = load_assumptions("att_lca.yaml")["lca"]
_MW = {"H2": 2.01588, "CH4": 16.04246, "CO": 28.0101, "CO2": 44.0095, "NaOH": 39.99711, "H2O": 18.01528}


def simulate_att_1kgph(dry_kgph=1.0):
    """Frozen model at the given dry feed; returns (system, captured warnings)."""
    from biorefineries.ATT.system import create_att_system

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        sys = inv._simulate(create_att_system(dry_sargassum_kgph=dry_kgph), dry_kgph)
    messages = sorted({_clean(f"{w.category.__name__}: {w.message}") for w in caught
                       if "replaced in registry" not in str(w.message)})
    return sys, messages


def _clean(text):
    # Remove terminal color codes from BioSTEAM warning messages.
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


# ---------------------------------------------------------------------------
# Sheets
# ---------------------------------------------------------------------------

def _basis(sys):
    U2 = inv._units(sys)["U2"]
    s = inv._streams(sys)
    dry = inv._dry_feed_kgph(sys)
    daf = float(U2._daf_sargassum_kgph)
    case = _ATT["reactor"]["cases"][_ATT["reactor"]["baseline_case"]]
    y = case["gas_yield_mmol_per_g_daf"]
    feed = U2.ins[0]
    rows = []

    def add(group, item, experiment, model, unit, note):
        rows.append(dict(group=group, item=item, UCLA_experiment=experiment, model_1kgph=model, unit=unit, note=note))

    add("Feed", "Sargassum", 0.25, daf * 1e3, "g seaweed, basis not stated (experiment) | g daf/h (model)",
        "Experiment: 0.25 g seaweed (workbook 261023, mass basis not stated); model: 1 kg/h dry x daf fraction")
    add("Feed", "daf / dry", 1 - 0.172, daf / dry, "-", "workbook ash 17.2 wt% dry | model presscake ash 32.07 wt% dry")
    add("Feed", "Dry Sargassum", float("nan"), dry, "kg/h", "Model basis")
    add("Feed", "Wet Sargassum as harvested", float("nan"), float(s["att_sargassum_feed"].F_mass), "kg/h",
        "presscake moisture 0.763 (feedstock.yaml nlr_pressed)")
    add("NaOH", "NaOH", 0.25, float(feed.imass["NaOH"]), "g (experiment) | kg/h (model)", "")
    add("NaOH", "NaOH : dry", float("nan"), float(feed.imass["NaOH"]) / dry, "kg/kg dry",
        "att.yaml reactor.cases.Ni-CatATT_1to1.naoh_kg_per_kg_dry = 1.0 (experiment: 0.25 g : 0.25 g, basis not stated)")
    steam_g_per_g_daf = 3.6 / 0.25   # 3.6 g steam over the run (workbook 261023 footnote); seaweed basis not stated
    water_u2 = float(feed.imass["Water"])
    add("Water/steam", "Steam over the run (3.6 g per 0.25 g seaweed)", steam_g_per_g_daf, steam_g_per_g_daf * daf,
        "g/g daf (exp.) | kg/h equivalent (model basis)",
        "Experiment: 0.03 mL/min steam for 1 h through a fixed bed with N2 carrier; NOT a model feed")
    add("Water/steam", "Water entering U2 (model)", float("nan"), water_u2, "kg/h",
        "= feed moisture at 50 wt% (D0 outlet) + water in the 50 % NaOH recycle liquor; no separate steam feed")
    add("Water/steam", "Water entering U2 per kg daf (model)", steam_g_per_g_daf, water_u2 / daf, "kg/kg daf",
        "Model water/daf vs experimental steam/daf")
    add("Water/steam", "U2 net water consumption (model)", float("nan"), -U2._net_water_formation_kmolph * _MW["H2O"],
        "kg/h", "Water reacted (H2 from water via C oxidation); far below either supply")
    for gas in ("H2", "CH4", "CO", "CO2"):
        mol_h = float(y[gas]) * daf  # mmol/g x kg/h = mol/h
        model = float(U2.outs[0].imol[gas]) * 1e3
        add("Gas yield", f"{gas}", float(y[gas]), model / daf, "mmol/g daf",
            "SPECIFIED (measured, Ni-CatATT 1:1); residual carbon goes to the char, not to CO2" +
            f" | experiment-equivalent {mol_h:.4f} mol/h = {mol_h * _MW[gas] / 1e3:.6f} kg/h at 1 kg/h dry")
    add("Gas yield", "H2 product", float("nan"), float(s["h2_product"].imass["H2"]), "kg/h", "")
    add("Conditions", "Temperature / hold", "500 C, 1 h", f"{_ATT['reactor']['target_temperature_K'] - 273.15:.0f} C",
        "-", "Experiment: N2 25 mL/min, steam 0.03 mL/min, 10 wt% Ni/ZrO2 (Ni-CatATT); model: no N2, no catalyst species")
    return rows


def _stream_inventory(sys):
    rows, comp = [], []
    seen = set()
    for u in sys.units:
        for s in (*u.ins, *u.outs):
            if s.ID in seen:
                continue
            seen.add(s.ID)
            F = float(s.F_mass)
            head = dict(stream=s.ID, from_unit=s.source.ID if s.source else "FEED (input)",
                        to_unit=s.sink.ID if s.sink else "PRODUCT (output)", T_C=float(s.T) - 273.15,
                        P_kPa=float(s.P) / 1e3, phase=s.phase)
            rows.append(dict(head, total_kg_per_h=F, total_mol_per_h=float(s.F_mol) * 1e3,
                             water_kg_per_h=float(s.imass["Water"]),
                             water_mass_fraction=float(s.imass["Water"]) / F if F else float("nan"),
                             mass_fraction_sum=sum(float(m) for m in s.mass) / F if F else float("nan")))
            for ID, m, n in zip(s.chemicals.IDs, s.mass, s.mol):
                if m != 0.0:
                    comp.append(dict(head, component=ID, kg_per_h=float(m), mol_per_h=float(n) * 1e3,
                                     mass_fraction=float(m) / F if F else float("nan")))
    return rows, comp


def _mass_summary(sys):
    s = inv._streams(sys)
    U2 = inv._units(sys)["U2"]
    u = inv._units(sys)
    gas, residue = U2.outs
    rows = []

    def add(item, value, unit="kg/h", note=""):
        rows.append(dict(item=item, value=value, unit=unit, note=note))

    feed = s["att_sargassum_feed"]
    add("Wet Sargassum input", float(feed.F_mass))
    add("Dry Sargassum input", inv._dry_feed_kgph(sys))
    add("daf Sargassum", float(U2._daf_sargassum_kgph))
    add("Ash", float(feed.imass["Ash"]))
    add("Feed moisture", float(feed.imass["Water"]))
    add("D0 water evaporated", float(s["dryer_exhaust"].imass["Water"]))
    add("NaOH gross into U2", float(U2.ins[0].imass["NaOH"]))
    add("Fresh NaOH makeup", float(s["fresh_naoh_solid"].imass["NaOH"]))
    add("Recycled NaOH (EC1 concentrate)", float(u["EC1"].outs[0].imass["NaOH"]))
    add("Water into U2", float(U2.ins[0].imass["Water"]), note="no separate steam feed")
    add("D1 dissolution water", float(s["dissolution_water"].F_mass))
    add("U2 gas outlet (total)", float(gas.F_mass))
    for ID in ("H2", "CO2", "Water", "CH4", "CO"):
        add(f"  U2 gas {ID}", float(gas.imass[ID]))
    add("U2 residue outlet (total)", float(residue.F_mass))
    for ID in ("Na2CO3", "Ash", "NaOH"):
        add(f"  U2 residue {ID}", float(residue.imass[ID]))
    add("H2 before PSA", float(gas.imass["H2"]))
    add("H2 product", float(s["h2_product"].imass["H2"]))
    add("Na2CO3 formed in U2", float(residue.imass["Na2CO3"] - U2.ins[0].imass["Na2CO3"]))
    C1 = u["C1"]
    add("Na2CO3 into C1", float(C1.ins[0].imass["Na2CO3"]))
    add("Na2CO3 converted in C1", float(C1.ins[0].imass["Na2CO3"] - C1.outs[0].imass["Na2CO3"]))
    add("Ca(OH)2 requirement", float(s["lime"].F_mass))
    add("CaCO3 generated", float(C1.outs[0].imass["CaCO3"]))
    add("Ash/char filter cake (F1)", float(s["att_char"].F_mass))
    add("CaCO3 filter cake (F2)", float(s["caco3_cake"].F_mass))
    for ID in _LCA["waste_management"]["wastewater_streams"]:
        if ID in s:
            add(f"Wastewater/purge: {ID}", float(s[ID].F_mass))
    add("PSA off-gas", float(inv._tail_gas(sys).F_mass))
    return rows


def _energy(sys):
    """Unit-level energy audit in kJ/h and kW (actual 1 kg/h simulation)."""
    burner = float(_ATT["energy_sources"]["natural_gas"]["burner_efficiency"])
    boiler = float(_LCA["natural_gas"]["boiler_efficiency"])
    notes = {u: rep._UNIT_INFO.get(u, ("", ""))[0] for u in rep._UNIT_INFO}
    balance = {r["unit"]: r for r in inv.get_att_unit_energy_balance(sys)}
    dry = inv._dry_feed_kgph(sys)
    rows = []
    for unit in sys.units:
        b = balance[unit.ID]
        heating = [hu for hu in unit.heat_utilities if hu.duty > 0]
        cooling = [hu for hu in unit.heat_utilities if hu.duty < 0]
        q_heat = sum(hu.unit_duty for hu in heating)
        q_util = sum(hu.duty for hu in heating)
        steam = [hu for hu in heating if hu.agent.ID.endswith("steam")]
        gas = [hu for hu in heating if hu.agent.ID == "natural_gas"]
        rows.append(dict(
            unit=unit.ID, cls=type(unit).__name__,
            Hnet_in_kJ_per_h=sum(float(x.Hnet) for x in unit.ins), Hnet_out_kJ_per_h=sum(float(x.Hnet) for x in unit.outs),
            process_heating_kJ_per_h=q_heat, process_cooling_kJ_per_h=sum(hu.unit_duty for hu in cooling),
            heat_loss_kJ_per_h=q_util - q_heat, purchased_heating_utility_kJ_per_h=q_util,
            heating_agent=",".join(hu.agent.ID for hu in heating),
            steam_kg_per_h=sum(hu.flow * hu.agent.MW for hu in steam),
            boiler_NG_LHV_kJ_per_h=sum(hu.duty for hu in steam) / boiler,
            NG_fuel_LHV_kJ_per_h=sum(hu.duty for hu in gas) / burner,
            electricity_kW=unit.power_utility.rate,
            enthalpy_residual_kJ_per_h=b["residual_MJ_per_kg_dry"] * 1e3 * dry,
            residual_explanation=b["explanation"], function=notes.get(unit.ID, ""),
        ))
    totals = {k: sum(r[k] for r in rows) for k in ("process_heating_kJ_per_h", "process_cooling_kJ_per_h",
                                                     "heat_loss_kJ_per_h", "purchased_heating_utility_kJ_per_h",
                                                     "steam_kg_per_h", "boiler_NG_LHV_kJ_per_h",
                                                     "NG_fuel_LHV_kJ_per_h", "electricity_kW")}
    rows.append(dict(unit="TOTAL", cls="", **totals))
    return rows


def _utilities(sys, estimates):
    rows = inv.get_att_purchased_utilities(sys, estimates)
    out = []
    for r in rows:
        unit = r["unit"].replace("/kg dry", "/h")
        if unit.startswith("MJ"):
            value, unit = r["per_kg_dry"] * inv._dry_feed_kgph(sys) * 1e3, "kJ/h"
        elif unit.startswith("kWh"):
            value, unit = r["per_kg_dry"] * inv._dry_feed_kgph(sys), "kW"
        else:
            value = r["per_kg_dry"] * inv._dry_feed_kgph(sys)
        out.append(dict(item=r["item"], value=value, unit=unit, note=r["note"]))
    out.append(dict(item="Conversion rule", value=float("nan"), unit="",
                    note="process duty -> delivered heat (x 1.05 loss) -> fuel LHV (/ 0.90 burner, / 0.80 boiler)"))
    return out


def _energy_detail(sys):
    rows = rep._energy_accounts(sys)
    dry = inv._dry_feed_kgph(sys)
    for r in rows:
        if r["unit"] == "MJ/kg dry":
            r["value"], r["unit"] = r["value"] * 1e3 * dry, "kJ/h"
        elif r["unit"] == "kg/kg dry":
            r["value"], r["unit"] = r["value"] * dry, "kg/h"
        elif r["unit"] == "kWh/kg dry":
            r["value"], r["unit"] = r["value"] * dry, "kW"
    return rows


def _comparison(small, ref):
    """Actual 1 kg/h simulation vs full-scale results normalized per kg dry."""
    def q(sys):
        s = inv._streams(sys)
        u = inv._units(sys)
        dry = inv._dry_feed_kgph(sys)
        hu = lambda unit, sign: sum(h.duty for h in u[unit].heat_utilities if h.duty * sign > 0) / dry
        ww = sum(float(s[ID].F_mass) for ID in _LCA["waste_management"]["wastewater_streams"] if ID in s) / dry
        steam = sum(h.flow * h.agent.MW for h in sys.heat_utilities if h.agent.ID.endswith("steam")) / dry
        gas = sum(h.duty for h in sys.heat_utilities if h.agent.ID == "natural_gas") / dry / 0.9
        cooling = -sum(h.duty for h in sys.heat_utilities if h.duty < 0) / dry
        out = {
            "H2 product [kg/kg dry]": float(s["h2_product"].imass["H2"]) / dry,
            "NaOH makeup [kg/kg dry]": float(s["fresh_naoh_solid"].F_mass) / dry,
            "NaOH into U2 [kg/kg dry]": float(u["U2"].ins[0].imass["NaOH"]) / dry,
            "Ca(OH)2 [kg/kg dry]": float(s["lime"].F_mass) / dry,
            "CaCO3 generated [kg/kg dry]": float(u["C1"].outs[0].imass["CaCO3"]) / dry,
            "Process water (D1) [kg/kg dry]": float(s["dissolution_water"].F_mass) / dry,
            "Wastewater + purge [kg/kg dry]": ww,
            "U2 utility heat [kJ/kg dry]": hu("U2", 1),
            "D0 utility heat [kJ/kg dry]": hu("D0", 1),
            "C1 utility heat [kJ/kg dry]": hu("C1", 1),
            "EC1 utility heat [kJ/kg dry]": hu("EC1", 1),
            "U2 natural gas fuel LHV [kJ/kg dry]": gas,
            "LP steam [kg/kg dry]": steam,
            "Cooling duty [kJ/kg dry]": cooling,
        }
        for unit in sys.units:
            if unit.power_utility.rate > 0:
                out[f"{unit.ID} electricity [kWh/kg dry]"] = unit.power_utility.rate / dry
        out["Electricity, modeled units [kWh/kg dry]"] = sys.power_utility.rate / dry
        return out

    a, b = q(small), q(ref)
    sizing = {"D0": "DrumDryer power from a size correlation with a minimum drum size (scale dependent)",
              "F2": "RotaryVacuumFilter minimum area and vacuum pump (scale dependent)",
              "Electricity, modeled units": "sum includes the scale-dependent D0 and F2 power"}
    rows = []
    for k in a:
        diff = (a[k] - b[k]) / b[k] if b[k] else float("nan")
        key = k.split(" electricity")[0].split(" [")[0]
        if abs(diff) <= 1e-6:
            expl = "Scale-independent (same per kg dry; recycle tolerance ~1e-11)"
        else:
            expl = sizing.get(key, "Scale-dependent BioSTEAM equipment correlation")
        rows.append(dict(parameter=k, actual_1kgph_simulation=a[k], full_scale_normalized_per_kg_dry=b[k],
                         relative_difference=diff, explanation=expl))
    rows.append(dict(parameter="Equipment sizes and purchase costs", actual_1kgph_simulation=float("nan"),
                     full_scale_normalized_per_kg_dry=float("nan"), relative_difference=float("nan"),
                     explanation="Not comparable: minimum sizes, parallel units at full scale "
                                 "(e.g. U3K compressors, F2 filters); costs are not linear in capacity"))
    return rows


_ATOMIC_MASS = {"H": 1.008, "C": 12.011, "O": 15.999, "N": 14.007, "S": 32.06}


def _checks(sys, warnings_list):
    rows = []
    c = inv.check_att_inventory(sys)
    # U2 takes specified yields, so the identified products can hold less of an element than the feed
    # (the unidentified products are not modeled). That accepted residual (outlet - inlet, kmol/h) is
    # removed from the closure checks, which then test everything else; it is reported separately.
    U2 = inv._units(sys)["U2"]
    unresolved = {e: float(v) for e, v in U2._unresolved_element_kmolph.items() if abs(v) > 0.0}
    sys_in = {e: sum(float(f.get_atomic_flow(e)) for f in sys.feeds) for e in unresolved}
    mass_in = sum(float(f.F_mass) for f in sys.feeds)
    mass_accepted = sum(v * _ATOMIC_MASS.get(e, 0.0) for e, v in unresolved.items()) / mass_in
    for e, v in unresolved.items():
        rows.append(dict(check=f"U2 accepted residual: unidentified-product {e} [fraction of the system {e} in]",
                         value=v / sys_in[e], status="INFO (accepted: identified products hold less than the feed)"))
    dm = c["mass_relative_error"] - mass_accepted
    rows.append(dict(check="Overall mass relative error, excluding the accepted U2 residual", value=dm,
                     status="PASS" if abs(dm) < 1e-6 else "FAIL"))   # 1e-6: atomic-mass rounding of the accepted residual
    for e, v in c["element_relative_error"].items():
        dv = v - (unresolved[e] / sys_in[e] if e in unresolved else 0.0)
        rows.append(dict(check=f"Element {e} relative error, excluding the accepted U2 residual", value=dv,
                         status="PASS" if abs(dv) < 1e-8 else "FAIL"))
    for r in inv.get_att_unit_balances(sys):
        errors = [r["mass_relative_error"]] + [r[f"{e}_relative_error"] for e in ("C", "H", "O", "N", "Na", "Ca")]
        if r["unit"] == "U2":
            unit_in = {e: sum(float(s.get_atomic_flow(e)) for s in inv._process_ins(U2)) for e in unresolved}
            u2_mass_in = sum(float(s.F_mass) for s in inv._process_ins(U2))
            errors[0] -= sum(v * _ATOMIC_MASS.get(e, 0.0) for e, v in unresolved.items()) / u2_mass_in
            for k, e in enumerate(("C", "H", "O", "N", "Na", "Ca"), start=1):
                if e in unresolved:
                    errors[k] -= unresolved[e] / unit_in[e]
        worst = max(abs(x) for x in errors)
        rows.append(dict(check=f"Unit {r['unit']} mass/element closure" + (" (excluding the accepted residual)" if r["unit"] == "U2" else ""),
                         value=worst, status="PASS" if worst < (1e-6 if r["unit"] == "U2" else 1e-8) else "FAIL"))
    water = {r["item"]: r["kg_per_kg_dry"] for r in inv.get_att_water_balance(sys)}
    rows.append(dict(check="Water balance residual [kg/h]", value=water["inputs + formation - outputs"],
                     status="PASS" if abs(water["inputs + formation - outputs"]) < 1e-8 else "FAIL"))
    for r in inv.get_att_unit_energy_balance(sys):
        v = r["unexplained_MJ_per_kg_dry"]
        if v == v:
            rows.append(dict(check=f"Unit {r['unit']} unexplained enthalpy residual [MJ/h]", value=v,
                             status="PASS" if abs(v) < 1e-6 else "FAIL"))
    for r in inv.get_att_utility_consistency_check(sys):
        rows.append(dict(check=r["check"], value=str(r["value"]), status=r["status"]))
    for r in inv.get_att_stream_sanity_check(sys):
        if r["status"] != "OK":
            rows.append(dict(check=f"Stream {r['stream']}", value=r["status"], status="FAIL"))
    rows.append(dict(check="Negative/non-finite flows or implausible T/P", value="none found"
                     if all(r["status"] == "OK" for r in inv.get_att_stream_sanity_check(sys)) else "see above",
                     status="PASS"))
    for r in inv.get_att_process_checks(sys):
        rows.append(dict(check=r["check"], value=r["value"], status=r["status"]))
    for w in warnings_list:
        rows.append(dict(check="BioSTEAM warning during the 1 kg/h simulation", value=w, status="INFO"))
    return rows


def _sources():
    rows = [dict(item=k, reference=v, role="configuration") for k, v in rep.FILES.items()]
    rows += [
        dict(item="Flowsheet", reference="biorefineries/ATT/system.py (create_att_system)", role="model"),
        dict(item="ATT units (U2, C1, EC1)", reference="biorefineries/ATT/units/_att.py", role="model"),
        dict(item="Chemicals (Char, CharN, CharS, feed pseudo-components)", reference="biorefineries/ATT/_chemicals.py",
             role="model"),
        dict(item="Extraction functions", reference="biorefineries/ATT/analyses/inventory.py, att/reporting.py",
             role="analysis"),
        dict(item="UCLA experimental data", reference="ATT Inputs and Assumptions_261023.xlsx, sheet '1. Gas Yield (Ni-ATT)'",
             role="experiment"),
    ]
    return rows


def _limitations():
    return [dict(limitation=x) for x in (
        "Material and heat flows per kg dry are scale-independent; electricity of D0 and F2 and all equipment sizes/costs "
        "at 1 kg/h reflect BioSTEAM minimum sizes and are not representative of a plant.",
        "The experimental steam (3.6 g per 0.5 g daf, flow-through) is not a model feed; U2 water is feed moisture plus "
        "recycle-liquor water.",
        "U2 takes the specified gas yields of the experimental team; carbon not otherwise assigned leaves as CO2 and "
        "oxygen closes with water. Unidentified products are not tracked.",
        "Feed composition is the NLR preprint composition, not an analysis of the UCLA sample.",
        "Cost-estimate equipment (C1 tank, EC1 vacuum) power is included in the utility table only as an estimate.",
    )]


# ---------------------------------------------------------------------------
# Build and export
# ---------------------------------------------------------------------------

def build_att_1kgph_audit():
    small, warns = simulate_att_1kgph(1.0)
    fingerprint = [float(x) for st in (*small.feeds, *small.products) for x in st.mass]
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        estimates = inv.get_att_cost_estimates(small)
    warns += sorted({_clean(f"{w.category.__name__} (cost estimates): {w.message}") for w in caught
                     if "replaced in registry" not in str(w.message)})
    streams, components = _stream_inventory(small)
    params = [dict(Parameter=r["parameter"], Value=r["value"], Unit=r["unit"], Process_unit=r["process_unit"],
                   Description=r["description"], Source_category=r["source_category"],
                   Source=f"{r['exact_source']} | {r['file_key']}", Status=r["assumption_status"], Notes=r["notes"])
              for r in rep._register_rows()
              if r["section"] in ("Feedstock", "Preparation", "ATT reaction", "Gas treatment", "Downstream", "Energy")]
    units = rep._units_table(small, [])
    for r in units:
        r["note_1kgph"] = "1 kg/h sizes/costs are BioSTEAM minimum-size artifacts; not for TEA"
    tables = {
        "01_Basis_Experiment": _basis(small),
        "02_Process_Parameters": params,
        "03_Units": units,
        "03b_Connectivity": rep._connectivity(small),
        "04_Stream_Inventory": streams,
        "05_Stream_Components": components,
        "06_Mass_Balance_Summary": _mass_summary(small),
        "06b_Total_Element_Balances": [dict(r, unit=r["unit"].replace("kg/kg dry", "kg/h").replace(
            "kg C/kg dry", "kg C/h")) for r in rep._mass_balance(small)],
        "07_NaOH_Carbonate": ([dict(item=r["item"], value=r["value"], unit=r["unit"].replace("kg/kg dry", "kg/h"))
                               for r in inv.get_att_sodium_calcium_ledger(small)]
                              + [dict(item=f"{r['stream']}: NaOH/(NaOH+H2O) | NaOH/total | Na2CO3/total",
                                      value=f"{r['NaOH_over_NaOH_plus_H2O']:.4g} | {r['NaOH_over_total_mixture']:.4g} | "
                                            f"{r['Na2CO3_over_total_mixture']:.4g}", unit=r["note"])
                                 for r in rep._naoh_extra(small)]),
        "08_Water_Balance": [dict(group=r["group"], item=r["item"], kg_per_h=r["kg_per_kg_dry"])
                             for r in inv.get_att_water_balance(small)],
        "09_Unit_Energy_Balance": _energy(small),
        "09b_Energy_Accounts": _energy_detail(small),
        "10_Utilities_Fuel": _utilities(small, estimates),
        "11_Products_Residues": [dict(r, kg_per_h=r.pop("kg_per_kg_dry")) for r in rep._products(small)],
        "13_Sources": _sources(),
    }
    # Full-scale run (ATT S1 capacity) for the comparison only (separate system object).
    from biorefineries.ATT.analyses import scenarios as scen
    ref = scen.create(scen.ATT_S1)
    tables["12_Compare_Full_Scale"] = _comparison(small, ref)
    aux = lambda est, sys: sum(r["power_kW"] for r in est if r["power_kW"] == r["power_kW"]) / inv._dry_feed_kgph(sys)
    a, b = aux(estimates, small), aux(inv.get_att_cost_estimates(ref), ref)
    b = b if b else float("nan")   # agitator and vacuum power are inside the unit models now (no TEA estimate)
    tables["12_Compare_Full_Scale"].insert(-1, dict(
        parameter="Electricity, agitators + EC1 vacuum (TEA estimates) [kWh/kg dry]", actual_1kgph_simulation=a,
        full_scale_normalized_per_kg_dry=b, relative_difference=(a - b) / b,
        explanation="Vacuum-system and tank correlations have minimum sizes (estimate, not a model unit)"))
    checks = _checks(small, warns)
    unchanged = _same_flows(small, fingerprint)
    checks.append(dict(check="1 kg/h flows unchanged after full-scale run", value=str(unchanged),
                       status="PASS" if unchanged else "FAIL"))
    tables["14_Limitations_Checks"] = _limitations() + checks
    order = ["01_Basis_Experiment", "02_Process_Parameters", "03_Units", "03b_Connectivity", "04_Stream_Inventory",
             "05_Stream_Components", "06_Mass_Balance_Summary", "06b_Total_Element_Balances", "07_NaOH_Carbonate",
             "08_Water_Balance", "09_Unit_Energy_Balance", "09b_Energy_Accounts", "10_Utilities_Fuel",
             "11_Products_Residues", "12_Compare_Full_Scale", "13_Sources", "14_Limitations_Checks"]
    return {k: tables[k] for k in order}


def _same_flows(sys, fingerprint, rtol=1e-12):
    now = [float(x) for st in (*sys.feeds, *sys.products) for x in st.mass]
    return all(abs(a - b) <= rtol * max(abs(b), 1e-12) for a, b in zip(now, fingerprint))


_README = """# ATT 1 kg/h process mass and energy audit

Generated by `python -m biorefineries.ATT.analyses.run baseline_1kg`
(`biorefineries/ATT/analyses/validation.py`).

## How the data were obtained

- **Actual simulation (A):** every sheet except `12_Compare_Full_Scale` comes from
  an actual BioSTEAM simulation of the frozen ATT model at exactly 1 kg dry
  Sargassum/h (`create_att_system(dry_sargassum_kgph=1.0)`, active U2 closure,
  recycle tolerance 1e-11). Values are in kg/h, mol/h, kJ/h and kW at that rate.
- **Full-scale normalized (B):** only `12_Compare_Full_Scale` also uses the SaBRe
  reference-scale run (82,937.5 kg dry/h) normalized per kg dry, side by side
  with (A).
- Material and heat flows agree between A and B (scale-independent). D0 and F2
  electricity, equipment sizes and costs differ (BioSTEAM minimum sizes and
  parallel units); the 1 kg/h equipment data are not for TEA.
- The UCLA experiment (0.5 g daf, 1 g NaOH, 3.6 g steam) is converted to the
  model basis in `01_Basis_Experiment`. Reported CH4/CO/CO2 are kept as
  experimental values only.

## Reproduce

```
python -m biorefineries.ATT.analyses.run baseline_1kg   # -> results/baseline_1kg
```

Nothing outside this folder is written; the frozen model, the inventory, LCA and
TEA outputs are not modified.

## Sheets

{sheets}
"""


def export_att_1kgph_audit(out_dir=None):
    import pandas as pd
    from biorefineries.ATT.analyses.paths import output_dir

    out_dir = os.fspath(out_dir or output_dir("baseline_1kg"))
    tables = build_att_1kgph_audit()
    os.makedirs(out_dir, exist_ok=True)
    with pd.ExcelWriter(os.path.join(out_dir, WORKBOOK), engine="openpyxl") as writer:
        for name, rows in tables.items():
            df = pd.DataFrame(rows)
            df.to_csv(os.path.join(out_dir, f"{name}.csv"), index=False)
            df.to_excel(writer, sheet_name=name[:31], index=False)
    sheets = "\n".join(f"- `{name}` ({len(rows)} rows)" for name, rows in tables.items())
    with open(os.path.join(out_dir, "README.md"), "w", encoding="utf-8") as f:
        f.write(_README.replace("{sheets}", sheets))
    return tables
