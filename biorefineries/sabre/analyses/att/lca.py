# Bioindustrial-Park: BioSTEAM's Premier Biorefinery Models and Results
# Copyright (C) 2026-, Yu Zhou,
#                      Yalin Li <mailto.yalin.li@gmail.com>
#
# This module is under the UIUC open-source license. See
# github.com/BioSTEAMDevelopmentGroup/biosteam/blob/master/LICENSE.txt
# for license details.

"""
GWP100 of the frozen ATT process model using BioSTEAM's impact framework.

Activity data come only from the frozen ATT model (active U2 closure, att.yaml)
simulated at the SaBRe reference scale (electricity is scale dependent):

- purchased materials: stream characterization factors (Stream.set_CF);
- natural gas (U2) and LP steam: utility-agent factors equivalent to
  fuel = delivered heat-utility duty / efficiency, applied once (the duty
  already includes the 5 % process heat loss); steam is not also counted
  as fuel;
- cooling water: agent factor on circulating water, equal to the BioSTEAM
  CoolingTower electricity (not in the unit power utilities);
- unit electricity: PowerUtility factor;
- off-flowsheet items (wastewater treatment, purge neutralization reagent,
  landfill, auxiliary electricity, optional collection/transport):
  System.define_process_impact.

The total is System.get_net_impact; the contribution tables decompose it and
are checked to sum to it. Factors and assumptions: data/att_lca.yaml.
"""
import biosteam as bst

from biorefineries.sabre.analyses.att import inventory as inv
from biorefineries.sabre.utils import load_assumptions

__all__ = (
    "create_att_lca_system",
    "apply_att_gwp",
    "get_att_gwp_contributions",
    "get_att_gwp_by_stage",
    "get_att_gwp_by_unit",
    "get_att_gwp_summary",
    "get_att_avoided_emission",
    "get_att_gwp_sensitivity",
    "get_att_lca_factor_register",
    "get_att_lca_data_gaps",
    "check_att_lca",
    "export_att_lca",
)

_LCA = load_assumptions("att_lca.yaml")["lca"]
KEY = _LCA["impact_key"]
_EF = _LCA["emission_factors"]
_MW = {"NaOH": 39.99711, "Na2CO3": 105.9888, "H2SO4": 98.07848, "H2O": 18.01528}
_FEED_FACTORS = {"fresh_naoh_solid": ("NaOH", "NaOH"), "dissolution_water": ("Water", "water_supply"),
                 "slaking_water": ("Water", "water_supply")}
_STAGES = {
    "NaOH makeup": "Chemical supply",
    "Ca(OH)2": "Chemical supply",
    "Purge neutralization (H2SO4)": "Chemical supply",
    "Process water (D1)": "Water supply",
    "Natural gas U2: combustion": "Onsite fuel combustion",
    "Natural gas boiler (LP steam): combustion": "Onsite fuel combustion",
    "Natural gas U2: upstream supply": "Natural gas supply chain",
    "Natural gas boiler (LP steam): upstream supply": "Natural gas supply chain",
    "Electricity: process units": "Purchased electricity",
    "Electricity: cooling tower and CW pumps": "Purchased electricity",
    "Electricity: outside unit models (agitators, EC1 vacuum)": "Purchased electricity",
    "Wastewater treatment": "Waste management",
    "Landfill: solid residues": "Waste management",
    "Biogenic carbon stored in landfilled solids (credit)": "Stored biogenic carbon",
    "Sargassum collection and transport": "Feedstock collection and transport",
}


def _factors(overrides=None):
    f = {k: float(v["value"]) for k, v in _EF.items()}
    f.update(overrides or {})
    return f


def create_att_lca_system(configuration="presscake"):
    """ATT model at the SaBRe reference scale ("presscake" or "fresh_sargassum") with operating hours."""
    from biorefineries.sabre.systems._att_system import create_att_system

    scale = inv.get_att_reference_scale(configuration)
    sys = inv._simulate(create_att_system(dry_sargassum_kgph=scale["dry_feed_kgph"], configuration=configuration),
                        scale["dry_feed_kgph"])
    sys.operating_hours = scale["operating_hours_per_year"]
    return sys


# ---------------------------------------------------------------------------
# Off-flowsheet activities (all from frozen streams)
# ---------------------------------------------------------------------------

def _wastewater_m3ph(sys):
    s = inv._streams(sys)
    rho = float(_LCA["water_density_kg_per_m3"])
    products = {p.ID for p in sys.products}
    return sum(float(s[ID].F_mass) for ID in _LCA["waste_management"]["wastewater_streams"] if ID in products) / rho


def _h2so4_kgph(sys):
    s = inv._streams(sys)
    n = _LCA["neutralization"]
    H = sum(n["H_plus_per_mol"][k] * float(s[ID].imol[k])
            for ID in n["streams"] for k in n["H_plus_per_mol"])  # kmol H+/h
    return H / 2.0 * _MW["H2SO4"]


