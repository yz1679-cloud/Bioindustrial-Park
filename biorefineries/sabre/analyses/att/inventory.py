"""
Research-stage material/energy inventory, preliminary LCI and TEA cost inputs
for the ATT baseline (user decisions 2026-10-09; att.yaml ``inventory``).

Bases
-----
- Simulation basis: ``create_att_system(dry_sargassum_kgph=1.0)``.
- Reference scale: the SaBRe common plant scale (feedstock.yaml ``scale``,
  tea.yaml ``operating_days``). Material and heat flows per kg dry feed do
  not depend on scale (checked by ``compare_scale_invariance``); electricity
  and equipment do (minimum equipment sizes), so per-kg electricity and all
  costs are taken at the reference scale.

Energy accounting (no double counting)
--------------------------------------
- Process heat = HeatUtility.unit_duty; utility heat = HeatUtility.duty
  (process heat plus the 5 % heat loss, applied once).
- U2 natural gas: fuel [MJ LHV] = utility heat / burner efficiency
  (att.energy_sources.natural_gas). The BioSTEAM agent flow already embeds
  its own combustion efficiency and is reported only as a cross-check.
- Steam: boiler natural gas = steam utility heat / boiler efficiency.
- The optional heat-integration scenario is not included.
"""
from contextlib import contextmanager
from math import ceil, exp, log, pi

import numpy as np

import biosteam as bst
from biosteam.units.design_tools import PressureVessel
from biosteam.units.design_tools.specification_factors import pressure_vessel_material_factors
from biosteam.units.design_tools.vacuum import compute_vacuum_system_power_and_cost

from biorefineries.sabre.utils import (
    OPERATING_DAYS_PER_YEAR, OPERATING_HOURS_PER_YEAR, get_scale_feed_kgph, load_assumptions,
)

__all__ = (
    "get_att_reference_scale",
    "get_att_external_flows",
    "get_att_u2_balance_checks",
    "get_att_product_scenarios",
    "get_att_chemical_ledger",
    "get_att_carbon_fate",
    "get_att_unit_energy",
    "get_att_cost_estimates",
    "get_att_purchased_utilities",
    "get_att_lci",
    "get_att_equipment_inventory",
    "get_att_tea_inputs",
    "get_att_unit_streams",
    "get_att_unit_balances",
    "get_att_stream_sanity_check",
    "get_att_water_balance",
    "get_att_sodium_calcium_ledger",
    "get_att_gas_accounting",
    "get_att_unit_energy_balance",
    "get_att_utility_consistency_check",
    "get_att_final_assumptions",
    "check_att_inventory",
    "compare_scale_invariance",
    "get_att_assumption_register",
    "build_att_inventory_tables",
    "export_att_inventory",
)

_ATT = load_assumptions("att.yaml")["att"]
_INV = _ATT["inventory"]
_LCA = _INV["lca"]
_NG = _ATT["energy_sources"]["natural_gas"]
_FEEDSTOCK = load_assumptions("feedstock.yaml")
_TEA = load_assumptions("tea.yaml")
_MW = {"H2": 2.01588, "CH4": 16.04246, "CO": 28.0101, "CO2": 44.0095}
_GAS_ELECTRONS = {"H2": 2, "CH4": 8, "CO": 2, "CO2": 0}
_NA_FRACTION = {"NaOH": 22.98977 / 39.99711, "Na2CO3": 2 * 22.98977 / 105.9888}
_THORNTON_kJ_PER_MOL_E = 110.0  # HHV per mol available electrons (Thornton's rule)


def _units(sys):
    return {u.ID: u for u in sys.units}


def _streams(sys):
    return {s.ID: s for s in (*sys.feeds, *sys.products)}


def _dry_feed_kgph(sys):
    feed = _streams(sys)["att_sargassum_feed"]
    return float(feed.F_mass - feed.imass["Water"])


def get_att_reference_scale(configuration="att_only"):
    """
    SaBRe common plant scale (project-wide assumption): 15,000 wet t/d of
    fresh Sargassum. For the integrated case the ATT plant receives the
    presscake of that Sargassum from a biostimulant plant.
    """
    from biorefineries.sabre.systems._att_system import get_att_reference_dry_feed_kgph

    feed_type = _ATT["feed_preparation"]["feedstock_type" if configuration == "att_only"
                                         else "integrated_feedstock_type"]
    moisture = float(_FEEDSTOCK["feedstock_type"][feed_type]["moisture_frac"])
    dry_kgph = get_att_reference_dry_feed_kgph(configuration)
    wet_kgph = dry_kgph / (1.0 - moisture)
    return dict(
        configuration=configuration,
        wet_feed_t_per_day=wet_kgph * 24.0 / 1000.0,
        wet_feed_kgph=wet_kgph,
        moisture_frac=moisture,
        dry_feed_kgph=dry_kgph,
        dry_feed_t_per_day=dry_kgph * 24.0 / 1000.0,
        operating_days_per_year=float(OPERATING_DAYS_PER_YEAR),
        operating_hours_per_year=float(OPERATING_HOURS_PER_YEAR),
        dry_feed_t_per_year=dry_kgph * OPERATING_HOURS_PER_YEAR / 1000.0,
        basis=_INV["reference_scale"]["basis"],
        status=_INV["reference_scale"]["status"],
    )


# ---------------------------------------------------------------------------
# Material inventory
# ---------------------------------------------------------------------------

def get_att_external_flows(sys):
    """Every external stream with its fate, total and component flows."""
    dry = _dry_feed_kgph(sys)
    fates = _INV["stream_fates"]
    rows = []
    for s in (*sys.feeds, *sys.products):
        direction, category, note = fates[s.ID]  # KeyError: undocumented stream
        expected = "input" if s in sys.feeds else "output"
        if direction != expected:
            raise ValueError(f"{s.ID} is a system {expected} but documented as {direction}")
        base = dict(stream=s.ID, direction=direction, category=category, T_C=float(s.T) - 273.15)
        rows.append(dict(base, component="TOTAL", kg_per_h=float(s.F_mass),
                         kg_per_kg_dry=float(s.F_mass) / dry, note=note))
        for ID, m in zip(s.chemicals.IDs, s.mass):
            if m > 0.0:
                rows.append(dict(base, component=ID, kg_per_h=float(m),
                                 kg_per_kg_dry=float(m) / dry, note=""))
    return rows


def get_att_u2_balance_checks(sys):
    """U2 checks: NaOH capacity for CO2, electrons, mass and energy (ATTReactor.balance_checks)."""
    return _units(sys)["U2"].balance_checks()


def get_att_product_scenarios(sys):
    """Specified U2 gas yields, H2 product and off-gas."""
    U2 = _units(sys)["U2"]
    daf = float(U2._daf_sargassum_kgph)
    dry = _dry_feed_kgph(sys)
    streams = _streams(sys)
    U2_gas = U2.outs[0]
    tail = streams["u3_tail_gas"]
    psa = float(_ATT["gas_treatment"]["psa_h2_recovery"])
    spec = {k: float(v) for k, v in U2.reported_gas_yield_mmol_per_g_daf.items()}
    method = "specified_yields"
    rows = []
    for k in _MW:
        rows.append(dict(closure=method, item=f"{k} in U2 gas", specified_mmol_per_g_daf=spec.get(k, 0.0),
                         kg_per_h_at_sim_basis=float(U2_gas.imass[k]),
                         kg_per_kg_dry=float(U2_gas.imass[k]) / dry,
                         status="specified (experimental team)" if k in spec else "not specified"))
    h2 = float(streams["h2_product"].imass["H2"])
    rows.append(dict(closure=method, item="H2 product (after PSA)", kg_per_h_at_sim_basis=h2,
                     kg_per_kg_dry=h2 / dry, status=f"PSA recovery {psa}"))
    for k in _MW:
        v = float(tail.imass[k])
        rows.append(dict(closure=method, item=f"{k} in collected off-gas", kg_per_h_at_sim_basis=v,
                         kg_per_kg_dry=v / dry, status=""))
    return rows


