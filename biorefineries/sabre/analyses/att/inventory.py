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

from biorefineries.sabre.analyses.att.thermodynamics import get_att_u2_gas_basis
from biorefineries.sabre.utils import (
    OPERATING_DAYS_PER_YEAR, OPERATING_HOURS_PER_YEAR, get_scale_feed_kgph, load_assumptions,
)

__all__ = (
    "get_att_reference_scale",
    "get_att_external_flows",
    "get_att_h2_yield_basis_check",
    "get_att_product_scenarios",
    "get_att_chemical_ledger",
    "get_att_carbon_fate",
    "get_att_unit_energy",
    "get_att_cost_estimates",
    "get_att_purchased_utilities",
    "get_att_lci",
    "get_att_equipment_inventory",
    "get_att_tea_inputs",
    "get_att_u2_closure_comparison",
    "get_att_experimental_gas_yield_scenario",
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


def get_att_reference_scale():
    """SaBRe common plant scale (project-wide assumption)."""
    feed_type = _ATT["feed_preparation"]["feedstock_type"]
    moisture = float(_FEEDSTOCK["feedstock_type"][feed_type]["moisture_frac"])
    wet_kgph = get_scale_feed_kgph(_FEEDSTOCK)
    return dict(
        wet_feed_t_per_day=float(_FEEDSTOCK["scale"]["wet_feed_ton_per_day"]),
        wet_feed_kgph=wet_kgph,
        moisture_frac=moisture,
        dry_feed_kgph=wet_kgph * (1.0 - moisture),
        dry_feed_t_per_day=wet_kgph * (1.0 - moisture) * 24.0 / 1000.0,
        operating_days_per_year=float(OPERATING_DAYS_PER_YEAR),
        operating_hours_per_year=float(OPERATING_HOURS_PER_YEAR),
        dry_feed_t_per_year=wet_kgph * (1.0 - moisture) * OPERATING_HOURS_PER_YEAR / 1000.0,
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


def _max_ch4_with_measured_h2(U2):
    """Largest CH4 compatible with the measured H2 (char = 0) [mmol/g daf]."""
    feed = U2.ins[0]
    residue = U2.outs[1]
    daf = float(U2._daf_sargassum_kgph)
    char = residue.chemicals[U2.char_ID].atoms
    h2 = float(U2.reported_gas_yield_mmol_per_g_daf["H2"]) * daf / 1000.0
    target = []
    for e in ("C", "H", "O"):
        fixed = float(residue.get_atomic_flow(e)) - float(residue.imol[U2.char_ID]) * char.get(e, 0.0)
        target.append(float(feed.get_atomic_flow(e)) - fixed - (2.0 * h2 if e == "H" else 0.0))
    # Unknowns: CH4, CO2, H2O.
    ch4, co2, water = np.linalg.solve(np.array([[1, 1, 0], [4, 0, 2], [0, 2, 1]], float), target)
    return ch4 * 1000.0 / daf, co2 * 1000.0 / daf


def get_att_h2_yield_basis_check(sys):
    """Targeted check of the reported gas yields against the feed electrons."""
    U2 = _units(sys)["U2"]
    daf = float(U2._daf_sargassum_kgph)
    dry = float(U2._dry_sargassum_kgph)
    redox = U2._redox_balance_kmol_e_per_h
    feed_e = redox["feed_organics"] / daf * 1e3  # mmol e-/g daf
    measured = {k: float(v) for k, v in U2.reported_gas_yield_mmol_per_g_daf.items()}
    gas_e = sum(_GAS_ELECTRONS[k] * y for k, y in measured.items())
    ratio = gas_e / feed_e
    hhv_range = _ATT["reactor"]["energy_basis"]["sensitivity_feed_HHV_MJ_per_kg_daf"]["secondary_literature"]
    ch4_max, co2_at_ch4_max = _max_ch4_with_measured_h2(U2)
    rows = [
        ("Source of reported yields", float("nan"), "",
         "ATT Inputs and Assumptions_261005.xlsx, sheet 'Experimental results', Ni-CatATT row: H2, CH4, CO, "
         "Gas 4 and CO2 in one table (hard-coded values, no formulas or notes); 500 C, 1 h, N2 carrier, "
         "steam 3.6 g; char, liquids and carbonate not reported"),
        ("Available electrons in feed organics (model composition)", feed_e, "mmol e-/g daf", ""),
        ("Available electrons in reported gases", gas_e, "mmol e-/g daf",
         "H2 x2, CH4 x8, CO x2, CO2 x0; water and NaOH are redox-neutral"),
        ("  of which H2", 2 * measured["H2"], "mmol e-/g daf", ""),
        ("  of which CH4", 8 * measured["CH4"], "mmol e-/g daf", ""),
        ("Reported gases / feed electrons", ratio, "-", "> 1: the reported gases cannot all be kept"),
        ("Measured H2 alone / feed electrons", 2 * measured["H2"] / feed_e, "-", "< 1: H2 alone is feasible"),
        ("Max CH4 compatible with measured H2 (char = 0)", ch4_max, "mmol/g daf",
         f"vs reported {measured['CH4']:.2f}; requires CO2 {co2_at_ch4_max:.2f} mmol/g daf"),
        ("Feed HHV implied by all reported gases (Thornton)", gas_e * _THORNTON_kJ_PER_MOL_E / 1e3, "MJ/kg daf",
         f"literature range {hhv_range[0]}-{hhv_range[1]} MJ/kg daf"),
        ("Ash fraction needed if yields were normalized to a too-small daf mass", 1 - daf / dry / ratio,
         "kg/kg dry", f"database {1 - daf / dry:.3f}, workbook 0.172 (both far lower)"),
        ("Model closure", float("nan"), "", U2.gas_closure_method),
    ]
    model = U2._model_gas_yield_mmol_per_g_daf
    for k in _MW:
        rows.append((f"  model {k}", model.get(k, 0.0), "mmol/g daf",
                     "measured" if (k == "H2" and U2.gas_closure_method == "h2_priority") else
                     ("closure product (unmeasured)" if k == U2.closure_gas_ID
                      and U2.gas_closure_method == "h2_priority" else "")))
    rows = [dict(item=a, value=b, unit=c, note=d) for a, b, c, d in rows]
    rows.append(dict(
        item="Conclusion", value=float("nan"), unit="",
        note=("The four measured gases together exceed the feed's available electrons (1.38x), so they cannot all "
              "be reproduced in a conserving model. Baseline: all four scaled by one factor s (ratios preserved); "
              "h2_priority keeps H2 only; experimental_fixed keeps all four with an open O balance. Ash basis, "
              "dry/daf or wet-mass normalization do not explain the excess. Documented limitation."),
    ))
    return rows


def get_att_product_scenarios(sys):
    """Reported (workbook) vs model gas yields, H2 product and off-gas."""
    basis = get_att_u2_gas_basis(sys)
    U2 = _units(sys)["U2"]
    daf = basis["daf_kgph"]
    dry = _dry_feed_kgph(sys)
    streams = _streams(sys)
    U2_gas = U2.outs[0]
    tail = streams["u3_tail_gas"]
    measured = basis["measured_yield_mmol_per_g_daf"]
    model = basis["model_yield_mmol_per_g_daf"]
    method = U2.gas_closure_method
    rows = []
    for k in _MW:
        if method == "h2_priority":
            status = ("measured" if k == "H2" else
                      "closure product (unmeasured)" if k == U2.closure_gas_ID else "not imposed (set to 0)")
        else:
            status = "measured x s (reconciled)"
        rows.append(dict(closure=method, item=f"{k} in U2 gas", reported_mmol_per_g_daf=measured[k],
                         model_mmol_per_g_daf=model.get(k, 0.0),
                         kg_per_h_at_sim_basis=float(U2_gas.imass[k]),
                         kg_per_kg_dry=float(U2_gas.imass[k]) / dry, status=status))
    h2 = float(streams["h2_product"].imass["H2"])
    rows.append(dict(closure=method, item="H2 product (after PSA)", kg_per_h_at_sim_basis=h2,
                     kg_per_kg_dry=h2 / dry, status=f"PSA recovery {basis['psa_h2_recovery']}"))
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
                          ("press_liquid", "Wastewater: press liquid"),
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


def _closure_metrics(sys):
    U2 = _units(sys)["U2"]
    dry = _dry_feed_kgph(sys)
    s = _streams(sys)
    estimates = get_att_cost_estimates(sys)
    flows = get_att_external_flows(sys)
    utilities = get_att_purchased_utilities(sys, estimates)
    lci = get_att_lci(flows, utilities, get_att_product_scenarios(sys))
    u = {r["item"]: r["per_kg_dry"] for r in utilities}
    y = U2._model_gas_yield_mmol_per_g_daf
    feed = U2.ins[0]
    gas, residue = U2.outs
    element_error = max(
        abs(float(gas.get_atomic_flow(e) + residue.get_atomic_flow(e) - feed.get_atomic_flow(e)))
        / float(feed.get_atomic_flow(e)) for e in ("C", "H", "O", "N", "Na")
    )
    redox = U2._redox_balance_kmol_e_per_h
    gwp = next(r for r in lci if r["flow"].startswith("TOTAL"))["GWP_kgCO2e_per_kg_dry"]
    gwp_h2 = next(r for r in lci if r["flow"].startswith("GWP per kg H2"))["GWP_kgCO2e_per_kg_dry"]
    return (
        ("H2 yield in U2 gas (model)", y["H2"], "mmol/g daf"),
        ("H2 at U2 outlet", float(gas.imass["H2"]) / dry, "kg/kg dry"),
        ("H2 product (PSA 90 %)", float(s["h2_product"].imass["H2"]) / dry, "kg/kg dry"),
        ("CH4 in U2 gas (model; reported 8.769 kept in 02c)", y["CH4"], "mmol/g daf"),
        ("CO in U2 gas (model; reported 0.165 kept in 02c)", y["CO"], "mmol/g daf"),
        ("CO2 in U2 gas (model)", y["CO2"], "mmol/g daf"),
        ("Gas scale factor s", float(U2._gas_scale_factor), "-"),
        ("Char incl. CharN/CharS", U2._char_kgph / dry, "kg/kg dry"),
        ("Char C / feed organic C", U2._char_carbon_fraction_of_feed_organic_C, "-"),
        ("U2 net water formation (negative = consumed)", U2._net_water_formation_kmolph * 18.01528 / dry,
         "kg/kg dry"),
        ("U3 condensate", float(s["u3_condensate"].F_mass) / dry, "kg/kg dry"),
        ("F1 ash/char cake", float(s["ash_residue_cake"].F_mass) / dry, "kg/kg dry"),
        ("PSA off-gas", float(s["u3_tail_gas"].F_mass) / dry, "kg/kg dry"),
        ("U2 max relative element error (C, H, O, N, Na)", element_error, "-"),
        ("U2 electron balance error (model gases + char vs feed)",
         (redox["model_gases"] + redox["char"] - redox["feed_organics"]) / redox["feed_organics"], "-"),
        ("U2 process heat", U2._heat_duty_kJph / 1e3 / dry, "MJ/kg dry"),
        ("U2 heat incl. 5 % loss", U2._utility_heat_duty_kJph / 1e3 / dry, "MJ/kg dry"),
        ("U2 natural gas fuel (LHV)", u["U2 natural gas: fuel input (LHV)"], "MJ/kg dry"),
        ("LP steam heat incl. loss", u["LP steam: utility heat incl. 5 % loss"], "MJ/kg dry"),
        ("Boiler natural gas for steam (LHV)", u["LP steam: boiler natural gas (LHV)"], "MJ/kg dry"),
        ("Total natural gas (U2 + boiler)", u["U2 natural gas: fuel input (LHV)"]
         + u["LP steam: boiler natural gas (LHV)"], "MJ/kg dry"),
        ("Cooling water heat removed", u["Cooling water: heat removed"], "MJ/kg dry"),
        ("Electricity total", u["Electricity: total"], "kWh/kg dry"),
        ("NaOH makeup", float(s["fresh_naoh_solid"].F_mass) / dry, "kg/kg dry"),
        ("Ca(OH)2", float(s["lime"].F_mass) / dry, "kg/kg dry"),
        ("GWP (limestone Ca(OH)2, missing factors excluded)", gwp, "kg CO2e/kg dry"),
        ("GWP per kg H2", gwp_h2, "kg CO2e/kg H2"),
    )


def get_att_experimental_gas_yield_scenario(sys):
    """
    EXPERIMENTAL GAS-YIELD SCENARIO (product accounting only).

    All reported Ni-CatATT yields (H2, CH4, CO, CO2) times the daf feed, with
    the PSA recovery applied to H2 and the other gases to the off-gas. It is
    NOT element- or redox-balanced with the SaBRe feed and has no energy
    balance; mass, energy and utilities come only from the closed baseline.
    Use: product accounting and CH4/CO coproduct-recovery or emission
    sensitivities, never combined with the baseline closure CO2.
    """
    U2 = _units(sys)["U2"]
    daf = float(U2._daf_sargassum_kgph)
    dry = _dry_feed_kgph(sys)
    psa = float(_ATT["gas_treatment"]["psa_h2_recovery"])
    reported = {k: float(v) for k, v in U2.reported_gas_yield_mmol_per_g_daf.items()}
    model = U2._model_gas_yield_mmol_per_g_daf
    label = "EXPERIMENTAL (reported); NOT element/redox balanced; product accounting only"
    rows = []
    for k in _MW:
        U2_kg = reported[k] * daf * _MW[k] / 1000.0 / dry
        product = U2_kg * psa if k == "H2" else 0.0
        rows.append(dict(item=k, reported_mmol_per_g_daf=reported[k], U2_outlet_kg_per_kg_dry=U2_kg,
                         to_H2_product_kg_per_kg_dry=product, to_offgas_kg_per_kg_dry=U2_kg - product,
                         baseline_model_mmol_per_g_daf=model.get(k, 0.0), status=label))
    feed_e = U2._redox_balance_kmol_e_per_h["feed_organics"] / daf * 1e3
    gas_e = sum(_GAS_ELECTRONS[k] * y for k, y in reported.items())
    rows.append(dict(item="Available electrons: reported gases / feed organics",
                     reported_mmol_per_g_daf=gas_e, U2_outlet_kg_per_kg_dry=float("nan"),
                     to_H2_product_kg_per_kg_dry=float("nan"), to_offgas_kg_per_kg_dry=float("nan"),
                     baseline_model_mmol_per_g_daf=feed_e,
                     status=f"deficit {gas_e - feed_e:.1f} mmol e-/g daf ({gas_e / feed_e - 1:.0%}); "
                            "no energy balance exists for this scenario"))
    return rows


def get_att_u2_closure_comparison(systems):
    """Side-by-side key results for simulated systems {label: sys}."""
    metrics = {label: _closure_metrics(sys) for label, sys in systems.items()}
    first = next(iter(metrics.values()))
    rows = []
    for i, (name, _, unit) in enumerate(first):
        row = dict(metric=name, unit=unit)
        for label, values in metrics.items():
            row[label] = values[i][1]
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Final verification tables
# ---------------------------------------------------------------------------

_ELEMENTS = ("C", "H", "O", "N", "S", "Na", "Ca")


def _component_basis(U2):
    """Origin of the U2 outlet components (measured vs model closure)."""
    closure = U2.closure_gas_ID
    basis = {
        ("att_gas", "H2"): "EXPERIMENTAL: measured H2 yield (Ni-CatATT)",
        ("att_gas", "Water"): "MODEL CLOSURE: C/H/O balance (product water)",
        ("att_residue", "Char"): "MODEL CLOSURE: C/H/O balance (char CH0.5O0.1)",
        ("att_residue", "CharN"): "MODEL: feed N retained in char",
        ("att_residue", "CharS"): "MODEL: feed S retained in char",
        ("att_residue", "Na2CO3"): "SPECIFIED: 100 % NaOH -> Na2CO3 (workbook)",
        ("att_residue", "Ash"): "SPECIFIED: inert ash (SaBRe database)",
    }
    if U2.gas_closure_method == "h2_priority":
        basis[("att_gas", closure)] = "MODEL-ASSUMED CLOSURE PRODUCT (not measured)"
    else:
        for ID in U2._measured_gas_kmolph:
            basis[("att_gas", ID)] = "MODEL: measured yield x s (reconciled)"
    return basis


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
        dict(group="internal", item="P1 mechanical dewatering (press liquid)",
             kg_per_kg_dry=float(s["press_liquid"].imass["Water"]) / dry),
        dict(group="internal", item="D0 thermal drying (evaporated)",
             kg_per_kg_dry=float(s["dryer_exhaust"].imass["Water"] - s["dryer_air"].imass["Water"]) / dry),
        dict(group="internal", item="U3 condensation (U3C + U3D)",
             kg_per_kg_dry=float(s["u3_condensate"].imass["Water"] + s["u3_dryer_removed_water"].imass["Water"]) / dry),
        dict(group="internal", item="EC1 evaporation (= condensate)",
             kg_per_kg_dry=float(s["ec1_condensate"].imass["Water"]) / dry),
        dict(group="internal", item="Wastewater total (press liquid + condensates)",
             kg_per_kg_dry=sum(float(s[k].imass["Water"]) for k in
                               ("press_liquid", "u3_condensate", "u3_dryer_removed_water", "ec1_condensate")) / dry),
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
        ("NaOH entering U2 (gross requirement, 2 kg/kg daf)", gross),
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


_MODEL_LABEL = "MODEL: measured x s (engineering prediction preserving the measured ratios; NOT a measurement)"


def get_att_gas_accounting(sys):
    """Reported vs model gas yields, labels, destinations and the CO2 path."""
    U2 = _units(sys)["U2"]
    daf = float(U2._daf_sargassum_kgph)
    dry = _dry_feed_kgph(sys)
    reported = {k: float(v) for k, v in U2.reported_gas_yield_mmol_per_g_daf.items()}
    model = U2._model_gas_yield_mmol_per_g_daf
    h2_priority = U2.gas_closure_method == "h2_priority"
    labels = {
        "H2": ("EXPERIMENTAL (measured); kept exactly" if h2_priority else _MODEL_LABEL,
               "90 % to h2_product (PSA), 10 % to u3_tail_gas", ""),
        "CH4": ("MODEL SIMPLIFICATION: set to 0 for element/redox feasibility; NOT an experimental "
                "observation. The reported yield cannot coexist with the measured H2 under the SaBRe "
                "feed composition (max ~2.4 mmol/g daf even with no char)" if h2_priority else _MODEL_LABEL,
                "u3_tail_gas",
                "TEA: no CH4 revenue in the baseline; CH4 recovery is a later sensitivity. LCA: CH4 "
                "emission/fugitive loss is a later sensitivity using the reported yield."),
        "CO": ("Not imposed (0); reported value kept" if h2_priority else _MODEL_LABEL, "u3_tail_gas", ""),
        "CO2": ("MODEL-ASSUMED CLOSURE PRODUCT (not measured): carbon beyond the NaOH capacity leaves "
                "fully oxidized. Reported value is gas-phase CO2 after in-situ NaOH capture (NaOH mixed "
                "with the sample in the reactor; inferred from the set-up, not stated in the workbook)"
                if h2_priority else _MODEL_LABEL, "u3_tail_gas", "Biogenic CO2."),
    }
    rows = []
    for k in _MW:
        label, destination, flag = labels[k]
        rows.append(dict(species=k, reported_mmol_per_g_daf=reported[k],
                         reported_kg_per_kg_dry=reported[k] * daf * _MW[k] / 1000.0 / dry,
                         model_mmol_per_g_daf=model.get(k, 0.0),
                         model_kg_per_kg_dry=float(U2.outs[0].imass[k]) / dry,
                         basis=label, destination=destination, TEA_LCA_flag=flag))
    ignored = U2.ignored_reported_gas_yields
    for k, y in ignored.items():
        rows.append(dict(species=k, reported_mmol_per_g_daf=float(y), reported_kg_per_kg_dry=float("nan"),
                         model_mmol_per_g_daf=0.0, model_kg_per_kg_dry=0.0,
                         basis="Ignored: CO on the second GC column (collaborator), negligible",
                         destination="", TEA_LCA_flag=""))
    # Path of the gas species through U3 (no unit absorbs CO2).
    for ID in ("att_gas", "u3_cooled_multiphase", "u3_wet_gas", "u3_dry_gas", "u3_raw_h2_product",
               "u3_tail_gas", "h2_product"):
        stream = next(s for unit in sys.units for s in (*unit.ins, *unit.outs) if s.ID == ID)
        rows.append(dict(species=f"path: {ID}", reported_mmol_per_g_daf=float("nan"),
                         reported_kg_per_kg_dry=float("nan"), model_mmol_per_g_daf=float("nan"),
                         model_kg_per_kg_dry=float("nan"),
                         basis=", ".join(f"{k} {float(stream.imass[k]) / dry:.5f}" for k in _MW),
                         destination=f"{stream.source} -> {stream.sink}", TEA_LCA_flag="kg/kg dry"))
    return rows


def _documented_enthalpy_residual(unit):
    """(value or None, explanation) for Hnet(out) - Hnet(in) - process heat."""
    kind = type(unit).__name__
    if unit.ID == "U2":
        return (unit._feed_Hf_HHV_correction_kJph + unit._aqueous_feed_correction_kJph,
                "Feed Hf re-referenced to the HHV + NaOH(aq) electrolyte correction of the feed")
    if unit.ID == "C1":
        return (-unit._aqueous_reference_correction_kJph,
                "Infinite-dilution aqueous-ion reference for NaOH/Na2CO3 (native Hf replaced)")
    if unit.ID == "EC1":
        return (None, "Duty from the Olsson NaOH(aq) enthalpy (latent + concentration + crystallization); "
                      "native stream enthalpy treats NaOH as molten")
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
        ("U2 gas closure method", u["U2"].gas_closure_method,
         _ATT["reactor"]["material_balance"]["gas_closure_method"]),
        ("U2 model H2 = measured x s (or measured) [mmol/g daf]", u["U2"]._model_gas_yield_mmol_per_g_daf["H2"],
         float(u["U2"].reported_gas_yield_mmol_per_g_daf["H2"])
         * (u["U2"]._gas_scale_factor if u["U2"].gas_closure_method == "uniform_redox_scaling" else 1.0)),
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
        ("NaOH : daf Sargassum", "2 kg/kg daf", "att.yaml reactor case naoh_kg_per_kg_daf"),
        ("Feedstock", "SaBRe pelagic: ash 34.53 % dry, moisture 86.73 %", "feedstock.yaml"),
        ("P1 / D0", "dewatering to 75 % moisture, thermal drying to 50 % (wet basis)", "att.yaml feed_preparation"),
        ("D1 dissolution water", f"{_ATT['downstream']['dissolution_water_kg_per_kg_Na2CO3']} kg/kg Na2CO3 into D1",
         "workbook B18"),
        ("Liquor recycle", f"{_ATT['downstream']['whole_liquor_recycle_fraction']:.0%} whole-liquor; "
                           "NaOH recovery calculated", "att.yaml downstream"),
        ("Measured gas yields", "H2 66.728, CH4 8.769, CO 0.165, CO2 0.187 mmol/g daf (never modified)",
         "workbook Ni-CatATT"),
        ("U2 closure", _INV["u2_closure"]["baseline"], "att.yaml reactor.material_balance"),
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
        ("PSA off-gas", "collected; no CH4 revenue; CH4 recovery/emission = later sensitivity", "user decision"),
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
    ("1 essential", "U2 gas yield", "All four measured gases x s (s = 0.5998, ratios preserved); alternatives "
     "h2_priority and experimental_fixed", "Reported gases exceed feed electrons 1.38x; s unique by C/H/O + electrons",
     "HIGH (H2 product and MSP scale with s)"),
    ("1 essential", "U2 chemistry", "100 % NaOH -> Na2CO3; unconverted C as char CH0.5O0.1; N, S retained in char",
     "Element/redox closure; att.yaml reactor.material_balance", "MEDIUM (NaOH makeup, Na2CO3 load)"),
    ("1 essential", "NaOH loading", "2 kg NaOH/kg daf", "Advisor-confirmed experimental basis", "HIGH (recycle, EC1 duty)"),
    ("1 essential", "Feedstock", "Database ash 34.53 % dry, moisture 86.73 %", "User decision; feedstock.yaml",
     "HIGH (daf per kg dry: 0.655 vs 0.828 workbook)"),
    ("1 essential", "Feed preparation", "P1 to 75 % moisture, D0 to 50 % (DrumDryer, ideal heat balance)",
     "User-confirmed process design", "HIGH (D0 ~6 MJ/kg dry)"),
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
    ("2 engineering", "Off-gas", "Collected 100 %, unpurified, no credit; baseline off-gas is mainly CH4 with "
     "unrecovered H2, CO and CO2", "User decisions 2026-10-09/12", "MEDIUM (CH4 value / emission sensitivities)"),
    ("2 engineering", "CH4", "Model CH4 = s x reported (5.26 mmol/g daf); reported 8.769 kept as reference",
     "Ratio-preserving closure", "FLAG: TEA CH4-recovery and LCA CH4-emission (if vented) sensitivities"),
    ("2 engineering", "CaCO3 cake", "Coproduct, no credit or burden", "User decision 2026-10-09",
     "MEDIUM (scenario later)"),
    ("2 engineering", "Filter cakes", "F1 30 %, F2 25 % moisture with entrained mother liquor", "Literature review",
     "MEDIUM (Na losses)"),
    ("2 engineering", "C1 enthalpy", "Infinite-dilution aqueous reference; concentrated-solution terms bounded",
     "-40 to +300 kJ/kg dry (<1.2 % of plant heat)", "LOW"),
    ("2 engineering", "EC1 Na2CO3 solubility", "Wu et al. 2020 at 90 C; anhydrous branch single-source",
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
    h2_check = get_att_h2_yield_basis_check(small)

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

    comparison_method = _ATT["reactor"]["material_balance"]["comparison_gas_closure_method"]
    comparison = _simulate(create_att_system(dry_sargassum_kgph=scale["dry_feed_kgph"],
                                             u2_gas_closure=comparison_method), scale["dry_feed_kgph"])
    closure_comparison = get_att_u2_closure_comparison({
        f"{_units(ref)['U2'].gas_closure_method} (baseline)": ref,
        f"{comparison_method} (comparison)": comparison,
    })

    checks = [dict(basis="1 kg/h simulation", check=k, value=str(v)) for k, v in check_s.items()]
    checks += [dict(basis="reference scale", check=k, value=str(v)) for k, v in check.items()]
    basis = [dict(item=k, value=v) for k, v in scale.items()]
    basis += [dict(item=f"U2 closure: {k}", value=v) for k, v in _INV["u2_closure"].items()]
    sanity = ([dict(r, basis="1 kg/h simulation") for r in get_att_stream_sanity_check(small)]
              + [dict(r, basis="reference scale") for r in get_att_stream_sanity_check(ref)])
    return {
        "00_basis": basis,
        "00b_final_assumptions": get_att_final_assumptions(),
        "01_external_flows": flows,
        "02_gas_products": products,
        "02b_u2_closure_comparison": closure_comparison,
        "02c_experimental_gas_yield_scenario": get_att_experimental_gas_yield_scenario(ref),
        "03_h2_yield_basis_check": h2_check,
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