def _landfill_kgph(sys):
    s = inv._streams(sys)
    products = {p.ID for p in sys.products}
    return sum(float(s[ID].F_mass) for ID in _LCA["waste_management"]["landfill_streams"] if ID in products)


def _stored_carbon_kgph(sys):
    """Carbon (kg C/h) leaving in landfilled solids; carbonate and char are taken as permanently stored."""
    s = inv._streams(sys)
    products = {p.ID for p in sys.products}
    return sum(float(s[ID].get_atomic_flow("C")) * 12.011
               for ID in _LCA["waste_management"]["landfill_streams"] if ID in products)


def _cooling_water_kWh_per_kg():
    att = load_assumptions("att.yaml")["att"]
    return sum(att["inventory"]["lca"]["cooling_water_kW_per_kmolph"]) / _MW["H2O"]


def _auxiliary_power_kW(estimates):
    return sum(r["power_kW"] for r in estimates if r["power_kW"] == r["power_kW"])


# ---------------------------------------------------------------------------
# Factors -> BioSTEAM
# ---------------------------------------------------------------------------

def apply_att_gwp(sys, lime_source=None, overrides=None, estimates=None):
    """Set all GWP100 characterization factors on the frozen system."""
    f = _factors(overrides)
    lime_key = lime_source or _LCA["scenarios"]["baseline"]["lime_source"]
    if KEY not in bst.settings.impact_indicators:
        bst.settings.define_impact_indicator(KEY, _LCA["impact_units"])
    s = inv._streams(sys)
    for stream in (*sys.feeds, *sys.products):
        stream.characterization_factors.pop(KEY, None)
    # Purchased materials (pure streams; checked).
    for ID, (component, name) in _FEED_FACTORS.items():
        if ID not in s:      # slaking water exists only with the lime recycle
            continue
        stream = s[ID]
        if abs(float(stream.imass[component]) - float(stream.F_mass)) > 1e-9 * max(1.0, stream.F_mass):
            raise ValueError(f"{ID} is not pure {component}; per-kg stream factor invalid")
        value = f[name] / float(_LCA["water_density_kg_per_m3"]) if name == "water_supply" else f[name]
        stream.set_CF(KEY, value)
    if abs(float(s["lime"].imass["CaOH2"]) - float(s["lime"].F_mass)) > 1e-9 * max(1.0, s["lime"].F_mass):
        raise ValueError("lime is not pure Ca(OH)2")
    s["lime"].set_CF(KEY, f[lime_key])

    # Heat utilities: CF per kJ of delivered utility heat.
    ng = f["natural_gas_combustion"] + f["natural_gas_upstream"]
    eta = _LCA["natural_gas"]
    # BioSTEAM flags the 298 K natural-gas agent as a cooling agent and
    # rejects a positive kJ-basis factor, so the same duty-based factor is
    # expressed per kg of agent: kJ delivered per kg from this system's U2
    # heat utility. The fuel energy stays duty / burner efficiency.
    gas = [hu for hu in sys.heat_utilities if hu.agent.ID == "natural_gas"]
    if gas:
        hu = gas[0]
        kJ_per_kg = hu.duty / (hu.flow * hu.agent.MW)
        bst.settings.set_utility_agent_CF("natural_gas", KEY,
                                          ng / eta["burner_efficiency"] / 1e3 * kJ_per_kg, basis="kg")
    bst.settings.set_utility_agent_CF("low_pressure_steam", KEY, ng / eta["boiler_efficiency"] / 1e3, basis="kJ")
    bst.settings.set_utility_agent_CF("cooling_water", KEY, _cooling_water_kWh_per_kg() * f["electricity"],
                                      basis="kg")
    used = {hu.agent.ID for hu in sys.heat_utilities}
    if not used <= {"natural_gas", "low_pressure_steam", "cooling_water"}:
        raise ValueError(f"Utility agents without GWP factors: {used}")
    bst.settings.set_electricity_CF(KEY, consumption=f["electricity"], basis="kWhr")

    # Off-flowsheet items.
    items = getattr(sys, "process_impact_items", {})
    items.pop(KEY, None)
    sys.process_impact_items = items
    hours = sys.operating_hours
    if estimates is None:
        estimates = inv.get_att_cost_estimates(sys)
    aux_kW = _auxiliary_power_kW(estimates)
    sys.define_process_impact(KEY, "Wastewater treatment", "m3",
                              lambda: _wastewater_m3ph(sys) * hours, f["wastewater_treatment"])
    sys.define_process_impact(KEY, "Purge neutralization (H2SO4)", "kg",
                              lambda: _h2so4_kgph(sys) * hours, f["H2SO4"])
    sys.define_process_impact(KEY, "Landfill: solid residues", "kg",
                              lambda: _landfill_kgph(sys) * hours, f["inert_landfill"])
    stored = 1.0 if _LCA["carbon_storage"]["credit_stored_carbon"] else 0.0
    sys.define_process_impact(KEY, "Biogenic carbon stored in landfilled solids (credit)", "kg CO2",
                              lambda: -stored * _stored_carbon_kgph(sys) * 44.0095 / 12.011 * hours, 1.0)
    sys.define_process_impact(KEY, "Electricity: outside unit models (agitators, EC1 vacuum)", "kWh",
                              lambda: aux_kW * hours, f["electricity"])
    # Natural gas displaced by the PSA tail gas burned in the U2 burner (fuel basis, MJ).
    sys.define_process_impact(KEY, "Natural gas displaced by PSA tail gas (burned in U2)", "MJ fuel",
                              lambda: -inv.get_att_tail_gas_offset(sys)["offset_MJph"] * hours, ng)
    fuel = _LCA["collection_transport"]["marine_fuel_kg_per_t_wet"]
    if fuel is not None:
        wet_tph = float(s["att_sargassum_feed"].F_mass) / 1e3
        sys.define_process_impact(KEY, "Sargassum collection and transport", "kg marine fuel",
                                  lambda: wet_tph * float(fuel) * hours, f["marine_fuel"])

    # CaCO3 coproduct (BioSTEAM subtracts product impacts as displacement).
    treatment = _LCA["coproduct"]["CaCO3_treatment"]
    if treatment == "substitution":
        CF = _LCA["coproduct"]["CaCO3_substitution_CF"]
        if CF is None:
            raise ValueError("CaCO3 substitution requires coproduct.CaCO3_substitution_CF")
        cake = s["caco3_cake"]
        cake.set_CF(KEY, float(CF) * float(cake.imass["CaCO3"]) / float(cake.F_mass))
    elif treatment != "none":
        raise ValueError(f"Unknown CaCO3 treatment '{treatment}'")
    return dict(factors=f, lime_source=lime_key, auxiliary_power_kW=aux_kW)


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