def get_att_chemical_ledger(sys):
    """NaOH, Ca(OH)2, CaCO3 and sodium flows."""
    dry = _dry_feed_kgph(sys)
    s = _streams(sys)
    u = _units(sys)
    recycle = u["EC1"].outs[0]
    to_U2 = u["U2"].ins[0]
    cake, purge, ash = s["caco3_cake"], s["liquor_purge"], s["ash_residue_cake"]

    def na(stream):
        return sum(_NA_FRACTION[k] * float(stream.imass[k]) for k in _NA_FRACTION)

    lime = float(s["lime"].imass["CaOH2"])
    lime_equiv = float(_ATT["downstream"]["lime_equiv"])
    items = [
        ("NaOH makeup (fresh solid)", float(s["fresh_naoh_solid"].imass["NaOH"]), "consumption"),
        ("NaOH in recycle liquor to U2 (after makeup)", float(recycle.imass["NaOH"]), "internal recycle"),
        ("NaOH entering U2 (gross)", float(to_U2.imass["NaOH"]), "internal"),
        ("Water in recycle liquor", float(recycle.imass["Water"]), "internal recycle"),
        ("Na2CO3 in recycle liquor", float(recycle.imass["Na2CO3"]), "internal recycle"),
        ("Ca(OH)2 input", lime, "consumption"),
        ("Ca(OH)2 stoichiometric part", lime / lime_equiv, "consumption"),
        ("CaCO3 in CaCO3 cake (coproduct)", float(cake.imass["CaCO3"]), "coproduct, no credit"),
        ("Unreacted Ca(OH)2 in CaCO3 cake", float(cake.imass["CaOH2"]), "coproduct, no credit"),
        ("NaOH entrained in CaCO3 cake", float(cake.imass["NaOH"]), "loss"),
        ("Na2CO3 entrained in CaCO3 cake", float(cake.imass["Na2CO3"]), "loss"),
        ("NaOH in liquor purge", float(purge.imass["NaOH"]), "loss"),
        ("Na2CO3 in liquor purge", float(purge.imass["Na2CO3"]), "loss"),
        ("Na2CO3 in ash residue cake", float(ash.imass["Na2CO3"]), "loss"),
        ("Na in: NaOH makeup", na(s["fresh_naoh_solid"]), "Na balance"),
        ("Na out: CaCO3 cake", na(cake), "Na balance"),
        ("Na out: liquor purge", na(purge), "Na balance"),
        ("Na out: ash residue cake", na(ash), "Na balance"),
    ]
    return [dict(item=i, kg_per_h_at_sim_basis=v, kg_per_kg_dry=v / dry, role=r) for i, v, r in items]


def get_att_carbon_fate(sys):
    """Biogenic carbon from the feedstock to each external output [kg C]."""
    dry = _dry_feed_kgph(sys)
    rows = []
    for s in (*sys.feeds, *sys.products):
        C = float(s.get_atomic_flow("C")) * 12.011
        if C > 0.0:
            rows.append(dict(stream=s.ID, direction="input" if s in sys.feeds else "output",
                             category=_INV["stream_fates"][s.ID][1],
                             kg_C_per_h_at_sim_basis=C, kg_C_per_kg_dry=C / dry))
    return rows


# ---------------------------------------------------------------------------
# Energy inventory
# ---------------------------------------------------------------------------

def get_att_unit_energy(sys):
    """Unit-level heating, cooling and electricity as simulated."""
    dry = _dry_feed_kgph(sys)
    rows = []
    for unit in sys.units:
        for hu in unit.heat_utilities:
            if abs(hu.duty) <= 1e-12:
                continue
            heating = hu.duty > 0.0
            rows.append(dict(
                unit=unit.ID, kind="heating" if heating else "cooling", agent=hu.agent.ID,
                process_duty_MJ_per_kg_dry=hu.unit_duty / 1e3 / dry,
                heat_loss_MJ_per_kg_dry=(hu.duty - hu.unit_duty) / 1e3 / dry if heating else 0.0,
                utility_duty_MJ_per_kg_dry=hu.duty / 1e3 / dry,
                agent_kg_per_kg_dry=hu.flow * hu.agent.MW / dry,
                electricity_kWh_per_kg_dry=0.0,
            ))
        if unit.power_utility.rate > 0.0:
            rows.append(dict(unit=unit.ID, kind="electricity", agent="electricity",
                             process_duty_MJ_per_kg_dry=0.0, heat_loss_MJ_per_kg_dry=0.0,
                             utility_duty_MJ_per_kg_dry=0.0, agent_kg_per_kg_dry=0.0,
                             electricity_kWh_per_kg_dry=unit.power_utility.rate / dry))
    return rows


@contextmanager
def _scratch_flowsheet():
    previous = bst.main_flowsheet.get_flowsheet()
    bst.main_flowsheet.set_flowsheet("att_cost_estimates")
    try:
        yield
    finally:
        bst.main_flowsheet.set_flowsheet(previous)


class _VesselEstimate(bst.Unit, PressureVessel):
    """Vertical vessel of a given volume (cost estimate only)."""
    _N_ins = _N_outs = 1
    _units = {"Pressure": "psi", "Diameter": "ft", "Length": "ft", "Wall thickness": "in", "Weight": "lb"}
    _F_BM_default = {"Vertical pressure vessel": 4.16, "Platform and ladders": 1.0}

    def __init__(self, ID, ins, volume_m3, length_to_diameter, material):
        super().__init__(ID, ins)
        self.volume_m3 = volume_m3
        self.length_to_diameter = length_to_diameter
        self.vessel_type = "Vertical"
        # BioSTEAM has no density for most alloys: size the wall with SS316
        # and apply the material factor of the specified alloy.
        self.vessel_material = "Stainless steel 316"
        self.F_M["Vertical pressure vessel"] = pressure_vessel_material_factors[material]

    def _run(self):
        self.outs[0].copy_like(self.ins[0])

    def _design(self):
        D_m = (4.0 * self.volume_m3 / (pi * self.length_to_diameter)) ** (1.0 / 3.0)
        self._design_and_cost_pressure_vessel(
            101325.0, D_m, self.length_to_diameter * D_m,
            pressure_units="Pa", length_units="m",
        )

    def _cost(self):
        pass


def get_att_cost_estimates(sys):
    """Engineering cost estimates for units without a BioSTEAM cost (TEA only)."""
    est = _INV["cost_estimates"]
    u = _units(sys)
    rows = []
    with _scratch_flowsheet():
        for ID, feed in (("C1", u["C1"].outs[0]),):
            tank = bst.MixTank(f"{ID}_estimate", ins=feed.copy(), tau=est[ID]["tau_h"])
            tank.simulate()
            rows.append(dict(unit=ID, item=f"{ID} agitated tank", purchase_cost=tank.purchase_cost,
                             installed_cost=tank.installed_cost, power_kW=tank.power_utility.rate,
                             size=f"{tank.design_results['Total volume']:.1f} m3 total",
                             method=f"{est[ID]['method']}, tau {est[ID]['tau_h']} h", note=est[ID]["note"]))

        v = est["U2_vessel"]
        feed = u["U2"].ins[0]
        volume = feed.F_mass / v["density_kg_per_m3"] * v["tau_h"] / v["fill_fraction"]
        vessel = _VesselEstimate("U2_vessel_estimate", feed.copy(), volume, v["length_to_diameter"], v["material"])
        vessel.simulate()
        rows.append(dict(unit="U2", item="U2 reactor vessel", purchase_cost=vessel.purchase_cost,
                         installed_cost=vessel.installed_cost, power_kW=0.0,
                         size=f"{volume:.1f} m3", method=f"{v['method']}, {v['material']}, tau {v['tau_h']} h",
                         note=v["note"]))

        e = est["EC1"]
        EC1 = u["EC1"]
        steam = [hu for hu in EC1.heat_utilities if hu.duty > 0.0]
        Q = sum(hu.unit_duty for hu in steam)
        if Q > 0.0:
            dT = steam[0].agent.T - EC1.T
            area = Q / (e["U_W_per_m2_K"] * 3.6 * dT)  # m2
            # Seider et al. forced-circulation evaporator, A in ft2 (150-8000
            # ft2 per unit), CE 500. BioSTEAM's tabulated lambda multiplies A
            # by 0.0929 although its areas are in m2, so it is not used here.
            area_ft2 = area * 10.7639
            n = max(1, ceil(area_ft2 / 8000.0))
            lnA = log(area_ft2 / n)
            evaporator = n * bst.CE / 500.0 * exp(8.2986 + 0.5329 * lnA - 0.000196 * lnA * lnA)
            rows.append(dict(unit="EC1", item="EC1 forced-circulation evaporator", purchase_cost=evaporator,
                             installed_cost=2.45 * evaporator, power_kW=0.0,
                             size=f"{area:.0f} m2 in {n} unit(s)", method=e["method"], note=e["note"]))
            vapor = EC1.outs[1].copy()
            vapor.phase = "g"
            vapor.T = EC1.T
            vapor.P = EC1._operating_pressure_Pa
            condenser = bst.HXutility("EC1_condenser_estimate", ins=vapor, V=0.0, rigorous=False)
            condenser.simulate()
            rows.append(dict(unit="EC1", item="EC1 condenser", purchase_cost=condenser.purchase_cost,
                             installed_cost=condenser.installed_cost, power_kW=0.0,
                             size=f"{condenser.design_results.get('Area', float('nan')):.0f} ft2",
                             method="bst.HXutility (cooling water)", note="Duty equals the EC1 cooling utility."))
            liquor_m3ph = EC1.ins[0].F_mass / e["liquor_density_kg_per_m3"]
            vessel_m3 = liquor_m3ph * e["vessel_holdup_h"] / e["vessel_fill_fraction"]
            vacuum = compute_vacuum_system_power_and_cost(0.0, 0.0, EC1._operating_pressure_Pa, vessel_m3)
            rows.append(dict(unit="EC1", item=f"EC1 vacuum system ({vacuum['Name']})", purchase_cost=vacuum["Cost"],
                             installed_cost=vacuum["Cost"], power_kW=vacuum["Work"],
                             size=f"{vessel_m3:.1f} m3 vessel", method="BioSTEAM vacuum-system correlation",
                             note="Air in-leakage only; condenser removes the vapor."))

    rows.append(dict(unit="U3P", item="PSA unit", purchase_cost=float("nan"), installed_cost=float("nan"),
                     power_kW=float("nan"), size="", method="none", note=est["U3P"]["note"]))
    return rows


def get_att_tail_gas_offset(sys):
    """
    Natural gas displaced by burning the PSA tail gas in the U2 burner
    (simple offset; att.yaml gas_treatment.tail_gas_combustion). The tail gas
    LHV replaces the same LHV of natural gas, up to U2's fuel demand
    (delivered heat / burner efficiency). Fuel basis, MJ/h.
    """
    enabled = load_assumptions("att.yaml")["att"]["gas_treatment"]["tail_gas_combustion"] == "offset_u2_natural_gas"
    tail = _streams(sys)["u3_tail_gas"]
    tail_LHV = float(tail.LHV) / 1e3 if tail.F_mol else 0.0
    ng = [hu for hu in sys.heat_utilities if hu.agent and hu.agent.ID == "natural_gas"]
    u2_fuel = sum(hu.duty for hu in ng) / 1e3 / float(_NG["burner_efficiency"])
    offset = min(tail_LHV, u2_fuel) if enabled else 0.0
    return dict(enabled=enabled, tail_gas_LHV_MJph=tail_LHV, u2_fuel_MJph=u2_fuel, offset_MJph=offset,
                displaced_fraction=offset / u2_fuel if u2_fuel else 0.0)


def get_att_purchased_utilities(sys, cost_estimates=None):
    """Purchased utilities and their primary-energy basis."""
    dry = _dry_feed_kgph(sys)
    hus = [(unit, hu) for unit in sys.units for hu in unit.heat_utilities if abs(hu.duty) > 1e-12]
    ng = [hu for _, hu in hus if hu.agent.ID == "natural_gas"]
    steam = [hu for _, hu in hus if hu.agent.ID.endswith("steam")]
    cw = [hu for _, hu in hus if hu.agent.ID == "cooling_water"]
    other = [hu.agent.ID for _, hu in hus if hu not in ng + steam + cw]
    if other:
        raise ValueError(f"Unaccounted utility agents: {other}")
    burner = float(_NG["burner_efficiency"])
    boiler = float(_LCA["steam_boiler_efficiency"])
    ng_heat = sum(hu.duty for hu in ng)
    steam_heat = sum(hu.duty for hu in steam)
    cw_kmolph = sum(hu.flow for hu in cw)
    ch4_LHV_kJ_per_kmol = bst.Chemical("CH4").LHV
    offset = get_att_tail_gas_offset(sys)
    modeled_power = sum(unit.power_utility.rate for unit in sys.units)
    cw_power = cw_kmolph * sum(_LCA["cooling_water_kW_per_kmolph"])
    # Equipment-based estimates exist only where costs were estimated.
    estimated_power = (sum(r["power_kW"] for r in cost_estimates if r["power_kW"] == r["power_kW"])
                       if cost_estimates else float("nan"))
    rows = [
        ("U2 natural gas: process heat", sum(hu.unit_duty for hu in ng) / 1e3, "MJ", "simulated"),
        ("U2 natural gas: heat delivered incl. 5 % reactor loss", ng_heat / 1e3, "MJ", "simulated"),
        ("U2 natural gas: fuel input (LHV)", ng_heat / 1e3 / burner, "MJ",
         f"= delivered / burner efficiency {burner}; used for TEA and LCA"),
        ("U2 natural gas displaced by PSA tail gas (offset)", offset["offset_MJph"], "MJ",
         f"tail gas LHV {offset['tail_gas_LHV_MJph'] / dry:.4g} MJ/kg dry; burned in the U2 burner, capped at U2 fuel"),
        ("U2 natural gas: BioSTEAM agent fuel (cross-check only)",
         sum(hu.flow for hu in ng) * ch4_LHV_kJ_per_kmol / 1e3, "MJ", "BioSTEAM agent flow x CH4 LHV; not used"),
        ("LP steam: process heat", sum(hu.unit_duty for hu in steam) / 1e3, "MJ", "D0, U3D, C1, EC1"),
        ("LP steam: utility heat incl. 5 % loss", steam_heat / 1e3, "MJ", "simulated"),
        ("LP steam: mass", sum(hu.flow * hu.agent.MW for hu in steam), "kg", "simulated"),
        ("LP steam: boiler natural gas (LHV)", steam_heat / 1e3 / boiler, "MJ",
         f"= steam heat / boiler efficiency {boiler} (assumed on-site NG boiler)"),
        ("Cooling water: heat removed", -sum(hu.duty for hu in cw) / 1e3, "MJ", "simulated"),
        ("Cooling water: circulation", sum(hu.flow * hu.agent.MW for hu in cw), "kg", "simulated"),
        ("Electricity: modeled units", modeled_power, "kWh", "simulated"),
        ("Electricity: cooling tower and CW pumps (estimate)", cw_power, "kWh", "BioSTEAM CoolingTower correlation"),
        ("Electricity: agitators and EC1 vacuum (estimate)", estimated_power, "kWh", "cost-estimate units"),
        ("Electricity: total", modeled_power + cw_power + estimated_power, "kWh", ""),
        ("Process water (D1)", float(_streams(sys)["dissolution_water"].F_mass), "kg", "simulated"),
    ]
    return [dict(item=i, per_kg_dry=v / dry, unit=f"{un}/kg dry", note=n) for i, v, un, n in rows]


# ---------------------------------------------------------------------------
# Preliminary LCI (GWP)
# ---------------------------------------------------------------------------