def _basis(sys):
    hours = sys.operating_hours
    dry = inv._dry_feed_kgph(sys)
    h2 = float(inv._streams(sys)["h2_product"].imass["H2"])
    return hours, dry * hours, h2 * hours


def get_att_gwp_contributions(sys, applied):
    """Decomposition of System.get_net_impact by material and energy input."""
    f = applied["factors"]
    hours, dry_yr, h2_yr = _basis(sys)
    s = inv._streams(sys)
    rows = []

    def add(item, amount_yr, unit, EF, EF_unit, gwp_yr, source):
        rows.append(dict(item=item, stage=_STAGES[item], activity_per_kg_dry=amount_yr / dry_yr,
                         activity_unit=unit, EF=EF, EF_unit=EF_unit,
                         GWP_kgCO2e_per_kg_dry=gwp_yr / dry_yr, GWP_kgCO2e_per_kg_H2=gwp_yr / h2_yr,
                         source=source))

    naoh, lime = s["fresh_naoh_solid"], s["lime"]
    waters = [s[ID] for ID in ("dissolution_water", "slaking_water") if ID in s]
    add("NaOH makeup", naoh.F_mass * hours, "kg", f["NaOH"], "kg CO2e/kg", naoh.get_impact(KEY) * hours,
        _EF["NaOH"]["source"])
    add("Ca(OH)2", lime.F_mass * hours, "kg", f[applied["lime_source"]], "kg CO2e/kg",
        lime.get_impact(KEY) * hours, f"{applied['lime_source']}: {_EF[applied['lime_source']]['source']}")
    rho = float(_LCA["water_density_kg_per_m3"])
    add("Process water (D1)", sum(w.F_mass for w in waters) / rho * hours, "m3", f["water_supply"], "kg CO2e/m3",
        sum(w.get_impact(KEY) for w in waters) * hours, _EF["water_supply"]["source"])

    eta = _LCA["natural_gas"]
    ng = f["natural_gas_combustion"] + f["natural_gas_upstream"]
    for agent, label, efficiency in (("natural_gas", "Natural gas U2", eta["burner_efficiency"]),
                                     ("low_pressure_steam", "Natural gas boiler (LP steam)",
                                      eta["boiler_efficiency"])):
        gwp = sys.get_net_heat_utility_impact(agent, KEY)
        fuel_MJ_yr = sum(hu.duty for hu in sys.heat_utilities if hu.agent.ID == agent) / 1e3 / efficiency * hours
        # The PSA tail gas burned in the U2/kiln burners replaces natural gas: the fuel bought is the total need
        # minus the tail gas LHV (capped at the need), shown in the same lines instead of a separate line.
        burned = inv.get_att_tail_gas_offset(sys)["offset_MJph"] * hours if agent == "natural_gas" else 0.0
        for part, name in (("natural_gas_combustion", "combustion"), ("natural_gas_upstream", "upstream supply")):
            add(f"{label}: {name}", fuel_MJ_yr - burned, "MJ fuel (LHV, net of the PSA tail gas)" if burned else "MJ fuel (LHV)",
                f[part], "kg CO2e/MJ", gwp * f[part] / ng - burned * f[part], _EF[part]["source"])
    cw_kg_yr = sum(hu.flow * hu.agent.MW for hu in sys.heat_utilities if hu.agent.ID == "cooling_water") * hours
    add("Electricity: cooling tower and CW pumps", cw_kg_yr * _cooling_water_kWh_per_kg(), "kWh",
        f["electricity"], "kg CO2e/kWh", sys.get_net_heat_utility_impact("cooling_water", KEY),
        "BioSTEAM CoolingTower correlation x electricity factor")
    add("Electricity: process units", sys.power_utility.rate * hours, "kWh", f["electricity"], "kg CO2e/kWh",
        sys.get_net_electricity_impact(KEY), _EF["electricity"]["source"])
    for item in sys.process_impact_items[KEY]:
        if item.name.startswith("Natural gas displaced"):      # folded into the natural gas lines above
            continue
        add(item.name, item.inventory(), item.basis, item.CF, f"kg CO2e/{item.basis}", item.impact(), "")
    total_yr = sys.get_net_impact(KEY)
    rows.append(dict(item="TOTAL (System.get_net_impact)", stage="", activity_per_kg_dry=float("nan"),
                     activity_unit="", EF=float("nan"), EF_unit="", GWP_kgCO2e_per_kg_dry=total_yr / dry_yr,
                     GWP_kgCO2e_per_kg_H2=total_yr / h2_yr, source=""))
    for r in rows:
        r["share"] = r["GWP_kgCO2e_per_kg_dry"] / (total_yr / dry_yr)
    return rows