def get_att_lci(flows, utilities, products, ca_source=None):
    """
    Preliminary life-cycle inventory and GWP per kg dry feed.

    ``flows``, ``utilities`` and ``products`` are the tables returned by
    get_att_external_flows, get_att_purchased_utilities and
    get_att_product_scenarios (normalized per kg dry feed).
    """
    ef = _LCA["emission_factors"]
    ca_key = ca_source or _LCA["ca_oh2_baseline_source"]
    total = {(r["stream"], r["component"]): r["kg_per_kg_dry"] for r in flows}
    util = {r["item"]: r["per_kg_dry"] for r in utilities}
    ng_ef = float(_NG["emission_factor_kgCO2e_per_MJ_fuel"])

    def factor(name):
        f = ef[name]
        return f["value"], f["range"], f"{f['unit']}; {f['source']}"

    rows = []

    def add(flow, amount, unit, value, ef_range, source, status):
        gwp = amount * value if value is not None else float("nan")
        lo = amount * ef_range[0] if ef_range else gwp
        hi = amount * ef_range[1] if ef_range else gwp
        rows.append(dict(flow=flow, amount_per_kg_dry=amount, unit=unit, EF=value, EF_source=source,
                         GWP_kgCO2e_per_kg_dry=gwp, GWP_low=lo, GWP_high=hi, status=status))

    add("Sargassum (dry basis)", 1.0, "kg", 0.0, None, "Waste biomass; collection/transport excluded",
        "DECISION NEEDED: zero upstream burden assumed")
    add("NaOH makeup", total[("fresh_naoh_solid", "NaOH")], "kg", *factor("NaOH"), "collaborators")
    add(f"Ca(OH)2 ({ca_key})", total[("lime", "CaOH2")], "kg", *factor(ca_key), "collaborators")
    add("Natural gas, U2 fuel", util["U2 natural gas: fuel input (LHV)"], "MJ", ng_ef, None,
        "kg CO2/MJ fuel; collaborators (combustion CO2 only)", "collaborators")
    add("Natural gas, steam boiler", util["LP steam: boiler natural gas (LHV)"], "MJ", ng_ef, None,
        f"kg CO2/MJ fuel; boiler efficiency {_LCA['steam_boiler_efficiency']}", "derived")
    add("Electricity, total", util["Electricity: total"], "kWh", *factor("electricity"),
        "BioSTEAM project; location-dependent")
    add("Process water", util["Process water (D1)"], "kg", None, None, "", "MISSING (expected negligible)")
    for stream, label in (("ash_residue_cake", "Ash/char residue to disposal"),
                          ("liquor_purge", "Alkaline purge treatment"),
                          ("u3_condensate", "Wastewater: U3 condensate"),
                          ("ec1_condensate", "Wastewater: EC1 condensate")):
        add(label, total[(stream, "TOTAL")], "kg", None, None, "", "MISSING")
    add("CaCO3 cake (coproduct)", total[("caco3_cake", "TOTAL")], "kg", 0.0, None,
        "No credit or burden by decision", "excluded by decision")
    add("PSA off-gas (collected)", total[("u3_tail_gas", "TOTAL")], "kg", 0.0, None,
        "Collected; no combustion credit. Its CO2 is biogenic (0 GWP if released); CH4 fugitive losses "
        "not modeled", "excluded by decision")

    known = [r for r in rows if r["GWP_kgCO2e_per_kg_dry"] == r["GWP_kgCO2e_per_kg_dry"]]
    gwp = sum(r["GWP_kgCO2e_per_kg_dry"] for r in known)
    lo = sum(r["GWP_low"] for r in known)
    hi = sum(r["GWP_high"] for r in known)
    rows.append(dict(flow="TOTAL (excluding MISSING items)", amount_per_kg_dry=1.0, unit="kg dry feed",
                     EF=None, EF_source="", GWP_kgCO2e_per_kg_dry=gwp, GWP_low=lo, GWP_high=hi, status=""))
    for r in products:
        if r["item"] == "H2 product (after PSA)":
            kg = r["kg_per_kg_dry"]
            rows.append(dict(flow=f"GWP per kg H2 ({r['closure']})", amount_per_kg_dry=kg, unit="kg H2/kg dry",
                             EF=None, EF_source="", GWP_kgCO2e_per_kg_dry=gwp / kg, GWP_low=lo / kg,
                             GWP_high=hi / kg, status="per kg H2 (no allocation to coproducts)"))
    return rows


# ---------------------------------------------------------------------------
# Equipment and TEA inputs
# ---------------------------------------------------------------------------

_NO_EQUIPMENT = ("Mixer", "Splitter")


def get_att_equipment_inventory(sys, cost_estimates):
    rows = []
    estimated = {r["unit"] for r in cost_estimates}
    for unit in sys.units:
        kind = type(unit).__name__
        if unit.purchase_cost > 0.0:
            status = "BioSTEAM correlation"
            if unit.ID == "U2":
                status += " (furnace only; vessel estimated separately)"
        elif kind in _NO_EQUIPMENT and unit.ID not in estimated:
            status = "stream junction, no equipment"
        elif unit.ID in estimated:
            status = "no model cost; see estimate rows"
        else:
            status = "MISSING"
        rows.append(dict(unit=unit.ID, item=kind, purchase_cost=unit.purchase_cost,
                         installed_cost=unit.installed_cost, power_kW=unit.power_utility.rate,
                         source=status, method="", note=""))
    for r in cost_estimates:
        rows.append(dict(unit=r["unit"], item=r["item"], purchase_cost=r["purchase_cost"],
                         installed_cost=r["installed_cost"], power_kW=r["power_kW"],
                         source="ENGINEERING ESTIMATE" if r["method"] != "none" else "MISSING",
                         method=r["method"], note=f"{r['size']}; {r['note']}"))
    for item, note in (
        ("Feed receiving, conveyors, solids handling", "Not modeled; TEA factor or estimate needed"),
        ("Storage (NaOH, Ca(OH)2, H2 product, off-gas)", "Not modeled"),
        ("Liquid and slurry pumps", "Not modeled (small power)"),
        ("Steam boiler and cooling tower (OSBL)", "Represented by purchased-utility prices; no capital"),
        ("Wastewater / purge neutralization", "Not modeled; disposal price in TEA"),
    ):
        rows.append(dict(unit="-", item=item, purchase_cost=float("nan"), installed_cost=float("nan"),
                         power_kW=float("nan"), source="NOT MODELED", method="", note=note))
    return rows


def get_att_tea_inputs():
    """TEA inputs: what is set, where from, and what is still missing."""
    scale = get_att_reference_scale()
    price = _TEA["price"]
    tea = _TEA["tea"]
    lps = bst.HeatUtility.get_agent("low_pressure_steam")
    cw = bst.HeatUtility.get_agent("cooling_water")
    ng = bst.HeatUtility.get_agent("natural_gas")
    rows = [
        ("Plant capacity", f"{scale['wet_feed_t_per_day']:.0f} wet t/d = {scale['dry_feed_t_per_day']:.0f} dry t/d",
         "feedstock.yaml scale (SaBRe common)", "set"),
        ("Operating time", f"{scale['operating_days_per_year']:.0f} d/yr = {scale['operating_hours_per_year']:.0f} h/yr",
         "tea.yaml operating_days", "set"),
        ("Financial parameters", ", ".join(f"{k}={tea[k]}" for k in ("IRR", "duration", "depreciation", "income_tax")),
         "tea.yaml tea (SaBReTEA)", "set"),
        ("Fixed operating cost", f"{tea['foc_frac_of_fci']} x FCI", "tea.yaml tea", "set"),
        ("Sargassum price", f"{price['sargassum']['baseline']} USD/kg wet (range {price['sargassum']['range']})",
         "tea.yaml price.sargassum", "set"),
        ("NaOH price", f"{price['naoh']['baseline']} USD/kg", "tea.yaml price.naoh (no literature source)",
         "set; source to verify"),
        ("Ca(OH)2 price", "", "", "MISSING"),
        ("Natural gas price", f"{ng.regeneration_price} USD/kmol (BioSTEAM default agent)", "BioSTEAM default",
         "set; confirm"),
        ("LP steam price", f"{lps.regeneration_price} USD/kmol (BioSTEAM default)", "BioSTEAM default",
         "set; or derive from NG boiler"),
        ("Cooling water price", f"{cw.regeneration_price} USD/kmol (BioSTEAM default)", "BioSTEAM default", "set"),
        ("Electricity price", f"{bst.PowerUtility.price} USD/kWh (BioSTEAM default)", "BioSTEAM default", "set; confirm"),
        ("Process water price", "", "", "MISSING (minor)"),
        ("H2 price", "solve minimum selling price", "SaBReTEA.solve_price", "output"),
        ("CH4 off-gas value", "0 in baseline; later scenario", "user decision 2026-10-09", "scenario"),
        ("CaCO3 value", "0 in baseline", "user decision 2026-10-09", "scenario"),
        ("Solid disposal (ash/char cake)", f"{price['disposal_solid']['baseline']} USD/kg", "tea.yaml disposal_solid", "set"),
        ("Wastewater disposal", f"{price['disposal_wastewater']['baseline']} USD/kg", "tea.yaml disposal_wastewater",
         "set; caustic purge may need neutralization cost"),
        ("PSA capital", "", "", "MISSING"),
    ]
    return [dict(input=a, value=b, source=c, status=d) for a, b, c, d in rows]


# ---------------------------------------------------------------------------
# Final verification tables
# ---------------------------------------------------------------------------

_ELEMENTS = ("C", "H", "O", "N", "S", "Na", "Ca")


def _component_basis(U2):
    """Origin of the U2 outlet components."""
    return {
        ("att_gas", "H2"): "SPECIFIED: experimental team yield",
        ("att_gas", "CH4"): "SPECIFIED: experimental team yield",
        ("att_gas", "CO"): "SPECIFIED: experimental team yield",
        ("att_gas", "CO2"): "SPECIFIED yield + carbon not otherwise assigned (C balance)",
        ("att_gas", "Water"): "MODEL: oxygen balance (product water)",
        ("att_residue", "Na2CO3"): "SPECIFIED: NaOH -> Na2CO3 (experimental team)",
        ("att_residue", "Ash"): "SPECIFIED: inert ash",
    }


def get_att_unit_streams(sys):
    """All unit inlet/outlet streams with component mass flows."""
    dry = _dry_feed_kgph(sys)
    U2 = _units(sys)["U2"]
    basis = _component_basis(U2)
    feeds = {s.ID for s in sys.feeds}
    rows = []
    for unit in sys.units:
        for port, streams in (("in", unit.ins), ("out", unit.outs)):
            for i, s in enumerate(streams):
                head = dict(unit=unit.ID, port=f"{port}{i}", stream=s.ID, phase=s.phase,
                            T_C=float(s.T) - 273.15, P_kPa=float(s.P) / 1e3)
                rows.append(dict(head, component="TOTAL", kg_per_h=float(s.F_mass),
                                 kg_per_kg_dry=float(s.F_mass) / dry, basis=""))
                for ID, m in zip(s.chemicals.IDs, s.mass):
                    if m != 0.0:
                        if s.ID in feeds:
                            b = "SPECIFIED INPUT"
                        else:
                            b = basis.get((s.ID, ID), "calculated (unit model)")
                        rows.append(dict(head, component=ID, kg_per_h=float(m),
                                         kg_per_kg_dry=float(m) / dry, basis=b))
    return rows


def get_att_unit_balances(sys):
    """Total-mass and element balance of every unit (relative errors)."""
    rows = []
    for unit in sys.units:
        m_in = sum(float(s.F_mass) for s in unit.ins)
        m_out = sum(float(s.F_mass) for s in unit.outs)
        row = dict(unit=unit.ID, type=type(unit).__name__, mass_in_kgph=m_in, mass_out_kgph=m_out,
                   mass_relative_error=(m_out - m_in) / m_in if m_in else 0.0)
        for e in _ELEMENTS:
            a_in = sum(float(s.get_atomic_flow(e)) for s in unit.ins)
            a_out = sum(float(s.get_atomic_flow(e)) for s in unit.outs)
            row[f"{e}_relative_error"] = (a_out - a_in) / a_in if a_in > 0.0 else a_out
        rows.append(row)
    return rows


def get_att_stream_sanity_check(sys):
    """Negative or non-finite flows and implausible states in every stream."""
    seen, rows = set(), []
    for unit in sys.units:
        for s in (*unit.ins, *unit.outs):
            if s.ID in seen:
                continue
            seen.add(s.ID)
            data = s.imol.data
            flows = data.to_array() if hasattr(data, "to_array") else np.asarray(data)
            issues = []
            if np.any(flows < -1e-12):
                issues.append(f"negative flow (min {flows.min():.3g} kmol/h)")
            if not np.all(np.isfinite(flows)):
                issues.append("non-finite flow")
            if s.F_mass > 0.0 and not 273.15 <= s.T <= 1000.0:
                issues.append(f"temperature {s.T:.1f} K")
            if s.F_mass > 0.0 and s.P <= 0.0:
                issues.append("non-positive pressure")
            rows.append(dict(stream=s.ID, kg_per_h=float(s.F_mass), phase=s.phase,
                             status="OK" if not issues else "; ".join(issues)))
    return rows


def get_att_water_balance(sys):
    """Water inputs, reaction, evaporation, condensation and wastewater."""
    dry = _dry_feed_kgph(sys)
    s = _streams(sys)
    u = _units(sys)
    fates = _INV["stream_fates"]
    rows = []
    w_in = 0.0
    for f in sys.feeds:
        w = float(f.imass["Water"])
        w_in += w
        rows.append(dict(group="input", item=f.ID, kg_per_kg_dry=w / dry))
    formation = u["U2"]._net_water_formation_kmolph * 18.01528
    rows.append(dict(group="reaction", item="U2 net water formation (negative = consumed)",
                     kg_per_kg_dry=formation / dry))
    w_out = 0.0
    for p in sys.products:
        w = float(p.imass["Water"])
        w_out += w
        rows.append(dict(group=f"output ({fates[p.ID][1]})", item=p.ID, kg_per_kg_dry=w / dry))
    rows += [
        dict(group="internal", item="P1 mechanical dewatering (juice, if present)",
             kg_per_kg_dry=(float(s["biostimulant_juice"].imass["Water"]) / dry) if "biostimulant_juice" in s else 0.0),
        dict(group="internal", item="D0 thermal drying (evaporated)",
             kg_per_kg_dry=float(s["dryer_exhaust"].imass["Water"] - s["dryer_air"].imass["Water"]) / dry),
        dict(group="internal", item="U3 condensation (U3C + U3D)",
             kg_per_kg_dry=float(s["u3_condensate"].imass["Water"] + s["u3_dryer_removed_water"].imass["Water"]) / dry),
        dict(group="internal", item="EC1 evaporation (= condensate)",
             kg_per_kg_dry=float(s["ec1_condensate"].imass["Water"]) / dry),
        dict(group="internal", item="Wastewater total (condensates)",
             kg_per_kg_dry=sum(float(s[k].imass["Water"]) for k in
                               ("u3_condensate", "u3_dryer_removed_water", "ec1_condensate")) / dry),
        dict(group="check", item="inputs + formation - outputs", kg_per_kg_dry=(w_in + formation - w_out) / dry),
    ]
    return rows


def get_att_sodium_calcium_ledger(sys):
    """NaOH/Na2CO3 formation, conversion, losses, makeup and recycle; Ca."""
    dry = _dry_feed_kgph(sys)
    s = _streams(sys)
    u = _units(sys)
    U2, C1, EC1 = u["U2"], u["C1"], u["EC1"]
    to_U2, residue = U2.ins[0], U2.outs[1]
    C1_in = C1.ins[0]
    C1_out = C1.outs[0]
    makeup = float(s["fresh_naoh_solid"].imass["NaOH"])
    gross = float(to_U2.imass["NaOH"])
    items = [
        ("NaOH entering U2 (gross requirement, 1 kg/kg daf)", gross),
        ("NaOH from recycle (EC1 concentrate)", gross - makeup),
        ("NaOH makeup (fresh solid)", makeup),
        ("Effective NaOH recovery = 1 - makeup / gross", 1.0 - makeup / gross),
        ("U2: NaOH consumed", gross - float(residue.imass["NaOH"])),
        ("U2: Na2CO3 formed", float(residue.imass["Na2CO3"] - to_U2.imass["Na2CO3"])),
        ("U2: Na2CO3 recycled in (EC1 crystals and liquor)", float(to_U2.imass["Na2CO3"])),
        ("C1: Na2CO3 in", float(C1_in.imass["Na2CO3"])),
        ("C1: Na2CO3 converted", float(C1_in.imass["Na2CO3"] - C1_out.imass["Na2CO3"])),
        ("C1: NaOH formed", float(C1_out.imass["NaOH"] - C1_in.imass["NaOH"])),
        ("EC1: Na2CO3 crystallized (recycled as solid)", float(EC1._na2co3_crystals_kgph)),
        ("Loss: NaOH in CaCO3 cake", float(s["caco3_cake"].imass["NaOH"])),
        ("Loss: Na2CO3 in CaCO3 cake", float(s["caco3_cake"].imass["Na2CO3"])),
        ("Loss: NaOH in liquor purge", float(s["liquor_purge"].imass["NaOH"])),
        ("Loss: Na2CO3 in liquor purge", float(s["liquor_purge"].imass["Na2CO3"])),
        ("Loss: Na2CO3 in ash/char cake", float(s["ash_residue_cake"].imass["Na2CO3"])),
        ("Ca(OH)2 input", float(s["lime"].imass["CaOH2"])),
        ("C1: CaCO3 formed (coproduct)", float(C1_out.imass["CaCO3"])),
        ("Unreacted Ca(OH)2 in CaCO3 cake", float(s["caco3_cake"].imass["CaOH2"])),
    ]
    rows = [dict(item=i, value=v if i.startswith("Effective") else v / dry,
                 unit="-" if i.startswith("Effective") else "kg/kg dry") for i, v in items]
    na_in = sum(float(f.get_atomic_flow("Na")) for f in sys.feeds)
    na_out = sum(float(p.get_atomic_flow("Na")) for p in sys.products)
    ca_in = sum(float(f.get_atomic_flow("Ca")) for f in sys.feeds)
    ca_out = sum(float(p.get_atomic_flow("Ca")) for p in sys.products)
    rows.append(dict(item="Na balance (out - in) / in", value=(na_out - na_in) / na_in, unit="-"))
    rows.append(dict(item="Ca balance (out - in) / in", value=(ca_out - ca_in) / ca_in, unit="-"))
    return rows