AVOIDED_CH4_ITEM = "Avoided CH4 if rotted on the beach (extra credit, not in net)"


def get_att_stored_carbon_credit(sys):
    """Stored-carbon credit in the net GWP [kg CO2e per kg H2; negative], 0 if switched off."""
    on = _LCA["carbon_storage"]["credit_stored_carbon"]
    h2 = float(inv._streams(sys)["h2_product"].imass["H2"])
    return -(_stored_carbon_kgph(sys) * 44.0095 / 12.011 / h2) if on else 0.0


def get_att_avoided_emission(sys):
    """
    Avoided emission if the Sargassum would otherwise rot on the beach [kg CO2e per kg H2, negative = avoided]:
    ``stored`` (the carbon the plant stores, already credited in the net GWP as CO2), ``CH4_extra`` (the extra
    warming of the CH4 that rotting would form, net of the CO2 its carbon is already counted as in ``stored``; NOT in
    the net) and ``total`` = stored + CH4_extra. CH4 formed: IPCC 2006 long-term potential (att_lca.yaml
    beach_rot_counterfactual).
    """
    c = _LCA["beach_rot_counterfactual"]
    dry = inv._dry_feed_kgph(sys)
    h2 = float(inv._streams(sys)["h2_product"].imass["H2"])
    carbon = sum(r["kg_C_per_kg_dry"] for r in inv.get_att_carbon_fate(sys) if r["direction"] == "input")
    ch4 = (carbon * c["dissimilated_fraction_DOCf"] * c["methane_correction_factor_MCF"] * c["methane_fraction_F"]
           * (1.0 - c["gas_capture_fraction_R"]) * (1.0 - c["oxidation_OX"]) * 16.04246 / 12.011)
    ch4_extra = -ch4 * (c["CH4_GWP100"] - 44.0095 / 16.04246) * dry / h2
    stored = get_att_stored_carbon_credit(sys)
    return dict(feed_carbon_kg_per_kg_dry=carbon, CH4_kg_per_kg_dry=ch4, stored_kgCO2e_per_kg_H2=stored,
                CH4_extra_kgCO2e_per_kg_H2=ch4_extra, total_kgCO2e_per_kg_H2=stored + ch4_extra)


def get_att_gwp_by_stage(contributions):
    stages = {}
    total = contributions[-1]
    for r in contributions[:-1]:
        stages.setdefault(r["stage"], [0.0, 0.0])
        stages[r["stage"]][0] += r["GWP_kgCO2e_per_kg_dry"]
        stages[r["stage"]][1] += r["GWP_kgCO2e_per_kg_H2"]
    rows = [dict(stage=k, GWP_kgCO2e_per_kg_dry=v[0], GWP_kgCO2e_per_kg_H2=v[1],
                 share=v[0] / total["GWP_kgCO2e_per_kg_dry"]) for k, v in stages.items()]
    if "Feedstock collection and transport" not in stages:
        rows.append(dict(stage="Feedstock collection and transport", GWP_kgCO2e_per_kg_dry=float("nan"),
                         GWP_kgCO2e_per_kg_H2=float("nan"), share=float("nan")))
    rows.append(dict(stage="Direct process emissions (fossil)", GWP_kgCO2e_per_kg_dry=0.0,
                     GWP_kgCO2e_per_kg_H2=0.0, share=0.0))
    return rows


def get_att_gwp_by_unit(sys, applied):
    """Attribution to process units (utilities by unit; materials to the consuming unit)."""
    f = applied["factors"]
    hours, dry_yr, h2_yr = _basis(sys)
    s = inv._streams(sys)
    cf = {agent: bst.HeatUtility.get_CF(agent, KEY) for agent in
          ("natural_gas", "low_pressure_steam", "cooling_water")}
    totals = {}
    for unit in sys.units:
        g = unit.power_utility.rate * f["electricity"]
        for hu in unit.heat_utilities:
            if hu.agent is None or hu.duty == 0.0:
                continue
            value, basis = cf[hu.agent.ID]
            g += hu.duty * value if basis == "kJ" else hu.flow * hu.agent.MW * value
        totals[unit.ID] = g * hours
    totals["M1"] += s["fresh_naoh_solid"].get_impact(KEY) * hours
    totals["C1"] += s["lime"].get_impact(KEY) * hours
    totals["D1"] += s["dissolution_water"].get_impact(KEY) * hours
    items = {item.name: item.impact() for item in sys.process_impact_items[KEY]}
    totals["C1 + EC1 (auxiliary electricity)"] = items.pop(
        "Electricity: outside unit models (agitators, EC1 vacuum)")
    totals["Waste management (off-flowsheet)"] = sum(items.values())
    total_yr = sys.get_net_impact(KEY)
    return [dict(unit=k, GWP_kgCO2e_per_kg_dry=v / dry_yr, GWP_kgCO2e_per_kg_H2=v / h2_yr,
                 share=v / total_yr) for k, v in totals.items() if v != 0.0]


def get_att_gwp_summary(sys, applied):
    """Headline results, boundary status, fossil/biogenic carbon and off-gas."""
    f = applied["factors"]
    hours, dry_yr, h2_yr = _basis(sys)
    s = inv._streams(sys)
    total_yr = sys.get_net_impact(KEY)
    dry = inv._dry_feed_kgph(sys)
    ng_fuel = (sum(hu.duty for hu in sys.heat_utilities if hu.agent.ID == "natural_gas")
               / _LCA["natural_gas"]["burner_efficiency"]
               + sum(hu.duty for hu in sys.heat_utilities if hu.agent.ID == "low_pressure_steam")
               / _LCA["natural_gas"]["boiler_efficiency"]) / 1e3
    tail = inv._tail_gas(sys)
    U2 = inv._units(sys)["U2"]
    daf = float(U2._daf_sargassum_kgph)
    credit = get_att_avoided_emission(sys)
    carbon = {r["stream"]: r["kg_C_per_kg_dry"] for r in inv.get_att_carbon_fate(sys)}
    ch4_reported = float(U2.reported_gas_yield_mmol_per_g_daf["CH4"]) * daf * 16.04246 / 1e3 / dry
    rows = [
        ("GWP100 per kg H2", total_yr / h2_yr, "kg CO2e/kg H2", "functional unit; experimental H2 basis"),
        ("GWP100 per kg dry Sargassum", total_yr / dry_yr, "kg CO2e/kg dry", ""),
        ("Annual GWP100 at reference scale", total_yr / 1e3, "t CO2e/yr",
         f"{dry * 24 / 1e3:.0f} dry t/d, {hours:.0f} h/yr"),
        ("H2 product", float(s["h2_product"].imass["H2"]) / dry, "kg/kg dry",
         f"model H2 {U2._model_gas_yield_mmol_per_g_daf['H2']:.3f} mmol/g daf x PSA recovery if any ({U2.gas_closure_method})"),
        ("CH4 in PSA off-gas (model)", float(tail.imass["CH4"]) / dry, "kg/kg dry",
         "explicit collected stream; final fate UNRESOLVED; direct CH4 emission not in baseline GWP; no credit"),
        ("Avoided CH4 if rotted on the beach: extra credit (not in net)", credit["CH4_extra_kgCO2e_per_kg_H2"], "kg CO2e/kg H2",
         f"{credit['CH4_kg_per_kg_dry']:.4f} kg CH4/kg dry avoided (IPCC 2006 defaults, att_lca.yaml beach_rot_counterfactual), "
         "net of the CO2 its carbon is counted as in the stored-carbon credit; counterfactual-dependent"),
        ("Avoided emission if rotted on the beach: stored carbon + extra CH4", credit["total_kgCO2e_per_kg_H2"], "kg CO2e/kg H2",
         "the stored-carbon credit already in the net plus the extra CH4 credit"),
        ("GWP100 per kg H2 with the extra CH4 credit", total_yr / h2_yr + credit["CH4_extra_kgCO2e_per_kg_H2"], "kg CO2e/kg H2",
         "net (incl. the stored-carbon credit) plus the extra CH4 credit"),
        ("Lime source", float("nan"), "", applied["lime_source"]),
        ("Boundary status", float("nan"), "",
         "PARTIAL: Sargassum collection/transport pending" if _LCA["collection_transport"][
             "marine_fuel_kg_per_t_wet"] is None else "collection/transport included"),
        ("Allocation", float("nan"), "", _LCA["allocation"]),
        ("Fossil CO2, onsite natural gas combustion", ng_fuel * f["natural_gas_combustion"] / dry, "kg CO2/kg dry", ""),
        ("Biogenic CO2 in PSA off-gas", float(tail.imass["CO2"]) / dry, "kg CO2/kg dry",
         "model value; recorded, GWP not applied (biogenic)"),
        ("H2 in PSA off-gas", float(tail.imass["H2"]) / dry, "kg/kg dry",
         "burned with the tail gas (natural gas offset); H2 indirect warming not quantified"),
        ("PSA off-gas total", float(tail.F_mass) / dry, "kg/kg dry", _LCA["offgas"]["treatment"]),
        ("Biogenic C retained in CaCO3 cake", carbon.get("caco3_cake", 0.0), "kg C/kg dry",
         "credited as stored carbon when the cake is landfilled (a product); not when it is recycled to the kiln"),
        ("Biogenic C in ash/char cake (landfilled)", carbon.get("ash_residue_cake", 0.0), "kg C/kg dry",
         "credited as stored carbon; degradation of the char not quantified"),
        ("Stored-carbon credit in the net GWP", get_att_stored_carbon_credit(sys), "kg CO2e/kg H2",
         "landfilled carbonate and char, permanence assumed"),
        ("CH4 in U2 gas (specified)", ch4_reported, "kg/kg dry", "experimental team yield, burned in the U2 burner"),
        ("CO in U2 gas (specified)",
         float(U2.reported_gas_yield_mmol_per_g_daf["CO"]) * daf * 28.0101 / 1e3 / dry, "kg/kg dry",
         "experimental team yield"),
    ]
    return [dict(item=a, value=b, unit=c, note=d) for a, b, c, d in rows]