def get_att_gas_accounting(sys):
    """Specified gas yields, labels, destinations and the CO2 path."""
    U2 = _units(sys)["U2"]
    dry = _dry_feed_kgph(sys)
    specified = {k: float(v) for k, v in U2.reported_gas_yield_mmol_per_g_daf.items()}
    model = U2._model_gas_yield_mmol_per_g_daf
    labels = {
        "H2": ("SPECIFIED (experimental team)", "90 % to h2_product (PSA), 10 % to u3_tail_gas", ""),
        "CH4": ("SPECIFIED (experimental team)", "u3_tail_gas",
                "TEA: no CH4 revenue; tail gas is burned in the U2 burner (natural gas offset)."),
        "CO": ("SPECIFIED (experimental team)", "u3_tail_gas", ""),
        "CO2": ("SPECIFIED yield plus the carbon not otherwise assigned (carbon balance)", "u3_tail_gas",
                "Biogenic CO2."),
    }
    rows = []
    for k in _MW:
        label, destination, flag = labels[k]
        rows.append(dict(species=k, specified_mmol_per_g_daf=specified.get(k, 0.0),
                         model_mmol_per_g_daf=model.get(k, 0.0),
                         model_kg_per_kg_dry=float(U2.outs[0].imass[k]) / dry,
                         basis=label, destination=destination, TEA_LCA_flag=flag))
    # Path of the gas species through U3 (no unit absorbs CO2).
    for ID in ("att_gas", "u3_cooled_multiphase", "u3_wet_gas", "u3_dry_gas", "u3_raw_h2_product",
               "u3_tail_gas", "h2_product"):
        stream = next(s for unit in sys.units for s in (*unit.ins, *unit.outs) if s.ID == ID)
        rows.append(dict(species=f"path: {ID}", specified_mmol_per_g_daf=float("nan"),
                         model_mmol_per_g_daf=float("nan"),
                         model_kg_per_kg_dry=float("nan"),
                         basis=", ".join(f"{k} {float(stream.imass[k]) / dry:.5f}" for k in _MW),
                         destination=f"{stream.source} -> {stream.sink}", TEA_LCA_flag="kg/kg dry"))
    return rows


def _documented_enthalpy_residual(unit):
    """(value or None, explanation) for Hnet(out) - Hnet(in) - process heat."""
    kind = type(unit).__name__
    if unit.ID == "U2":
        return (unit._feed_Hf_HHV_correction_kJph + unit._aqueous_feed_correction_kJph,
                "Feed Hf re-referenced to the HHV + NaOH heat-of-solution correction of the feed")
    if unit.ID == "C1":
        return (-unit._aqueous_reference_correction_kJph,
                "Infinite-dilution aqueous-ion reference for NaOH/Na2CO3 (native Hf replaced)")
    if unit.ID == "EC1":
        return (None, "Duty = latent heat of the evaporated water + liquor sensible heat (heat of "
                      "concentration lumped into the U2 NaOH heat-of-solution term)")
    if kind == "MolecularSieve":
        return (None, "Adsorbent regeneration heat, not carried by process streams (BioSTEAM MolecularSieve)")
    if kind == "IsothermalCompressor":
        return (None, "Cooling = ideal isothermal work; the efficiency loss (power - cooling) is not routed "
                      "to cooling water (BioSTEAM convention)")
    return (0.0, "")


def get_att_unit_energy_balance(sys):
    """Per-unit enthalpy balance: Hnet(out) - Hnet(in) vs process heat."""
    dry = _dry_feed_kgph(sys)
    rows = []
    for unit in sys.units:
        h_in = sum(float(s.Hnet) for s in unit.ins)
        h_out = sum(float(s.Hnet) for s in unit.outs)
        heating = [hu for hu in unit.heat_utilities if hu.duty > 0.0]
        cooling = [hu for hu in unit.heat_utilities if hu.duty < 0.0]
        q = sum(hu.unit_duty for hu in unit.heat_utilities)
        residual = h_out - h_in - q
        documented, note = _documented_enthalpy_residual(unit)
        unexplained = residual - documented if documented is not None else float("nan")
        rows.append(dict(
            unit=unit.ID, type=type(unit).__name__,
            dH_MJ_per_kg_dry=(h_out - h_in) / 1e3 / dry,
            process_heating_MJ_per_kg_dry=sum(hu.unit_duty for hu in heating) / 1e3 / dry,
            process_cooling_MJ_per_kg_dry=sum(hu.unit_duty for hu in cooling) / 1e3 / dry,
            heat_loss_MJ_per_kg_dry=sum(hu.duty - hu.unit_duty for hu in heating) / 1e3 / dry,
            utility_heating_MJ_per_kg_dry=sum(hu.duty for hu in heating) / 1e3 / dry,
            utility_cooling_MJ_per_kg_dry=sum(hu.duty for hu in cooling) / 1e3 / dry,
            heating_agent=",".join(hu.agent.ID for hu in heating),
            electricity_kWh_per_kg_dry=unit.power_utility.rate / dry,
            residual_MJ_per_kg_dry=residual / 1e3 / dry,
            documented_correction_MJ_per_kg_dry=documented / 1e3 / dry if documented is not None else float("nan"),
            unexplained_MJ_per_kg_dry=unexplained / 1e3 / dry,
            explanation=note,
        ))
    return rows


def get_att_utility_consistency_check(sys):
    """Duplicated utilities and consistency of the reporting functions."""
    from biorefineries.sabre.analyses.att.mass_energy import get_att_energy_summary

    u = _units(sys)
    unit_hus = [hu for unit in sys.units for hu in unit.heat_utilities]
    system_total = sum(hu.duty for hu in sys.heat_utilities)
    energy = get_att_energy_summary(sys)
    rows = [
        ("Heat-recovery facility in baseline", any(type(x).__name__ == "ATTHeatRecovery"
                                                   for x in (*sys.units, *sys.facilities)), False),
        ("Sum of unit heat utilities = system heat utilities [kJ/h]", sum(hu.duty for hu in unit_hus), system_total),
        ("U2 heat utility = U2 utility duty attribute [kJ/h]",
         sum(hu.duty for hu in u["U2"].heat_utilities), u["U2"]._utility_heat_duty_kJph),
        ("U2 heat utility = energy summary [kJ/h]",
         sum(hu.duty for hu in u["U2"].heat_utilities), energy["U2_utility_heat_kJph"]),
        ("C1 heat utility = energy summary [kJ/h]",
         sum(hu.duty for hu in u["C1"].heat_utilities), energy["C1_utility_heat_kJph"]),
        ("EC1 heating utility = energy summary [kJ/h]",
         sum(hu.duty for hu in u["EC1"].heat_utilities if hu.duty > 0), energy["EC1_utility_heat_kJph"]),
        ("D0 heat utility = energy summary [kJ/h]",
         sum(hu.duty for hu in u["D0"].heat_utilities), energy["D0_utility_heat_kJph"]),
        ("U2 model H2 = specified H2 [mmol/g daf]", u["U2"]._model_gas_yield_mmol_per_g_daf["H2"],
         float(u["U2"].reported_gas_yield_mmol_per_g_daf["H2"])),
    ]
    out = []
    for item, a, b in rows:
        if isinstance(a, (bool, str)) or isinstance(b, (bool, str)):
            ok = a == b
        else:
            ok = abs(a - b) <= 1e-6 * max(1.0, abs(b))
        out.append(dict(check=item, value=a, expected=b, status="PASS" if ok else "FAIL"))
    return out


def get_att_final_assumptions():
    """Accepted research-stage assumptions (user-confirmed 2026-10-10)."""
    rows = [
        ("NaOH : daf Sargassum", "1 kg/kg daf", "att.yaml reactor case naoh_kg_per_kg_daf"),
        ("Feedstock", "NLR preprint: fresh Sargassum (14.3 % solids; pressed 23.7 / 27.0 %)", "feedstock.yaml"),
        ("P1 / D0", "ATT-only: municipal-type screw press to 76.3 % moisture (juice to biostimulant), thermal drying to 50 % (wet basis); integrated: presscake from the biostimulant plant, no P1", "att.yaml feed_preparation"),
        ("D1 dissolution water", f"{_ATT['downstream']['dissolution_water_kg_per_kg_Na2CO3']} kg/kg Na2CO3 into D1",
         "workbook B18"),
        ("Liquor recycle", f"{_ATT['downstream']['whole_liquor_recycle_fraction']:.0%} whole-liquor; "
                           "NaOH recovery calculated", "att.yaml downstream"),
        ("Gas yields", "H2 70.52, CH4 0.70, CO 0.31, CO2 22.68 mmol/g daf (experimental team Excel)",
         "att.yaml reactor"),
        ("U2 checks", "NaOH capacity for CO2; electron, mass and energy balances of the identified products",
         "ATTReactor.balance_checks"),
        ("NaOH -> Na2CO3 in U2", "100 %", "workbook"),
        ("C1", f"{_ATT['downstream']['causticization_conversion']:.0%} conversion, Ca(OH)2 "
               f"{_ATT['downstream']['lime_equiv']} x stoich., 90 C", "workbook / att.yaml"),
        ("EC1", "single-effect, 90 C, NaOH/(NaOH+H2O) = 50 % after makeup", "att.yaml downstream"),
        ("F1 / F2 cake moisture", f"{_ATT['downstream']['f1_cake_moisture_wt_frac']:.0%} / "
                                  f"{_ATT['downstream']['f2_cake_moisture_wt_frac']:.0%}", "att.yaml downstream"),
        ("PSA", f"{_ATT['gas_treatment']['psa_h2_recovery']:.0%} H2 recovery; product 20 bar", "att.yaml gas_treatment"),
        ("Heat loss", "5 % of process heat (U2, C1, EC1; steam agent for D0, U3D)", "workbook"),
        ("Heat sources", "U2 direct natural gas (burner 0.90); LP steam from NG boiler (0.80)", "workbook / BioSTEAM"),
        ("Heat integration", "excluded from the baseline", "user decision"),
        ("CaCO3 cake", "coproduct, no credit", "user decision"),
        ("PSA off-gas", "collected and burned in the U2 burner (natural gas offset); no CH4 revenue", "user decision 2026-10-15"),
    ]
    return [dict(assumption=a, value=b, source=c) for a, b, c in rows]


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def check_att_inventory(sys, flows=None, utilities=None):
    """One-pass mass, element and energy-accounting checks."""
    flows = flows or get_att_external_flows(sys)
    totals = [r for r in flows if r["component"] == "TOTAL"]
    mass_in = sum(r["kg_per_h"] for r in totals if r["direction"] == "input")
    mass_out = sum(r["kg_per_h"] for r in totals if r["direction"] == "output")
    elements = {}
    for e in ("C", "H", "O", "N", "Na", "Ca"):
        a_in = sum(float(s.get_atomic_flow(e)) for s in sys.feeds)
        a_out = sum(float(s.get_atomic_flow(e)) for s in sys.products)
        elements[e] = (a_out - a_in) / max(a_in, 1e-30)
    hus = [hu for unit in sys.units for hu in unit.heat_utilities if hu.duty > 0.0]
    loss_ok = all(hu.duty >= hu.unit_duty - 1e-9 for hu in hus)
    utilities = utilities or get_att_purchased_utilities(sys)
    u = {r["item"]: r["per_kg_dry"] for r in utilities}
    return dict(
        mass_in_kgph=mass_in, mass_out_kgph=mass_out,
        mass_relative_error=(mass_out - mass_in) / mass_in,
        element_relative_error=elements,
        utility_heat_ge_process_heat=loss_ok,
        ng_fuel_ge_delivered_heat=u["U2 natural gas: fuel input (LHV)"]
        >= u["U2 natural gas: heat delivered incl. 5 % reactor loss"],
        ng_fuel_vs_biosteam_agent=u["U2 natural gas: fuel input (LHV)"]
        / u["U2 natural gas: BioSTEAM agent fuel (cross-check only)"] - 1.0,
    )


def compare_scale_invariance(sys_small, sys_large):
    """Relative differences of per-kg-dry flows and duties between two scales."""
    a, b = _dry_feed_kgph(sys_small), _dry_feed_kgph(sys_large)
    sa, sb = _streams(sys_small), _streams(sys_large)
    rows = []
    for ID, s in sa.items():
        x, y = s.F_mass / a, sb[ID].F_mass / b
        rows.append(dict(item=f"stream {ID}", small_scale=x, reference_scale=y,
                         relative_difference=(y - x) / x if x else 0.0))
    ua, ub = _units(sys_small), _units(sys_large)
    for ID, unit in ua.items():
        for kind, f in (("heat", lambda u: sum(hu.duty for hu in u.heat_utilities)),
                        ("power", lambda u: u.power_utility.rate)):
            x, y = f(unit) / a, f(ub[ID]) / b
            if abs(x) > 1e-12 or abs(y) > 1e-12:
                rows.append(dict(item=f"{ID} {kind}", small_scale=x, reference_scale=y,
                                 relative_difference=(y - x) / x if x else float("inf")))
    return rows



# ---------------------------------------------------------------------------
# Assumption register and export
# ---------------------------------------------------------------------------

# (level, area, assumption, basis, TEA/LCA influence)
ASSUMPTION_REGISTER = (
    ("1 essential", "U2 gas yield", "H2 70.52, CH4 0.70, CO 0.31, CO2 22.68 mmol/g daf specified; extra carbon "
     "leaves as CO2", "Experimental team Excel; closes the electron balance", "HIGH (H2 product and MSP)"),
    ("1 essential", "U2 chemistry", "100 % NaOH -> Na2CO3; oxygen balance sets the product water; N, S not tracked",
     "att.yaml reactor.material_balance", "MEDIUM (NaOH makeup, Na2CO3 load)"),
    ("1 essential", "NaOH loading", "1 kg NaOH/kg daf", "Experimental team Excel", "HIGH (recycle, EC1 duty)"),
    ("1 essential", "Feedstock", "NLR preprint composition (fresh and pressed Sargassum)", "feedstock.yaml",
     "HIGH (daf per kg dry)"),
    ("1 essential", "Feed preparation", "ATT-only: P1 municipal-type press to 76.3 % moisture, D0 to 50 % "
     "(DrumDryer, ideal heat balance); integrated: presscake, no P1", "User-confirmed process design",
     "HIGH (D0 ~6 MJ/kg dry)"),
    ("1 essential", "Recycle", "95 % whole-liquor recycle, 5 % purge; EC1 to 50 % NaOH/(NaOH+H2O) at 90 C",
     "Collaborator '95 % NaOH recycling' read as whole-liquor recycle", "HIGH (NaOH makeup, EC1 duty)"),
    ("1 essential", "C1", "85 % conversion, Ca(OH)2 1.1 x stoichiometric, 90 C", "att.yaml downstream",
     "HIGH (Ca(OH)2 is a leading GWP item)"),
    ("2 engineering", "Heat losses", "5 % of process heat for U2, C1, EC1, D0 (steam)", "Workbook 5 %", "LOW"),
    ("2 engineering", "Heat sources", "U2 direct natural gas (burner 0.90); steam from NG boiler (0.80)",
     "Collaborators (burner); BioSTEAM default (boiler)", "HIGH for LCA"),
    ("2 engineering", "Electricity EF", "0.449 kg CO2e/kWh (GREET 2022 US mix)",
     "BioSTEAM project value; location-dependent", "MEDIUM"),
    ("2 engineering", "Ca(OH)2 source", "Limestone baseline (0.91); steel slag scenario (0)", "Collaborators",
     "HIGH for LCA"),
    ("2 engineering", "PSA", "90 % H2 recovery, ideal selectivity, no power; product 20 bar",
     "att.yaml gas_treatment (provisional)", "MEDIUM (H2 product; capital missing)"),
    ("2 engineering", "Off-gas", "Collected 100 %, unpurified, burned in the U2 burner (natural gas offset up to U2's "
     "fuel demand; no burner, flue gas or capital); mainly CH4 with unrecovered H2, CO and CO2",
     "User decisions 2026-10-09/12/15", "MEDIUM (burner not modeled; planned fired heater)"),
    ("2 engineering", "CaCO3 cake", "Coproduct, no credit or burden", "User decision 2026-10-09",
     "MEDIUM (scenario later)"),
    ("2 engineering", "Filter cakes", "F1 30 %, F2 25 % moisture with entrained mother liquor", "Literature review",
     "MEDIUM (Na losses)"),
    ("2 engineering", "C1 enthalpy", "Infinite-dilution aqueous reference; concentrated-solution terms bounded",
     "-40 to +300 kJ/kg dry (<1.2 % of plant heat)", "LOW"),
    ("2 engineering", "EC1 dissolved Na2CO3 fraction", "5 % dissolved (Wu et al. 2020 near 50 wt% NaOH; single source)",
     "<10 kJ/kg dry effect", "LOW"),
    ("2 engineering", "Missing costs", "C1 tank; U2 vessel (Inconel, tau 1 h); EC1 evaporator/condenser/vacuum",
     "BioSTEAM correlations; att.yaml inventory.cost_estimates", "MEDIUM (U2 vessel uncertain)"),
    ("2 engineering", "Plant scale", "SaBRe common 15000 wet t/d, 330 d/yr", "feedstock.yaml, tea.yaml",
     "HIGH for TEA"),
    ("2 engineering", "Wastes", "Ash/char cake, purge, wastewater: disposal prices from tea.yaml; GWP factors missing",
     "tea.yaml price", "LOW-MEDIUM"),
    ("2 engineering", "Sargassum burden", "Zero upstream burden; collection/transport excluded",
     "Waste-biomass cut-off", "MEDIUM (decision)"),
    ("3 optional", "Heat integration", "Excluded from the baseline (separate scenario)", "User decision", "Scenario"),
    ("3 optional", "Dryer alternatives, EC1 multi-effect/MVR, lime kiln", "Not modeled", "Out of scope", "Scenario"),
)