def _total_per_kg(sys, **kw):
    applied = apply_att_gwp(sys, **kw)
    hours, dry_yr, h2_yr = _basis(sys)
    total = sys.get_net_impact(KEY)
    return total / dry_yr, total / h2_yr, applied


def get_att_gwp_sensitivity(sys, estimates):
    """Baseline, steel-slag lime, one-at-a-time factor ranges."""
    rows = []
    base_dry, base_h2, _ = _total_per_kg(sys, estimates=estimates)
    rows.append(dict(scenario="Baseline", parameter="", value=float("nan"),
                     GWP_kgCO2e_per_kg_dry=base_dry, GWP_kgCO2e_per_kg_H2=base_h2, delta_per_kg_H2=0.0))
    d, h, _ = _total_per_kg(sys, lime_source="CaOH2_steel_slag", estimates=estimates)
    rows.append(dict(scenario="S1 steel-slag Ca(OH)2", parameter="CaOH2_steel_slag",
                     value=_EF["CaOH2_steel_slag"]["value"], GWP_kgCO2e_per_kg_dry=d,
                     GWP_kgCO2e_per_kg_H2=h, delta_per_kg_H2=h - base_h2))
    for name in _LCA["sensitivity_factors"]:
        for bound, value in zip(("low", "high"), _EF[name]["range"]):
            d, h, _ = _total_per_kg(sys, overrides={name: float(value)}, estimates=estimates)
            rows.append(dict(scenario=f"S2 {name} {bound}", parameter=name, value=float(value),
                             GWP_kgCO2e_per_kg_dry=d, GWP_kgCO2e_per_kg_H2=h, delta_per_kg_H2=h - base_h2))
    apply_att_gwp(sys, estimates=estimates)  # restore baseline factors
    return rows