def get_att_assumption_register():
    return [dict(level=a, area=b, assumption=c, basis=d, influence=e) for a, b, c, d, e in ASSUMPTION_REGISTER]


def _annualize(rows, dry_t_per_year, key="kg_per_kg_dry", out="t_per_year"):
    for r in rows:
        v = r.get(key)
        if isinstance(v, float) and v == v:
            r[out] = v * dry_t_per_year
    return rows


def _attach_small_scale(rows, small_rows, keys, value, out):
    lookup = {tuple(r[k] for k in keys): r[value] for r in small_rows}
    for r in rows:
        r[out] = lookup.get(tuple(r[k] for k in keys), float("nan"))
    return rows


def _simulate(sys, dry_feed_kgph):
    # Recycle tolerance as in test_att_unit_mass_audit, scaled with the feed.
    sys.set_tolerance(mol=1e-11 * dry_feed_kgph, rmol=1e-11, T=1e-5, rT=1e-5,
                      maxiter=200, method="fixedpoint")
    sys.simulate()
    return sys


def build_att_inventory_tables():
    """Simulate the 1 kg/h basis and the reference scale; return all tables."""
    from biorefineries.sabre.systems._att_system import create_att_system

    small = _simulate(create_att_system(dry_sargassum_kgph=1.0), 1.0)
    flows_s = get_att_external_flows(small)
    products_s = get_att_product_scenarios(small)
    chem_s = get_att_chemical_ledger(small)
    carbon_s = get_att_carbon_fate(small)
    energy_s = get_att_unit_energy(small)
    utilities_s = get_att_purchased_utilities(small)
    check_s = check_att_inventory(small, flows_s, utilities_s)
    h2_check = get_att_u2_balance_checks(small)

    scale = get_att_reference_scale()
    ref = _simulate(create_att_system(dry_sargassum_kgph=scale["dry_feed_kgph"]), scale["dry_feed_kgph"])
    estimates = get_att_cost_estimates(ref)
    flows = get_att_external_flows(ref)
    products = get_att_product_scenarios(ref)
    chem = get_att_chemical_ledger(ref)
    carbon = get_att_carbon_fate(ref)
    energy = get_att_unit_energy(ref)
    utilities = get_att_purchased_utilities(ref, estimates)
    lci = get_att_lci(flows, utilities, products)
    lci_slag = get_att_lci(flows, utilities, products, ca_source="CaOH2_steel_slag")
    check = check_att_inventory(ref, flows, utilities)
    dry_t = scale["dry_feed_t_per_year"]

    _attach_small_scale(flows, flows_s, ("stream", "component"), "kg_per_h", "kg_per_h_at_1kgph_sim")
    _attach_small_scale(products, products_s, ("closure", "item"), "kg_per_h_at_sim_basis",
                        "kg_per_h_at_1kgph_sim")
    _attach_small_scale(chem, chem_s, ("item",), "kg_per_h_at_sim_basis", "kg_per_h_at_1kgph_sim")
    _attach_small_scale(carbon, carbon_s, ("stream",), "kg_C_per_h_at_sim_basis", "kg_C_per_h_at_1kgph_sim")
    _attach_small_scale(energy, energy_s, ("unit", "kind", "agent"), "utility_duty_MJ_per_kg_dry",
                        "utility_duty_MJ_at_1kgph_sim")
    _attach_small_scale(energy, energy_s, ("unit", "kind", "agent"), "electricity_kWh_per_kg_dry",
                        "electricity_kWh_at_1kgph_sim")
    _attach_small_scale(utilities, utilities_s, ("item",), "per_kg_dry", "at_1kgph_sim")
    for rows in (flows, products, chem):
        for r in rows:
            if "kg_per_h_at_sim_basis" in r:
                r["kg_per_h_at_reference_scale"] = r.pop("kg_per_h_at_sim_basis")
            elif "kg_per_h" in r:
                r["kg_per_h_at_reference_scale"] = r.pop("kg_per_h")
        _annualize(rows, dry_t)
    for r in carbon:
        r["kg_C_per_h_at_reference_scale"] = r.pop("kg_C_per_h_at_sim_basis")
    _annualize(carbon, dry_t, "kg_C_per_kg_dry", "t_C_per_year")
    for r in utilities:
        r["per_year_at_reference_scale"] = r["per_kg_dry"] * dry_t * 1000.0

    checks = [dict(basis="1 kg/h simulation", check=k, value=str(v)) for k, v in check_s.items()]
    checks += [dict(basis="reference scale", check=k, value=str(v)) for k, v in check.items()]
    basis = [dict(item=k, value=v) for k, v in scale.items()]
    sanity = ([dict(r, basis="1 kg/h simulation") for r in get_att_stream_sanity_check(small)]
              + [dict(r, basis="reference scale") for r in get_att_stream_sanity_check(ref)])
    return {
        "00_basis": basis,
        "00b_final_assumptions": get_att_final_assumptions(),
        "01_external_flows": flows,
        "02_gas_products": products,
        "03_u2_balance_checks": h2_check,
        "04_chemical_ledger": chem,
        "05_carbon_fate": carbon,
        "06_unit_energy": energy,
        "07_purchased_utilities": utilities,
        "08_lci_gwp_limestone_lime": lci,
        "09_lci_gwp_steel_slag_lime": lci_slag,
        "10_equipment_inventory": get_att_equipment_inventory(ref, estimates),
        "11_tea_inputs": get_att_tea_inputs(),
        "12_checks": checks,
        "13_scale_invariance": compare_scale_invariance(small, ref),
        "14_assumption_register": get_att_assumption_register(),
        "15_unit_streams_per_kg_dry": get_att_unit_streams(small),
        "16_unit_mass_element_balance": get_att_unit_balances(ref),
        "17_stream_sanity_check": sanity,
        "18_water_balance": get_att_water_balance(ref),
        "19_sodium_calcium_ledger": get_att_sodium_calcium_ledger(ref),
        "20_gas_accounting": get_att_gas_accounting(ref),
        "21_unit_energy_balance": get_att_unit_energy_balance(ref),
        "22_utility_consistency": get_att_utility_consistency_check(ref),
    }


def export_att_inventory(out_dir=None, tables=None):
    """Write each table as CSV and all tables to one Excel workbook (default att_outputs/full_scale/mass_energy)."""
    import os
    import pandas as pd
    from biorefineries.sabre.analyses.att.paths import output_dir

    out_dir = os.fspath(out_dir or output_dir("mass_energy"))
    tables = tables or build_att_inventory_tables()
    os.makedirs(out_dir, exist_ok=True)
    with pd.ExcelWriter(os.path.join(out_dir, "att_inventory.xlsx"), engine="openpyxl") as writer:
        for name, rows in tables.items():
            df = pd.DataFrame(rows)
            df.to_csv(os.path.join(out_dir, f"{name}.csv"), index=False)
            df.to_excel(writer, sheet_name=name[:31], index=False)
    return tables