def get_att_lca_factor_register():
    rows = []
    for name, e in _EF.items():
        rows.append(dict(factor=name, value=e["value"], range=str(e.get("range", "")), unit=e["unit"],
                         source=e["source"], boundary=e.get("boundary", ""), note=e.get("note", "")))
    eta = _LCA["natural_gas"]
    rows += [
        dict(factor="burner_efficiency (U2)", value=eta["burner_efficiency"], range="", unit="-",
             source="ATT collaborators (att.yaml energy_sources)", boundary="", note=eta["note"]),
        dict(factor="boiler_efficiency (LP steam)", value=eta["boiler_efficiency"], range="[0.80, 0.90]", unit="-",
             source="BioSTEAM BoilerTurbogenerator default", boundary="", note=""),
        dict(factor="cooling-water electricity", value=_cooling_water_kWh_per_kg(), range="", unit="kWh/kg CW",
             source="BioSTEAM CoolingTower correlation (Humbird et al. 2011)", boundary="tower fans + CW pumps",
             note="avoids counting cooling as fuel"),
        dict(factor="water density", value=_LCA["water_density_kg_per_m3"], range="", unit="kg/m3",
             source="assumption", boundary="", note="m3 = kg / 1000"),
        dict(factor="neutralization endpoint", value=float("nan"), range="", unit="",
             source="assumption", boundary="", note=_LCA["neutralization"]["endpoint"]),
    ]
    for key in ("functional_unit", "boundary", "allocation", "energy_basis"):
        rows.append(dict(factor=key, value=float("nan"), range="", unit="", source="att_lca.yaml",
                         boundary="", note=_LCA[key]))
    return rows


def get_att_lca_data_gaps(sys, applied):
    """Missing or uncertain items with indicative magnitudes (not in results)."""
    f = applied["factors"]
    hours, dry_yr, h2_yr = _basis(sys)
    dry = inv._dry_feed_kgph(sys)
    h2 = h2_yr / dry_yr
    s = inv._streams(sys)
    summary = {r["item"]: r["value"] for r in get_att_gwp_summary(sys, applied)}
    wet_t_per_kg_dry = float(s["att_sargassum_feed"].F_mass) / 1e3 / dry
    per_fuel = wet_t_per_kg_dry * f["marine_fuel"]
    gwp_ch4 = _LCA["indicative_gwp100"]["CH4_non_fossil"]["value"]
    ch4_model = summary["CH4 in PSA off-gas (model)"] * gwp_ch4
    steam_fuel = sum(hu.duty for hu in sys.heat_utilities if hu.agent.ID == "low_pressure_steam") / 1e3 / dry
    ng = f["natural_gas_combustion"] + f["natural_gas_upstream"]
    boiler_delta = steam_fuel * ng * (1 / 0.90 - 1 / 0.80)
    cake = s["caco3_cake"]
    cake_landfill = float(cake.F_mass) / dry * f["inert_landfill"]
    rows = [
        ("Sargassum collection and transport", "PENDING (no SaBRe data)",
         per_fuel, f"per 1 kg marine fuel per t wet Sargassum ({per_fuel / h2:.2f} per kg H2)", "potentially HIGH"),
        ("Model off-gas CH4 if vented", "NOT IN BASELINE GWP (baseline burns the off-gas in the U2 burner)", ch4_model,
         "indicative: model off-gas CH4 x GWP100 27.0 (AR6 non-fossil); burning gives biogenic CO2 (0)",
         "HIGH if vented instead of burned"),
        ("PSA off-gas fate (CH4, unrecovered H2, CO, CO2)",
         "BURNED in the U2 burner (natural gas offset; no burner equipment or cost in the baseline TEA)", float("nan"),
         "CH4 venting quantified above; burning gives biogenic CO2; H2 indirect warming not quantified", "MEDIUM"),
        ("Plant-location electricity factor", "PLACEHOLDER (US average)", float("nan"),
         "see S2 electricity range", "MEDIUM"),
        ("Steam boiler efficiency 0.80 vs 0.90", "ASSUMPTION", boiler_delta, "change if 0.90", "MEDIUM"),
        ("NG upstream factor basis (NETL 2019 LHV/HHV)", "UNVERIFIED", float("nan"),
         "+/-11 % of the upstream part; range covered in S2", "LOW-MEDIUM"),
        ("CaCO3 cake fate if not marketable", "SCENARIO NOT RUN", cake_landfill,
         "landfill proxy for the whole wet cake; entrained NaOH neutralization not included", "LOW"),
        ("Char degradation in landfill", "NOT QUANTIFIED", float("nan"),
         f"{summary['Biogenic C in ash/char cake (landfilled)']:.3f} kg C/kg dry (incl. carbonate C)", "LOW-MEDIUM"),
        ("Wastewater process CH4/N2O and COD of condensates and purge", "NOT INCLUDED", float("nan"),
         "condensates modeled as pure water; energy-only WWT factor", "LOW-MEDIUM"),
        ("Cooling-tower and boiler make-up water", "NOT INCLUDED", float("nan"), "small", "LOW"),
        ("Water/WWT factors (Zib et al. 2021)", "AS PROVIDED, not rechecked", float("nan"), "tiny contribution", "LOW"),
        ("Capital goods, chemical transport", "EXCLUDED", float("nan"), "outside the workbook boundary", "LOW"),
        ("Biogenic C storage in landfilled solids", "CREDITED in the net", summary["Biogenic C retained in CaCO3 cake"] * 44.0095 / 12.011,
         "kg CO2 equivalent of the C retained in the cake; permanence of the landfilled carbonate is assumed", "assumption"),
    ]
    return [dict(item=a, status=b, indicative_kgCO2e_per_kg_dry=c, note=d, importance=e) for a, b, c, d, e in rows]


def check_att_lca(sys, applied, contributions, utilities):
    """Numerical checks: decomposition, unit conversions and double counting."""
    f = applied["factors"]
    hours, dry_yr, h2_yr = _basis(sys)
    u = {r["item"]: r["per_kg_dry"] for r in utilities}
    c = {r["item"]: r["GWP_kgCO2e_per_kg_dry"] for r in contributions}
    total = c.pop("TOTAL (System.get_net_impact)")
    ng = f["natural_gas_combustion"] + f["natural_gas_upstream"]
    cw_kWh = u["Electricity: cooling tower and CW pumps (estimate)"]
    s = inv._streams(sys)
    checks = [
        ("Sum of contributions = System.get_net_impact", sum(c.values()), total),
        ("Product impacts (credits) in baseline", sys.get_total_products_impact(KEY), 0.0),
        ("NG GWP = (U2 fuel + boiler fuel - tail gas offset) x (combustion + upstream)",
         sum(v for k, v in c.items() if k.startswith("Natural gas")),
         (u["U2 natural gas: fuel input (LHV)"] + u["LP steam: boiler natural gas (LHV)"]
          - u["U2 natural gas displaced by PSA tail gas (offset)"]) * ng),
        ("Cooling GWP = inventory CW electricity x EF", c["Electricity: cooling tower and CW pumps"],
         cw_kWh * f["electricity"]),
        ("Unit + CW + auxiliary electricity = inventory total",
         (c["Electricity: process units"] + c["Electricity: cooling tower and CW pumps"]
          + c["Electricity: outside unit models (agitators, EC1 vacuum)"]) / f["electricity"],
         u["Electricity: total"]),
        ("Water m3 = kg / 1000", s["dissolution_water"].get_impact(KEY) / f["water_supply"],
         float(s["dissolution_water"].F_mass) / 1000.0),
        ("H2 basis = model yield x daf x PSA recovery [kg/kg dry]", h2_yr / dry_yr,
         inv._units(sys)["U2"]._model_gas_yield_mmol_per_g_daf["H2"]
         * float(inv._units(sys)["U2"]._daf_sargassum_kgph) * 2.01588 / 1e3
         * (float(inv._ATT["gas_treatment"]["psa_h2_recovery"]) if "U3P" in inv._units(sys) else 1.0)
         / inv._dry_feed_kgph(sys)),
    ]
    return [dict(check=a, value=b, expected=d,
                 status="PASS" if abs(b - d) <= 1e-9 * max(1.0, abs(d)) else "FAIL") for a, b, d in checks]


def export_att_lca(out_dir=None):
    """Run the baseline, scenarios and checks; write CSV files and one workbook (default att_outputs/full_scale/lca)."""
    import os
    import pandas as pd
    from biorefineries.sabre.analyses.att.paths import output_dir

    out_dir = os.fspath(out_dir or output_dir("lca"))

    sys = create_att_lca_system()
    fingerprint = [float(x) for st in (*sys.feeds, *sys.products) for x in st.mass]
    estimates = inv.get_att_cost_estimates(sys)
    applied = apply_att_gwp(sys, estimates=estimates)
    contributions = get_att_gwp_contributions(sys, applied)
    utilities = inv.get_att_purchased_utilities(sys, estimates)
    tables = {
        "00_factor_register": get_att_lca_factor_register(),
        "01_summary": get_att_gwp_summary(sys, applied),
        "02_contributions_by_input": contributions,
        "03_contributions_by_stage": get_att_gwp_by_stage(contributions),
        "04_contributions_by_unit": get_att_gwp_by_unit(sys, applied),
        "05_activity_inventory_per_kg_dry": utilities,
    }
    checks = check_att_lca(sys, applied, contributions, utilities)
    tables["06_scenarios_and_sensitivity"] = get_att_gwp_sensitivity(sys, estimates)
    tables["07_data_gaps"] = get_att_lca_data_gaps(sys, applied)
    unchanged = fingerprint == [float(x) for st in (*sys.feeds, *sys.products) for x in st.mass]
    checks.append(dict(check="Frozen model flows unchanged by LCA", value=float(unchanged), expected=1.0,
                       status="PASS" if unchanged else "FAIL"))
    tables["08_checks"] = checks
    os.makedirs(out_dir, exist_ok=True)
    with pd.ExcelWriter(os.path.join(out_dir, "att_lca_gwp100.xlsx"), engine="openpyxl") as writer:
        for name, rows in tables.items():
            df = pd.DataFrame(rows)
            df.to_csv(os.path.join(out_dir, f"{name}.csv"), index=False)
            df.to_excel(writer, sheet_name=name[:31], index=False)
    return tables
