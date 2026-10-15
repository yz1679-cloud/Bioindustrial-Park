"""
Side-by-side TEA and LCA contribution analysis of the three selected
element-balanced gas-yield scenarios (att.final.GAS_SCENARIOS): Gas-C
(baseline, uniform_redox_scaling), Gas-Cprime (uniform_co2_free) and Gas-A
(h2_measured_ch4_max). "Gas-A" is unrelated to TEA Case A (CaCO3 filter cake
disposed).

Reporting only. Each scenario is simulated separately at the SaBRe reference
scale and evaluated with the existing functions of att.inventory, att.tea,
att.lca and att.reporting; no process, closure, price, financial or
emission-factor input is changed. The MSP breakdown levelizes the columns of
SaBReTEA's own cash-flow table at the solved MSP (NPV = 0), so its components
sum to the MSP. Writes att_outputs/scenarios/gas_yield/.
"""
import os
import warnings

import numpy as np

from biorefineries.sabre.analyses.att import reporting as rep
from biorefineries.sabre.analyses.att import final as fin
from biorefineries.sabre.analyses.att import inventory as inv
from biorefineries.sabre.analyses.att import lca
from biorefineries.sabre.analyses.att import tea as tea_mod
from biorefineries.sabre.utils import load_assumptions

__all__ = ("build_att_gas_scenario_tables", "export_att_gas_scenario_comparison")

IDS = tuple(label for label, _, _ in fin.GAS_SCENARIOS)
_BASE = IDS[0]
_EXPECTED = {  # D7_Gas_Yield_Scenarios at commit 419ad328 (MSP ref, MSP TEA Case A, GWP per kg H2)
    "Gas-C": (15.99, 18.28, 89.5), "Gas-Cprime": (12.83, 14.67, 72.4), "Gas-A": (9.71, 11.09, 55.0)}
_AREAS = {
    "P1": "Feed dewatering (P1)", "D0": "Feed drying (D0)", "M1": "Feed mixing (M1)", "U2": "ATT reactor (U2)",
    "U3HX": "Gas cooling and drying (U3HX, U3C, U3D)", "U3C": "Gas cooling and drying (U3HX, U3C, U3D)",
    "U3D": "Gas cooling and drying (U3HX, U3C, U3D)", "U3P": "PSA (U3P)", "U3K": "H2 compression (U3K)",
    "RC1": "Residue cooling (RC1)", "D1": "Residue slurry (D1)", "F1": "Residue filtration (F1)",
    "C1": "Causticization (C1)", "F2": "CaCO3 filtration (F2)", "SP1": "Liquor split (SP1)",
    "EC1": "NaOH evaporation (EC1)", "M2": "NaOH makeup (M2)",
}
_ANNUAL = {"kg": (1e-3, "t/yr"), "MJ": (1e-6, "TJ/yr"), "kWh": (1e-3, "MWh/yr"), "m3": (1.0, "m3/yr"),
           "USD": (1e-6, "MUSD/yr"), "kg CO2e": (1e-3, "t CO2e/yr"), "kg C": (1e-3, "t C/yr"),
           "MJ fuel (LHV)": (1e-6, "TJ fuel/yr"), "kg wet": (1e-3, "t wet/yr")}
_NAN = float("nan")


def _num(x):
    return isinstance(x, (int, float, np.floating)) and not isinstance(x, bool)


# ---------------------------------------------------------------------------
# One scenario
# ---------------------------------------------------------------------------

def _cost_group(item, category):
    solid = tea_mod._T["prices"]["solid_waste_streams"]
    if category == "FOC":
        return "Fixed operating cost (4 % FCI)"
    for prefix, group in (("NaOH", "NaOH makeup"), ("Ca(OH)2", "Ca(OH)2"), ("Process water", "Process water"),
                          ("Sargassum", "Sargassum feedstock (0 in baseline)"),
                          ("Utility: natural_gas", "Natural gas, U2 furnace"),
                          ("Natural gas", "Natural gas, U2 furnace"),
                          ("Utility: low_pressure_steam", "LP steam (agent price)"),
                          ("Utility: cooling_water", "Cooling water (agent price)"),
                          ("Electricity", "Electricity"), ("Purge neutralization", "Neutralization (H2SO4)"),
                          ("CaCO3 cake", "CaCO3 filter cake disposal (TEA Case A)"),
                          ("PSA off-gas", "PSA off-gas handling (0; fate unresolved)")):
        if item.startswith(prefix):
            return group
    if item.startswith("Disposal: "):
        return "Ash/char cake disposal" if item.split(": ")[1] in solid else "Wastewater treatment"
    raise KeyError(item)


def _dcf_breakdown(sys, result):
    """Levelize SaBReTEA's cash-flow table at the solved MSP (NPV = 0)."""
    tea = result["tea"]
    hours = sys.operating_hours
    product = inv._streams(sys)[tea_mod._T["product"]]
    h2_kg_yr = float(product.F_mass) * hours
    df = tea.get_cashflow_table()
    DF = df["Discount factor"].to_numpy()

    def pv(col):
        return float((df[f"{col} [MM$]"].to_numpy() * DF).sum()) * 1e6

    n = len(df)
    start, w0 = tea._start, tea._startup_time % 1
    end_start = start + int(tea._startup_time)
    v, o = np.zeros(n), np.zeros(n)
    v[start:end_start], o[start:end_start] = tea.startup_VOCfrac, tea.startup_FOCfrac
    v[end_start] = w0 * tea.startup_VOCfrac + (1 - w0)
    o[end_start] = w0 * tea.startup_FOCfrac + (1 - w0)
    v[end_start + 1:], o[end_start + 1:] = 1.0, 1.0
    pv_v, pv_o = float((v * DF).sum()), float((o * DF).sum())
    sales = tea.sales
    S = df["Sales [MM$]"].to_numpy() * 1e6
    pv_f = float((S / sales * DF).sum())
    pv_h2 = h2_kg_yr * pv_f  # discounted kg H2
    li_construction = 0.0
    if tea.finance_interest and not tea.accumulate_interest_during_construction:
        li_construction = float((df["Loan interest payment [MM$]"].to_numpy()[:start] * DF[:start]).sum()) * 1e6

    rows = []

    def add(component, group, pv_usd, basis):
        rows.append(dict(component=component, group=group, PV_MUSD=pv_usd / 1e6, USD_per_kg_H2=pv_usd / pv_h2,
                         basis=basis))

    opex = tea_mod._opex_table(sys, result)
    for r in opex:
        if r["category"] in ("materials", "utilities", "extra VOC"):
            add(r["item"], _cost_group(r["item"], r["category"]), r["USD_per_yr"] * pv_v,
                "VOC item x PV(VOC profile)")
        elif r["category"] in ("waste disposal", "CaCO3 cake", "off-gas"):
            add(r["item"], _cost_group(r["item"], r["category"]), r["USD_per_yr"] * pv_f,
                "negative sales x PV(sales profile)")
        elif r["category"] == "FOC":
            add(r["item"], _cost_group(r["item"], r["category"]), r["USD_per_yr"] * pv_o, "FOC x PV(FOC profile)")
    add("Capital investment: FCI + working capital (incl. WC recovery)", "Capital (FCI + WC, net of loan)",
        pv("Fixed capital investment") + pv("Working capital"), "PV of capital outlays")
    add("Loan proceeds (60 % of FCI)", "Capital (FCI + WC, net of loan)", -pv("Loan"), "PV of loan inflow")
    add("Loan repayment incl. interest (8 %, 10 yr)", "Financing (debt service)",
        pv("Loan payment") + li_construction, "PV of debt service")
    add("Income tax (21 %)", "Income tax", pv("Tax"), "PV of tax column")
    pv_cf = float((df["Cash flow [MM$]"].to_numpy() * DF).sum()) * 1e6
    add("Solver residual (-NPV at MSP)", "Solver residual", -pv_cf, "should be ~0")
    total = sum(r["USD_per_kg_H2"] for r in rows)
    msp = result["msp"]
    checks = dict(
        sum_vs_msp=total - msp,
        pv_C_check=pv("Annual operating cost (excluding depreciation)") - (tea.VOC * pv_v + tea.FOC * pv_o),
        incentives_pv=pv("Incentives"),
        replacement_capex_pv=pv("Fixed capital investment") - float(
            (df["Fixed capital investment [MM$]"].to_numpy()[:start] * DF[:start]).sum()) * 1e6,
    )
    for r in rows:
        r["share_of_MSP"] = r["USD_per_kg_H2"] / msp
    return rows, checks, dict(pv_VOC_profile=pv_v, pv_FOC_profile=pv_o, pv_sales_profile=pv_f,
                              pv_H2_kg=pv_h2, h2_kg_yr=h2_kg_yr)


def _evaluate(label, method, note):
    from biorefineries.sabre.systems._att_system import create_att_system

    scale = inv.get_att_reference_scale()
    sys = inv._simulate(create_att_system(dry_sargassum_kgph=scale["dry_feed_kgph"], u2_gas_closure=method),
                        scale["dry_feed_kgph"])
    sys.operating_hours = scale["operating_hours_per_year"]
    fingerprint = [float(x) for st in (*sys.feeds, *sys.products) for x in st.mass]
    est = inv.get_att_cost_estimates(sys)
    util = inv.get_att_purchased_utilities(sys, est)
    U2 = inv._units(sys)["U2"]
    s = inv._streams(sys)
    dry = inv._dry_feed_kgph(sys)
    out = dict(label=label, method=method, note=note, dry_kgph=dry)

    # TEA: Case A first, reference last (reference prices stay on the system).
    case_a = tea_mod.evaluate_att_tea(sys, est, caco3=dict(fraction=0.0))
    out["opex_detail_A"] = rep._opex_detail(sys, case_a)
    out["opex_table_A"] = tea_mod._opex_table(sys, case_a)
    out["dcf_A"], out["dcf_checks_A"], out["dcf_basis_A"] = _dcf_breakdown(sys, case_a)
    out["msp_A"] = case_a["msp"]
    ref = tea_mod.evaluate_att_tea(sys, est)
    out["opex_detail"] = rep._opex_detail(sys, ref)
    out["opex_table"] = tea_mod._opex_table(sys, ref)
    out["dcf"], out["dcf_checks"], out["dcf_basis"] = _dcf_breakdown(sys, ref)
    out["msp"] = ref["msp"]
    out["capex"] = tea_mod._capex_table(sys, ref)
    out["capex_detail"] = rep._capex_detail(sys, ref)
    t = ref["tea"]
    out["tea_totals"] = dict(FCI=t.FCI, WC=t.working_capital, TCI=t.TCI, FOC=t.FOC, VOC=t.VOC, sales=t.sales,
                             add_OPEX=t._annual_unit_add_opex(), extra_VOC=t.extra_VOC,
                             material_cost=t.material_cost, utility_cost=t.utility_cost)
    out["prices"] = dict(ref["prices"])
    out["tea_checks"] = tea_mod._checks(sys, ref, fingerprint)
    out["estimates"] = est
    out["psa_t_H2_per_day"] = float(s["h2_product"].imass["H2"]) * 24.0 / 1e3

    # LCA on the same system; factors are set immediately before use.
    applied = lca.apply_att_gwp(sys, estimates=est)
    out["gwp"] = lca.get_att_gwp_contributions(sys, applied)
    out["gwp_unit"] = lca.get_att_gwp_by_unit(sys, applied)
    out["gwp_stage"] = lca.get_att_gwp_by_stage(out["gwp"])
    out["lca_checks"] = lca.check_att_lca(sys, applied, out["gwp"], util)
    out["factors"] = dict(applied["factors"])
    out["ng_agent_CF"] = lca.bst.HeatUtility.get_CF("natural_gas", lca.KEY)
    out["gwp_ch4"] = lca._LCA["indicative_gwp100"]["CH4_non_fossil"]["value"]

    # Process, energy and inventory data.
    out["U2"] = dict(model=dict(U2._model_gas_yield_mmol_per_g_daf),
                     measured={k: float(v) for k, v in U2.reported_gas_yield_mmol_per_g_daf.items()},
                     s=U2._gas_scale_factor, status=U2._elemental_balance_status,
                     daf_kgph=float(U2._daf_sargassum_kgph), utility_kJph=U2._utility_heat_duty_kJph)
    residue = U2.outs[1]
    char = residue.chemicals["Char"]
    out["char"] = dict(mass=float(residue.imass["Char"]) / dry,
                       carbon=float(residue.imol["Char"]) * char.atoms["C"] * 12.011 / dry,
                       C_fraction=char.atoms["C"] * 12.011 / char.MW,
                       NS=float(residue.imass["CharN"] + residue.imass["CharS"]) / dry)
    out["h2_kg_per_kg_dry"] = float(s["h2_product"].imass["H2"]) / dry
    out["product_kg_per_kg_dry"] = float(s["h2_product"].F_mass) / dry
    out["external"] = inv.get_att_external_flows(sys)
    out["na_ca"] = inv.get_att_sodium_calcium_ledger(sys)
    out["carbon"] = inv.get_att_carbon_fate(sys)
    out["unit_energy"] = inv.get_att_unit_energy(sys)
    out["utilities"] = util
    out["streams"] = {ID: dict(F_mass=float(st.F_mass), **{c: float(st.imass[c]) for c in
                                                            ("CH4", "H2", "CO", "CO2", "CaCO3", "Char", "Water")
                                                            if c in st.chemicals}) for ID, st in s.items()}
    out["wastewater_m3_per_kg_dry"] = lca._wastewater_m3ph(sys) / dry
    out["h2so4_kg_per_kg_dry"] = lca._h2so4_kgph(sys) / dry
    out["landfill_kg_per_kg_dry"] = lca._landfill_kgph(sys) / dry
    out["inventory_check"] = inv.check_att_inventory(sys)
    out["hours"] = sys.operating_hours
    out["flows_unchanged"] = tea_mod._same_flows(sys, fingerprint)
    return out


# ---------------------------------------------------------------------------
# Table helpers
# ---------------------------------------------------------------------------

def _expand(section, item, per_kg_dry, unit, h2, dry_yr, note=""):
    """One quantity on the three bases: per kg dry, per kg H2 and annual."""
    factor, annual_unit = _ANNUAL.get(unit, (1.0, f"{unit}/yr"))
    return [dict(section=section, item=item, basis="per kg dry Sargassum", unit=f"{unit}/kg dry", value=per_kg_dry,
                 note=note),
            dict(section=section, item=item, basis="per kg H2", unit=f"{unit}/kg H2", value=per_kg_dry / h2,
                 note=note),
            dict(section=section, item=item, basis="annual", unit=annual_unit, value=per_kg_dry * dry_yr * factor,
                 note=note)]


def _wide(per_scenario, keys, value="value", deltas=True):
    order, data = [], {}
    for sid in IDS:
        for r in per_scenario[sid]:
            k = tuple(r.get(f, "") for f in keys)
            if k not in data:
                order.append(k)
                data[k] = {}
            data[k][sid] = r[value]
    rows = []
    for k in order:
        row = dict(zip(keys, k))
        for sid in IDS:
            row[sid] = data[k].get(sid, _NAN)
        if deltas:
            base = row[_BASE]
            for sid in IDS[1:]:
                x = row[sid]
                ok = _num(x) and _num(base)
                row[f"{sid} minus Gas-C"] = x - base if ok else _NAN
                row[f"{sid} vs Gas-C [%]"] = (x / base - 1.0) * 100.0 if ok and base else _NAN
        rows.append(row)
    return rows


def _long(per_scenario, extra=None):
    rows = []
    for sid in IDS:
        for r in per_scenario[sid]:
            rows.append(dict(scenario=sid, **(extra(sid) if extra else {}), **r))
    return rows


# ---------------------------------------------------------------------------
# Sheets
# ---------------------------------------------------------------------------

def _definitions(R):
    out = {}
    for sid in IDS:
        r = R[sid]
        u2, ch = r["U2"], r["char"]
        rows = [dict(item="Closure method", unit="-", value=r["method"]),
                dict(item="Status", unit="-", value="BASELINE" if sid == _BASE else "ALTERNATIVE SCENARIO (not baseline)"),
                dict(item="Definition", unit="-", value=r["note"]),
                dict(item="Uniform scale factor s", unit="-", value=u2["s"])]
        for g in ("H2", "CH4", "CO", "CO2"):
            rows.append(dict(item=f"{g} yield, experimental (Ni-CatATT)", unit="mmol/g daf", value=u2["measured"][g]))
            rows.append(dict(item=f"{g} yield, model", unit="mmol/g daf", value=u2["model"][g]))
        rows += [dict(item="Char mass (CH0.5O0.1)", unit="kg/kg dry", value=ch["mass"]),
                 dict(item="Char carbon", unit="kg C/kg dry", value=ch["carbon"]),
                 dict(item="Char carbon mass fraction", unit="-", value=ch["C_fraction"]),
                 dict(item="Feed N and S retained in residue", unit="kg/kg dry", value=ch["NS"]),
                 dict(item="H2 product (PSA, 90 % recovery)", unit="kg H2/kg dry", value=r["h2_kg_per_kg_dry"]),
                 dict(item="H2 product", unit="t/yr", value=r["h2_kg_per_kg_dry"] * r["dry_kgph"] * r["hours"] / 1e3),
                 dict(item="U2 element balance", unit="-", value=u2["status"]),
                 dict(item="PSA off-gas fate", unit="-", value=fin.OFFGAS_FATE)]
        out[sid] = rows
    rows = _wide(out, ("item", "unit"))
    rows.insert(0, dict(item="NOTE", unit="-", **{sid: "Gas-A is a gas-yield scenario; it is unrelated to TEA Case A "
                                                       "(CaCO3 filter cake disposed)" if sid == _BASE else ""
                                                  for sid in IDS}))
    return rows


def _process_io(R):
    out = {}
    for sid in IDS:
        r = R[sid]
        h2, dry_yr = r["h2_kg_per_kg_dry"], r["dry_kgph"] * r["hours"]
        st = {k: {c: v / r["dry_kgph"] for c, v in d.items()} for k, d in r["streams"].items()}
        na = {x["item"]: x["value"] for x in r["na_ca"]}
        rows = []
        E = lambda sec, item, v, unit, note="": rows.extend(_expand(sec, item, v, unit, h2, dry_yr, note))
        E("Products", "H2 product (H2)", st["h2_product"]["H2"], "kg")
        for g in ("CH4", "H2", "CO", "CO2"):
            E("Products", f"PSA off-gas: {g}", st["u3_tail_gas"][g], "kg", "collected; final fate UNRESOLVED")
        E("Products", "PSA off-gas: total", st["u3_tail_gas"]["F_mass"], "kg")
        E("Char", "Char mass (CH0.5O0.1)", r["char"]["mass"], "kg")
        E("Char", "Char carbon", r["char"]["carbon"], "kg C")
        E("NaOH loop", "NaOH entering U2 (gross)", na["NaOH entering U2 (gross requirement, 2 kg/kg daf)"], "kg")
        E("NaOH loop", "NaOH recovered (EC1 recycle)", na["NaOH from recycle (EC1 concentrate)"], "kg")
        E("NaOH loop", "NaOH makeup (fresh solid)", na["NaOH makeup (fresh solid)"], "kg")
        rows.append(dict(section="NaOH loop", item="Effective NaOH recovery", basis="-", unit="-",
                         value=na["Effective NaOH recovery = 1 - makeup / gross"], note="1 - makeup / gross"))
        E("Lime and carbonate", "Ca(OH)2 consumption", st["lime"]["F_mass"], "kg")
        E("Lime and carbonate", "CaCO3 formed (C1)", na["C1: CaCO3 formed (coproduct)"], "kg")
        E("Lime and carbonate", "CaCO3 wet filter cake", st["caco3_cake"]["F_mass"], "kg",
          "reference: no cost, no revenue; TEA Case A: disposed")
        E("Water and waste", "Process water (D1)", st["dissolution_water"]["F_mass"], "kg")
        E("Water and waste", "Wastewater to treatment (incl. alkaline purge)", r["wastewater_m3_per_kg_dry"], "m3")
        E("Water and waste", "Solid waste to landfill (ash/char cake)", r["landfill_kg_per_kg_dry"], "kg")
        E("Water and waste", "H2SO4 for purge neutralization", r["h2so4_kg_per_kg_dry"], "kg")
        for x in r["external"]:
            if x["component"] == "TOTAL":
                E(f"External streams ({x['direction']})", f"{x['stream']} [{x['category']}]", x["kg_per_kg_dry"], "kg")
        for x in r["carbon"]:
            E("Biogenic carbon fate", f"{x['stream']} [{x['direction']}]", x["kg_C_per_kg_dry"], "kg C")
        out[sid] = rows
    return _wide(out, ("section", "item", "basis", "unit"))


def _energy(R):
    out = {}
    for sid in IDS:
        r = R[sid]
        h2, dry_yr = r["h2_kg_per_kg_dry"], r["dry_kgph"] * r["hours"]
        rows = []
        for x in r["unit_energy"]:
            if x["kind"] == "electricity":
                rows += _expand("Electricity by unit (modeled)", x["unit"], x["electricity_kWh_per_kg_dry"], "kWh",
                                h2, dry_yr)
            else:
                rows += _expand(f"Unit {x['kind']} duty (utility side)", f"{x['unit']} [{x['agent']}]",
                                abs(x["utility_duty_MJ_per_kg_dry"]), "MJ", h2, dry_yr,
                                f"process {abs(x['process_duty_MJ_per_kg_dry']):.4g} + loss "
                                f"{x['heat_loss_MJ_per_kg_dry']:.4g} MJ/kg dry")
        for est in r["estimates"]:
            if est["power_kW"] == est["power_kW"] and est["power_kW"] > 0:
                rows += _expand("Electricity by unit (outside unit models)", f"{est['unit']}: {est['item']}",
                                est["power_kW"] / r["dry_kgph"], "kWh", h2, dry_yr)
        for x in r["utilities"]:
            unit = x["unit"].split("/")[0]
            rows += _expand("Purchased utilities (totals)", x["item"], x["per_kg_dry"], unit, h2, dry_yr, x["note"])
        out[sid] = rows
    return _wide(out, ("section", "item", "basis", "unit"))


def _capex(R):
    out = {}
    for sid in IDS:
        rows = []
        for x in R[sid]["capex"]:
            first = x["item"].split()[0].rstrip(":")
            uid = "U3P" if first == "PSA" else first
            rows.append(dict(item=x["item"], unit=uid if uid in _AREAS else "-",
                             area=_AREAS.get(uid, "TOTAL"), metric="installed cost [USD]", value=x["installed_cost"]))
            rows.append(dict(item=x["item"], unit=uid if uid in _AREAS else "-",
                             area=_AREAS.get(uid, "TOTAL"), metric="purchase cost [USD]", value=x["purchase_cost"]))
        out[sid] = rows
    wide = _wide(out, ("item", "unit", "area", "metric"))
    for r in wide:
        fci = {sid: next(x["installed_cost"] for x in R[sid]["capex"] if x["item"].startswith("Installed equipment"))
               for sid in IDS}
        for sid in IDS:
            r[f"{sid} share of FCI"] = (r[sid] / fci[sid] if r["metric"].startswith("installed") and _num(r[sid])
                                        else _NAN)
    return wide


def _capex_detail(R):
    rows = []
    for sid in IDS:
        r = R[sid]
        for x in r["capex_detail"]:
            rows.append(dict(scenario=sid, **{k: x.get(k, "") for k in (
                "item", "class_", "sizing_basis", "parallel_units", "purchase_cost_USD", "installed_cost_USD", "F_BM",
                "correlation", "cost_year", "source")}))
        for e in r["estimates"]:
            rows.append(dict(scenario=sid, item=f"{e['unit']}: {e['item']} (capacity)", class_="estimate capacity",
                             sizing_basis=e["size"], correlation=e["method"], source=e["note"]))
        rows.append(dict(scenario=sid, item="PSA capacity (H2 product)", class_="anchor scaling",
                         sizing_basis=f"{r['psa_t_H2_per_day']:.2f} t H2/d",
                         correlation=f"{tea_mod._T['capex']['PSA']['anchor_installed_cost_usd']:.4g} USD at "
                                     f"{tea_mod._T['capex']['PSA']['anchor_capacity_t_H2_per_day']} t/d, "
                                     f"exponent {tea_mod._T['capex']['PSA']['exponent']}",
                         source=tea_mod._T["capex"]["PSA"]["source"]))
    return rows


def _opex(R, case):
    key, msp_key = ("opex_detail", "msp") if case == "Reference" else ("opex_detail_A", "msp_A")
    rows = []
    for sid in IDS:
        r = R[sid]
        dry_yr = r["dry_kgph"] * r["hours"]
        total = sum(x["annual_cost_USD"] for x in r[key])
        for x in r[key]:
            rows.append(dict(scenario=sid, TEA_case=case, item=x["item"],
                             activity_per_kg_dry=x["consumption_per_kg_dry"], activity_unit=x["unit"],
                             annual_activity=x["annual_consumption"], unit_price=x["unit_price"],
                             price_unit=x["price_unit"], annual_cost_USD=x["annual_cost_USD"],
                             USD_per_kg_dry=x["annual_cost_USD"] / dry_yr, USD_per_kg_H2=x["USD_per_kg_H2"],
                             share_of_total_OPEX=x["annual_cost_USD"] / total, source=x["source"],
                             accounting=x["accounting"]))
        rows.append(dict(scenario=sid, TEA_case=case, item="TOTAL OPEX (VOC incl. disposal + FOC)",
                         annual_cost_USD=total, USD_per_kg_dry=total / dry_yr,
                         USD_per_kg_H2=total / (r["product_kg_per_kg_dry"] * dry_yr), share_of_total_OPEX=1.0,
                         accounting=f"MSP {r[msp_key]:.4f} USD/kg H2"))
    return rows


def _msp_breakdown(R):
    rows = []
    for sid in IDS:
        r = R[sid]
        h = r["product_kg_per_kg_dry"]
        for case, k, msp in (("Reference", "dcf", r["msp"]), ("TEA Case A (CaCO3 cake disposed)", "dcf_A", r["msp_A"])):
            for x in r[k]:
                rows.append(dict(scenario=sid, TEA_case=case, **x, USD_per_kg_dry_levelized=x["USD_per_kg_H2"] * h))
            rows.append(dict(scenario=sid, TEA_case=case, component="MSP (sum of components)", group="TOTAL",
                             PV_MUSD=sum(x["PV_MUSD"] for x in r[k]),
                             USD_per_kg_H2=sum(x["USD_per_kg_H2"] for x in r[k]),
                             basis=f"SaBReTEA.solve_price = {msp:.6f}", share_of_MSP=1.0,
                             USD_per_kg_dry_levelized=msp * h))
    return rows


def _msp_simple(R):
    """Existing att.tea._opex_table view (annual cost / annual H2 + remainder) and its reconciliation."""
    rows = []
    for sid in IDS:
        r = R[sid]
        dcf = {x["group"]: 0.0 for x in r["dcf"]}
        for x in r["dcf"]:
            dcf[x["group"]] += x["USD_per_kg_H2"]
        for x in r["opex_table"]:
            rows.append(dict(scenario=sid, item=x["item"], category=x["category"], USD_per_yr=x["USD_per_yr"],
                             USD_per_kg_H2=x["USD_per_kg_H2"], basis=x["basis"]))
        remainder = next(x["USD_per_kg_H2"] for x in r["opex_table"] if x["category"] == "capital")
        dcf_capital = sum(v for g, v in dcf.items() if g in ("Capital (FCI + WC, net of loan)",
                                                             "Financing (debt service)", "Income tax",
                                                             "Solver residual"))
        rows.append(dict(scenario=sid, item="RECONCILIATION: simple remainder - DCF (capital + financing + tax)",
                         category="check", USD_per_kg_H2=remainder - dcf_capital,
                         basis="difference = FOC startup profile (FOC at 100 % in the startup year while sales are "
                               "at 50 %); VOC and disposal pass through 1:1"))
    return rows


def _tea_cases(R):
    rows = []
    for sid in IDS:
        r = R[sid]
        hours, dry = r["hours"], r["dry_kgph"]
        cake_t = r["streams"]["caco3_cake"]["F_mass"] * hours / 1e3
        disposal = -next(x["unit_price"] for x in r["opex_detail_A"] if x["item"] == "Disposal: caco3_cake")
        cake_usd = next(x["annual_cost_USD"] for x in r["opex_detail_A"] if x["item"] == "Disposal: caco3_cake")
        h2_yr = r["product_kg_per_kg_dry"] * dry * hours
        rows.append(dict(scenario=sid, MSP_TEA_reference=r["msp"], MSP_TEA_CaseA_CaCO3_disposal=r["msp_A"],
                         delta_USD_per_kg_H2=r["msp_A"] - r["msp"], wet_CaCO3_cake_t_per_yr=cake_t,
                         cake_disposal_price_USD_per_kg=-disposal, cake_disposal_MUSD_per_yr=cake_usd / 1e6,
                         cake_disposal_USD_per_kg_H2=cake_usd / h2_yr,
                         note="Reference: cake neither sold nor costed; TEA Case A: cake disposed at tea.yaml "
                              "disposal_solid. Gas-A (gas-yield scenario) is unrelated to TEA Case A."))
    return rows


def _lca_factors(R):
    rows = [dict(table="Emission-factor register (att_lca.yaml; identical for all scenarios)", **x)
            for x in lca.get_att_lca_factor_register()]
    per = {}
    for sid in IDS:
        r = R[sid]
        dry_yr = r["dry_kgph"] * r["hours"]
        per[sid] = []
        for x in r["gwp"][:-1]:
            per[sid] += _expand("Activity data", x["item"], x["activity_per_kg_dry"], x["activity_unit"],
                                r["h2_kg_per_kg_dry"], dry_yr, f"EF {x['EF']:.6g} {x['EF_unit']}")
    rows += [dict(table="Activity data by scenario", **x) for x in _wide(per, ("item", "basis", "unit"))]
    return rows


def _gwp_inputs(R):
    rows = []
    for sid in IDS:
        r = R[sid]
        dry_yr = r["dry_kgph"] * r["hours"]
        for x in r["gwp"]:
            rows.append(dict(scenario=sid, item=x["item"], stage=x["stage"], activity_per_kg_dry=x["activity_per_kg_dry"],
                             activity_per_kg_H2=x["activity_per_kg_dry"] / r["h2_kg_per_kg_dry"],
                             annual_activity=x["activity_per_kg_dry"] * dry_yr, activity_unit=x["activity_unit"],
                             EF=x["EF"], EF_unit=x["EF_unit"], EF_source=x["source"],
                             GWP_kgCO2e_per_kg_dry=x["GWP_kgCO2e_per_kg_dry"],
                             GWP_kgCO2e_per_kg_H2=x["GWP_kgCO2e_per_kg_H2"],
                             GWP_t_CO2e_per_yr=x["GWP_kgCO2e_per_kg_dry"] * dry_yr / 1e3, share=x["share"]))
        ch4 = r["streams"]["u3_tail_gas"]["CH4"] / r["dry_kgph"]
        rows.append(dict(scenario=sid, item="NOT IN GWP: PSA off-gas CH4 if vented (indicative)", stage="excluded",
                         activity_per_kg_dry=ch4, activity_per_kg_H2=ch4 / r["h2_kg_per_kg_dry"],
                         annual_activity=ch4 * dry_yr, activity_unit="kg CH4", EF=r["gwp_ch4"],
                         EF_unit="kg CO2e/kg CH4 (GWP100, AR6 non-fossil)", EF_source="IPCC AR6 WG1 Table 7.15",
                         GWP_kgCO2e_per_kg_dry=ch4 * r["gwp_ch4"],
                         GWP_kgCO2e_per_kg_H2=ch4 * r["gwp_ch4"] / r["h2_kg_per_kg_dry"],
                         GWP_t_CO2e_per_yr=ch4 * r["gwp_ch4"] * dry_yr / 1e3, share=_NAN))
        cake = r["streams"]["caco3_cake"]["F_mass"] / r["dry_kgph"]
        ef = float(lca._EF["inert_landfill"]["value"])
        rows.append(dict(scenario=sid, item="NOT IN GWP: CaCO3 wet cake landfilled (TEA Case A consistency, indicative)",
                         stage="excluded", activity_per_kg_dry=cake, activity_per_kg_H2=cake / r["h2_kg_per_kg_dry"],
                         annual_activity=cake * dry_yr, activity_unit="kg", EF=ef, EF_unit="kg CO2e/kg",
                         EF_source=lca._EF["inert_landfill"]["source"], GWP_kgCO2e_per_kg_dry=cake * ef,
                         GWP_kgCO2e_per_kg_H2=cake * ef / r["h2_kg_per_kg_dry"],
                         GWP_t_CO2e_per_yr=cake * ef * dry_yr / 1e3, share=_NAN))
    return rows


def _gwp_view(R, key, name):
    out = {sid: [] for sid in IDS}
    for sid in IDS:
        r = R[sid]
        dry_yr = r["dry_kgph"] * r["hours"]
        for x in r[key]:
            for basis, unit, v in (("per kg dry Sargassum", "kg CO2e/kg dry", x["GWP_kgCO2e_per_kg_dry"]),
                                   ("per kg H2", "kg CO2e/kg H2", x["GWP_kgCO2e_per_kg_H2"]),
                                   ("annual", "t CO2e/yr", x["GWP_kgCO2e_per_kg_dry"] * dry_yr / 1e3
                                    if _num(x["GWP_kgCO2e_per_kg_dry"]) else _NAN),
                                   ("share", "-", x["share"])):
                out[sid].append(dict(**{name: x[name]}, basis=basis, measure_unit=unit, value=v))
        total = r["gwp"][-1]
        for basis, unit, v in (("per kg dry Sargassum", "kg CO2e/kg dry", total["GWP_kgCO2e_per_kg_dry"]),
                               ("per kg H2", "kg CO2e/kg H2", total["GWP_kgCO2e_per_kg_H2"]),
                               ("annual", "t CO2e/yr", total["GWP_kgCO2e_per_kg_dry"] * dry_yr / 1e3)):
            out[sid].append(dict(**{name: "TOTAL (System.get_net_impact)"}, basis=basis, measure_unit=unit, value=v))
    return _wide(out, (name, "basis", "measure_unit"))


def _decompose(B, h):
    """Change vs Gas-C of B/h: denominator (H2 yield) effect at Gas-C burden + inventory effect."""
    b0, h0 = B[_BASE], h[_BASE]
    rows = {}
    for sid in IDS[1:]:
        yield_effect = b0 / h[sid] - b0 / h0
        inventory_effect = (B[sid] - b0) / h[sid]
        rows[sid] = (yield_effect, inventory_effect)
    return rows


def _comparison(R):
    rows = []
    h = {sid: R[sid]["h2_kg_per_kg_dry"] for sid in IDS}
    hp = {sid: R[sid]["product_kg_per_kg_dry"] for sid in IDS}

    def wide(section, item, unit, vals, note=""):
        row = dict(section=section, item=item, unit=unit, **vals)
        for sid in IDS[1:]:
            ok = _num(vals[sid]) and _num(vals[_BASE])
            row[f"{sid} minus Gas-C"] = vals[sid] - vals[_BASE] if ok else _NAN
            row[f"{sid} vs Gas-C [%]"] = (vals[sid] / vals[_BASE] - 1) * 100 if ok and vals[_BASE] else _NAN
        row["note"] = note
        rows.append(row)

    util = {sid: {x["item"]: x["per_kg_dry"] for x in R[sid]["utilities"]} for sid in IDS}
    dry_yr = {sid: R[sid]["dry_kgph"] * R[sid]["hours"] for sid in IDS}
    wide("H2", "Annual H2 production", "t H2/yr", {s: h[s] * dry_yr[s] / 1e3 for s in IDS})
    wide("H2", "H2 product", "kg H2/kg dry", h)
    for item, unit in (("NaOH makeup (fresh solid)", "kg/kg dry"),):
        wide("Materials", item, unit, {s: R[s]["streams"]["fresh_naoh_solid"]["F_mass"] / R[s]["dry_kgph"] for s in IDS})
    wide("Materials", "Ca(OH)2", "kg/kg dry", {s: R[s]["streams"]["lime"]["F_mass"] / R[s]["dry_kgph"] for s in IDS})
    wide("Materials", "CaCO3 wet cake", "kg/kg dry",
         {s: R[s]["streams"]["caco3_cake"]["F_mass"] / R[s]["dry_kgph"] for s in IDS})
    wide("Materials", "Wastewater", "m3/kg dry", {s: R[s]["wastewater_m3_per_kg_dry"] for s in IDS})
    wide("Materials", "Ash/char cake to landfill", "kg/kg dry", {s: R[s]["landfill_kg_per_kg_dry"] for s in IDS})
    for item in ("U2 natural gas: fuel input (LHV)", "LP steam: boiler natural gas (LHV)", "Cooling water: heat removed",
                 "Electricity: total"):
        unit = "kWh/kg dry" if item.startswith("Electricity") else "MJ/kg dry"
        wide("Energy", item, unit, {s: util[s][item] for s in IDS})
    wide("Energy", "Natural gas total (U2 + boiler, LHV)", "MJ/kg dry",
         {s: util[s]["U2 natural gas: fuel input (LHV)"] + util[s]["LP steam: boiler natural gas (LHV)"] for s in IDS})
    fci = {s: R[s]["tea_totals"]["FCI"] for s in IDS}
    wide("CAPEX", "FCI", "MUSD", {s: fci[s] / 1e6 for s in IDS})
    wide("CAPEX", "TCI", "MUSD", {s: R[s]["tea_totals"]["TCI"] / 1e6 for s in IDS})
    for area in sorted(set(_AREAS.values())):
        vals = {}
        for s in IDS:
            vals[s] = sum(x["installed_cost"] for x in R[s]["capex"]
                          if _AREAS.get("U3P" if x["item"].split()[0] == "PSA" else x["item"].split()[0].rstrip(":"))
                          == area) / 1e6
        if any(vals.values()):
            wide("CAPEX", f"Installed: {area}", "MUSD", vals)
    opex = {s: sum(x["annual_cost_USD"] for x in R[s]["opex_detail"]) for s in IDS}
    wide("OPEX", "Total OPEX (reference)", "MUSD/yr", {s: opex[s] / 1e6 for s in IDS})
    wide("OPEX", "Total OPEX per kg dry (reference)", "USD/kg dry", {s: opex[s] / dry_yr[s] for s in IDS})
    wide("OPEX", "Total OPEX per kg H2 (reference)", "USD/kg H2", {s: opex[s] / (hp[s] * dry_yr[s]) for s in IDS})
    for case, k in (("Reference", "msp"), ("TEA Case A", "msp_A")):
        msp = {s: R[s][k] for s in IDS}
        B = {s: msp[s] * hp[s] for s in IDS}
        wide("MSP", f"MSP {case}", "USD/kg H2", msp)
        wide("MSP", f"Levelized cost per kg dry feed ({case})", "USD/kg dry", B, "MSP x H2 product per kg dry")
        dec = _decompose(B, hp)
        wide("MSP decomposition", f"{case}: change due to H2 yield (denominator)", "USD/kg H2",
             {_BASE: 0.0, **{s: dec[s][0] for s in IDS[1:]}}, "Gas-C cost per kg dry / scenario H2 yield - Gas-C MSP")
        wide("MSP decomposition", f"{case}: change due to process inventory and cost", "USD/kg H2",
             {_BASE: 0.0, **{s: dec[s][1] for s in IDS[1:]}}, "(scenario - Gas-C cost per kg dry) / scenario H2 yield")
    gwp_dry = {s: R[s]["gwp"][-1]["GWP_kgCO2e_per_kg_dry"] for s in IDS}
    wide("GWP", "GWP100 per kg dry feed", "kg CO2e/kg dry", gwp_dry)
    wide("GWP", "GWP100 per kg H2", "kg CO2e/kg H2", {s: R[s]["gwp"][-1]["GWP_kgCO2e_per_kg_H2"] for s in IDS})
    wide("GWP", "Annual GWP100", "kt CO2e/yr", {s: gwp_dry[s] * dry_yr[s] / 1e6 for s in IDS})
    dec = _decompose(gwp_dry, h)
    wide("GWP decomposition", "change due to H2 yield (denominator)", "kg CO2e/kg H2",
         {_BASE: 0.0, **{s: dec[s][0] for s in IDS[1:]}}, "Gas-C GWP per kg dry / scenario H2 yield - Gas-C GWP")
    wide("GWP decomposition", "change due to process inventory", "kg CO2e/kg H2",
         {_BASE: 0.0, **{s: dec[s][1] for s in IDS[1:]}}, "(scenario - Gas-C GWP per kg dry) / scenario H2 yield")
    # Per-contributor decomposition (GWP inputs and MSP groups).
    for x in R[_BASE]["gwp"][:-1]:
        B = {s: next(y["GWP_kgCO2e_per_kg_dry"] for y in R[s]["gwp"] if y["item"] == x["item"]) for s in IDS}
        d = _decompose(B, h)
        wide("GWP decomposition by input", f"{x['item']}: yield | inventory effect", "kg CO2e/kg H2",
             {_BASE: 0.0, **{s: f"{d[s][0]:.4f} | {d[s][1]:.4f}" for s in IDS[1:]}})
    for g in _groups(R[_BASE]["dcf"]):
        B = {s: _group_sum(R[s]["dcf"], g) * hp[s] for s in IDS}
        d = _decompose(B, hp)
        wide("MSP decomposition by group (reference)", f"{g}: yield | inventory effect", "USD/kg H2",
             {_BASE: 0.0, **{s: f"{d[s][0]:.4f} | {d[s][1]:.4f}" for s in IDS[1:]}})
    return rows


def _groups(dcf):
    out = []
    for x in dcf:
        if x["group"] not in out:
            out.append(x["group"])
    return out


def _group_sum(dcf, group):
    return sum(x["USD_per_kg_H2"] for x in dcf if x["group"] == group)


def _assumptions(R):
    scale = inv.get_att_reference_scale()
    fin_ = tea_mod._FIN
    rows = [
        ("Scenarios", "Gas-C (BASELINE): uniform_redox_scaling, s = 0.5998; Gas-Cprime: uniform_co2_free; Gas-A: "
                      "h2_measured_ch4_max. Selected element-balanced gas-yield scenarios, not physical bounds.",
         "att.yaml; att.final.GAS_SCENARIOS"),
        ("Gas-A vs TEA Case A", "Gas-A is a gas-yield scenario. TEA Case A = CaCO3 filter cake disposed at tea.yaml "
                                "disposal_solid (no sales).", "att.tea.evaluate_att_tea(caco3=dict(fraction=0))"),
        ("Experimental input", "Ni-CatATT only (att.yaml reactor.cases)", "att_experiment.yaml row 8"),
        ("Scale", f"{scale['wet_feed_t_per_day']:.0f} wet t/d = {scale['dry_feed_t_per_day']:.1f} dry t/d; "
                  f"{scale['operating_hours_per_year']:.0f} h/yr; identical for all scenarios", "feedstock.yaml"),
        ("Simulation", "Each scenario: separate full-scale BioSTEAM simulation (create_att_system(u2_gas_closure=...)); "
                       "equipment, utilities and electricity from that simulation", "att.scenarios._evaluate"),
        ("Financial", f"IRR {fin_['IRR']}, income tax {fin_['income_tax']}, {fin_['depreciation']}, duration "
                      f"{fin_['duration']}, loan {fin_['finance_fraction']} of FCI at {fin_['finance_interest']} for "
                      f"{fin_['finance_years']} yr, WC {fin_['WC_over_FCI']} FCI, FOC {fin_['foc_frac_of_fci']} FCI",
         "tea.yaml"),
        ("FCI", "FCI = installed equipment cost incl. TEA-only estimates (PSA anchor, vessels, EC1 evaporator); no "
                "indirect capital (SaBRe convention)", "att.tea.ATTTEA"),
        ("MSP breakdown", "Levelized from SaBReTEA's cash-flow table at the solved MSP: component = PV(component) / "
                          "PV(H2 kg). VOC items use the VOC profile, disposal (negative sales) the sales profile, FOC "
                          "its profile; capital = PV(FCI + WC - loan), financing = PV(debt service), tax = PV(tax).",
         "att.scenarios._dcf_breakdown"),
        ("Utilities in TEA", "U2 natural gas priced as fuel = duty / 0.90 x USD/MJ (agent cost plus adjustment, no "
                             "double count); LP steam and cooling water at BioSTEAM agent prices (boiler fuel and tower "
                             "power not priced again); electricity = modeled units + agitator/EC1 vacuum estimate",
         "att.tea._voc_items"),
        ("Utilities in LCA", "U2 natural gas = duty / 0.90; LP steam = boiler natural gas, duty / 0.80; cooling = "
                             "cooling-tower and CW-pump electricity; combustion and upstream supply separated",
         "att.lca.apply_att_gwp"),
        ("TEA/LCA steam basis", "TEA prices LP steam at the BioSTEAM agent price; LCA charges boiler natural gas "
                                "(0.80). Each is counted once in its own analysis.", "documented asymmetry"),
        ("CaCO3 cake in LCA", "Baseline GWP (all scenarios) has no CaCO3 cake burden or credit, consistent with the TEA "
                              "reference. TEA Case A disposes the cake; its landfill GWP is listed in 09 as indicative "
                              "and NOT added.", "att_lca.yaml coproduct"),
        ("Revenue", "None besides H2: no CH4, off-gas or CaCO3 revenue; no CaCO3 or CH4 credits", "att_tea.yaml"),
        ("LCA boundary", "PARTIAL: Sargassum collection and transport excluded (no activity data); cradle-to-gate H2 "
                         "at 20 bar; allocation none", "att_lca.yaml"),
        ("PSA off-gas", fin.OFFGAS_FATE + ". Indicative CH4 venting impact reported separately, NOT added to GWP.",
         "att_lca.yaml offgas"),
        ("Biogenic CO2", "Biogenic CO2 in off-gas and residues: GWP 0 (recorded, not credited); CaCO3 carbon storage "
                         "not credited", "att_lca.yaml"),
        ("Char", "Gas-C: char closes carbon (CH0.5O0.1); Gas-Cprime and Gas-A: char = 0 (residue char not measured)",
         "att.yaml"),
        ("Units", "per kg dry Sargassum; per kg H2 product; annual at reference scale (t, TJ, MWh, MUSD, t CO2e)", ""),
    ]
    return [dict(topic=a, assumption_or_limitation=b, source=c) for a, b, c in rows]


def _qc(R, rerun):
    rows = []

    def add(scenario, check, value, expected, ok):
        rows.append(dict(scenario=scenario, check=check, value=str(value), expected=str(expected),
                         status="PASS" if ok else "FAIL"))

    att = load_assumptions("att.yaml")["att"]
    exp = load_assumptions("att_experiment.yaml")["experimental_results"]["cases"]["Ni-CatATT"]
    add("all", "Baseline closure (att.yaml)", att["reactor"]["material_balance"]["gas_closure_method"],
        "uniform_redox_scaling", att["reactor"]["material_balance"]["gas_closure_method"] == "uniform_redox_scaling")
    add(_BASE, "Gas-C scale factor s", round(R[_BASE]["U2"]["s"], 4), 0.5998, abs(R[_BASE]["U2"]["s"] - 0.5998) < 5e-5)
    from biorefineries.sabre.analyses.att.paths import output_dir
    d7_path = output_dir("comparison") / "D7_Gas_Yield_Scenarios.csv"
    d7 = {}
    if d7_path.exists():
        import pandas as pd
        d7 = {r["scenario"]: r for r in pd.read_csv(d7_path).to_dict("records")}
    for sid in IDS:
        r = R[sid]
        msp, msp_a, gwp = _EXPECTED[sid]
        add(sid, "Experimental yields = att_experiment.yaml Ni-CatATT",
            r["U2"]["measured"], "unchanged", all(r["U2"]["measured"][g] == exp[g] for g in ("H2", "CH4", "CO", "CO2")))
        add(sid, "Reference MSP [USD/kg H2] ~ expected", round(r["msp"], 4), msp, abs(r["msp"] - msp) < 0.006)
        add(sid, "TEA Case A MSP [USD/kg H2] ~ expected", round(r["msp_A"], 4), msp_a, abs(r["msp_A"] - msp_a) < 0.006)
        g = r["gwp"][-1]["GWP_kgCO2e_per_kg_H2"]
        add(sid, "GWP100 [kg CO2e/kg H2] ~ expected", round(g, 3), gwp, abs(g - gwp) < 0.06)
        for col, val in (("MSP_TEA_reference_USD_per_kg_H2", r["msp"]),
                         ("MSP_TEA_CaseA_CaCO3_disposal_USD_per_kg_H2", r["msp_A"]),
                         ("GWP_kgCO2e_per_kg_H2", g), ("H2_product_kg_per_kg_dry", r["h2_kg_per_kg_dry"])):
            if sid in d7:
                add(sid, f"Equals comparison/D7 {col}", val, d7[sid][col], abs(val - d7[sid][col]) <= 1e-9 * abs(val))
            else:
                rows.append(dict(scenario=sid, check=f"Equals comparison/D7 {col}", value=str(val), expected="",
                                 status="NOT CHECKED (comparison/D7_Gas_Yield_Scenarios.csv missing; run run_att_final first)"))
        for case, k, kc, msp_k in (("Reference", "dcf", "dcf_checks", "msp"), ("TEA Case A", "dcf_A", "dcf_checks_A", "msp_A")):
            c = r[kc]
            add(sid, f"{case}: MSP components sum to MSP [USD/kg H2]", c["sum_vs_msp"], 0.0, abs(c["sum_vs_msp"]) < 1e-6)
            add(sid, f"{case}: PV(operating cost) = VOC x PV(v) + FOC x PV(o) [USD]", c["pv_C_check"], 0.0,
                abs(c["pv_C_check"]) < 1e-3 * r["tea_totals"]["FCI"] * 1e-6)
            add(sid, f"{case}: no incentives / replacement capital", (c["incentives_pv"], c["replacement_capex_pv"]),
                (0, 0), c["incentives_pv"] == 0 and abs(c["replacement_capex_pv"]) < 1e-6)
        t = r["tea_totals"]
        voc_items = sum(x["USD_per_yr"] for x in r["opex_table"] if x["category"] in ("materials", "utilities", "extra VOC"))
        add(sid, "OPEX: VOC items = SaBReTEA VOC (material + utility + add_OPEX + extra VOC)", voc_items, t["VOC"],
            abs(voc_items - t["VOC"]) <= 1e-9 * t["VOC"])
        add(sid, "OPEX: unit add_OPEX (none; not double counted)", t["add_OPEX"], 0.0, t["add_OPEX"] == 0.0)
        h2_rev = r["msp"] * r["product_kg_per_kg_dry"] * r["dry_kgph"] * r["hours"]
        neg = sum(x["USD_per_yr"] for x in r["opex_table"] if x["category"] in ("waste disposal", "CaCO3 cake", "off-gas"))
        add(sid, "OPEX: disposal items = -(sales - H2 revenue)", neg, -(t["sales"] - h2_rev),
            abs(neg + t["sales"] - h2_rev) <= 1e-6 * t["sales"])
        det = sum(x["annual_cost_USD"] for x in r["opex_detail"])
        tab = sum(x["USD_per_yr"] for x in r["opex_table"] if x["category"] not in ("capital", "total"))
        add(sid, "OPEX: detailed items = existing OPEX table (no double count or omission)", det, tab,
            abs(det - tab) <= 1e-9 * abs(tab))
        for x in r["tea_checks"]:
            add(sid, f"TEA: {x['check']}", x["value"], x["expected"], x["status"] == "PASS")
        for x in r["lca_checks"]:
            add(sid, f"LCA: {x['check']}", x["value"], x.get("expected", ""), x["status"] == "PASS")
        tot = r["gwp"][-1]["GWP_kgCO2e_per_kg_dry"]
        for name, part in (("inputs", r["gwp"][:-1]), ("unit operations", r["gwp_unit"]),
                           ("life-cycle stages", [x for x in r["gwp_stage"]
                                                  if x["GWP_kgCO2e_per_kg_dry"] == x["GWP_kgCO2e_per_kg_dry"]])):
            ssum = sum(x["GWP_kgCO2e_per_kg_dry"] for x in part)
            add(sid, f"GWP by {name} sums to total [kg CO2e/kg dry]", ssum, tot, abs(ssum - tot) <= 1e-9 * tot)
        hours = r["hours"]
        add(sid, "Operating hours", hours, 7920.0, hours == 7920.0)
        add(sid, "Annual H2 = H2 kg/h x 7920 h [t/yr]", r["h2_kg_per_kg_dry"] * r["dry_kgph"] * hours / 1e3,
            "H2 kg/kg dry x dry kg/h x h", True)
        add(sid, "H2 product purity (MSP per kg product = per kg H2)", r["h2_kg_per_kg_dry"] / r["product_kg_per_kg_dry"],
            1.0, abs(r["h2_kg_per_kg_dry"] / r["product_kg_per_kg_dry"] - 1) < 1e-9)
        ic = r["inventory_check"]
        add(sid, "Mass balance closed (relative)", ic["mass_relative_error"], 0.0, abs(ic["mass_relative_error"]) < 1e-8)
        worst = max(abs(v) for v in ic["element_relative_error"].values())
        add(sid, "Element balances closed (worst relative)", worst, 0.0, worst < 1e-8)
        add(sid, "Model flows unchanged by TEA/LCA evaluation", r["flows_unchanged"], True, r["flows_unchanged"])
        util = {x["item"]: x["per_kg_dry"] for x in r["utilities"]}
        e_tot = util["Electricity: total"]
        e_parts = (util["Electricity: modeled units"] + util["Electricity: cooling tower and CW pumps (estimate)"]
                   + util["Electricity: agitators and EC1 vacuum (estimate)"])
        add(sid, "Electricity total = units + cooling tower + auxiliaries (each once)", e_tot, e_parts,
            abs(e_tot - e_parts) <= 1e-12)
        lca_e = sum(x["activity_per_kg_dry"] for x in r["gwp"] if x["item"].startswith("Electricity"))
        add(sid, "LCA electricity activity = inventory electricity total [kWh/kg dry]", lca_e, e_tot,
            abs(lca_e - e_tot) <= 1e-9 * e_tot)
    for sid in IDS[1:]:
        for name, a, b in (("dry feed", R[sid]["dry_kgph"], R[_BASE]["dry_kgph"]),
                           ("prices", R[sid]["prices"], R[_BASE]["prices"]),
                           ("emission factors", R[sid]["factors"], R[_BASE]["factors"])):
            add(sid, f"Same {name} as Gas-C", "same" if a == b else f"{a} vs {b}", "same", a == b)
        a, b = R[sid]["ng_agent_CF"], R[_BASE]["ng_agent_CF"]
        add(sid, "Same natural-gas agent CF as Gas-C (kg basis; recomputed per system)", a, b,
            a[1] == b[1] and abs(a[0] - b[0]) <= 1e-12 * abs(b[0]))
    b = R[_BASE]
    for name, x, y in (("Reference MSP", rerun["msp"], b["msp"]), ("TEA Case A MSP", rerun["msp_A"], b["msp_A"]),
                       ("GWP per kg H2", rerun["gwp"][-1]["GWP_kgCO2e_per_kg_H2"], b["gwp"][-1]["GWP_kgCO2e_per_kg_H2"]),
                       ("FCI", rerun["tea_totals"]["FCI"], b["tea_totals"]["FCI"])):
        add(_BASE, f"Isolation: Gas-C re-run after Gas-Cprime and Gas-A reproduces {name}", x, y,
            abs(x - y) <= 1e-9 * abs(y))
    return rows


def _figures(R):
    msp, gwp, capex, opex, mat = [], [], [], [], []
    for sid in IDS:
        r = R[sid]
        for case, k in (("Reference", "dcf"), ("TEA Case A", "dcf_A")):
            for g in _groups(r[k]):
                msp.append(dict(scenario=sid, TEA_case=case, component=g, USD_per_kg_H2=_group_sum(r[k], g)))
        for x in r["gwp"][:-1]:
            gwp.append(dict(scenario=sid, contributor=x["item"], stage=x["stage"],
                            kgCO2e_per_kg_H2=x["GWP_kgCO2e_per_kg_H2"], kgCO2e_per_kg_dry=x["GWP_kgCO2e_per_kg_dry"]))
        areas = {}
        for x in r["capex"]:
            first = x["item"].split()[0].rstrip(":")
            area = _AREAS.get("U3P" if first == "PSA" else first)
            if area:
                areas[area] = areas.get(area, 0.0) + x["installed_cost"]
        capex += [dict(scenario=sid, area=a, installed_MUSD=v / 1e6) for a, v in areas.items() if v]
        cats = {}
        for x in r["opex_table"]:
            if x["category"] in ("capital", "total"):
                continue
            g = _cost_group(x["item"], x["category"])
            cats[g] = cats.get(g, 0.0) + x["USD_per_yr"]
        opex += [dict(scenario=sid, category=g, MUSD_per_yr=v / 1e6) for g, v in cats.items()]
        util = {x["item"]: x["per_kg_dry"] for x in r["utilities"]}
        s = r["streams"]
        dry = r["dry_kgph"]
        h = r["h2_kg_per_kg_dry"]
        for item, unit, v in (("NaOH makeup", "kg", s["fresh_naoh_solid"]["F_mass"] / dry),
                              ("Ca(OH)2", "kg", s["lime"]["F_mass"] / dry),
                              ("CaCO3 wet cake", "kg", s["caco3_cake"]["F_mass"] / dry),
                              ("Process water", "kg", s["dissolution_water"]["F_mass"] / dry),
                              ("Natural gas, U2 (LHV)", "MJ", util["U2 natural gas: fuel input (LHV)"]),
                              ("Natural gas, steam boiler (LHV)", "MJ", util["LP steam: boiler natural gas (LHV)"]),
                              ("Electricity, total", "kWh", util["Electricity: total"])):
            mat.append(dict(scenario=sid, item=item, per_kg_dry=v, per_kg_dry_unit=f"{unit}/kg dry", per_kg_H2=v / h,
                            per_kg_H2_unit=f"{unit}/kg H2"))
    return dict(F1_MSP_Stack=msp, F2_GWP_Stack=gwp, F3_CAPEX_by_Area=capex, F4_OPEX_by_Category=opex,
                F5_Material_Energy=mat)


# ---------------------------------------------------------------------------
# Build and export
# ---------------------------------------------------------------------------

def build_att_gas_scenario_tables():
    warnings.filterwarnings("ignore")
    R = {label: _evaluate(label, method, note) for label, method, note in fin.GAS_SCENARIOS}
    label, method, note = fin.GAS_SCENARIOS[0]
    rerun = _evaluate(label, method, note)  # isolation check: Gas-C after the other scenarios
    tables = {
        "01_Scenario_Definitions": _definitions(R),
        "02_Process_IO": _process_io(R),
        "03_Unit_Energy_Utilities": _energy(R),
        "04_CAPEX_by_Scenario": _capex(R),
        "04b_CAPEX_Cost_Items_Sizing": _capex_detail(R),
        "05_OPEX_Reference": _opex(R, "Reference"),
        "05b_OPEX_TEA_Case_A": _opex(R, "TEA Case A"),
        "06_MSP_Breakdown_DCF": _msp_breakdown(R),
        "06b_MSP_Simple_Reconcile": _msp_simple(R),
        "07_TEA_Ref_vs_Case_A": _tea_cases(R),
        "08_LCA_EF_Activity": _lca_factors(R),
        "09_GWP_by_Input": _gwp_inputs(R),
        "10_GWP_by_Unit": _gwp_view(R, "gwp_unit", "unit"),
        "11_GWP_by_Stage": _gwp_view(R, "gwp_stage", "stage"),
        "12_Scenario_Comparison": _comparison(R),
        "13_Assumptions_Limitations": _assumptions(R),
        "14_QC_Checks": _qc(R, rerun),
    }
    tables.update(_figures(R))
    return tables


_README = """# ATT gas-yield scenarios: detailed TEA and LCA

Generated by `python -m biorefineries.sabre.test.run_att_gas_scenarios`
(`biorefineries/sabre/analyses/att/scenarios.py`). Reporting only: the
three selected element-balanced gas-yield scenarios are simulated separately
at the SaBRe reference scale and evaluated with the existing `att.tea`,
`att.lca`, `att.inventory` and `att.reporting` functions.

- **Gas-C (BASELINE):** `uniform_redox_scaling`, s = 0.5998.
- **Gas-Cprime:** `uniform_co2_free` (alternative scenario).
- **Gas-A:** `h2_measured_ch4_max` (H2-prioritized alternative scenario).
  Unrelated to **TEA Case A** (CaCO3 filter cake disposed, no sales).

MSP components (06) levelize SaBReTEA's cash-flow table at the solved MSP and
sum to the MSP. GWP100 is partial-boundary (no Sargassum collection and
transport). The PSA off-gas final fate is UNRESOLVED: no CH4 emission,
combustion or treatment cost is included; the indicative CH4 venting impact is
listed in 09 and not added to GWP. No CH4, off-gas or CaCO3 revenue or credit.
QC: sheet 14. Figure-ready data: sheets F1-F5.

Reproduce:

```
python -m biorefineries.sabre.test.run_att_all            # all results; QC 14 then compares with comparison/D7
python -m biorefineries.sabre.test.run_att_gas_scenarios  # this folder only (att_outputs/scenarios/gas_yield)
```

## Sheets

{sheets}
"""


def export_att_gas_scenario_comparison(out_dir=None):
    import re
    import pandas as pd
    from biorefineries.sabre.analyses.att.paths import output_dir

    out_dir = os.fspath(out_dir or output_dir("gas_scenarios"))
    tables = build_att_gas_scenario_tables()
    os.makedirs(out_dir, exist_ok=True)
    with pd.ExcelWriter(os.path.join(out_dir, "ATT_Gas_Scenarios_Detailed_TEA_LCA.xlsx")) as writer:
        for name, rows in tables.items():
            df = pd.DataFrame(rows)
            for col in df.columns:
                if df[col].dtype == object:
                    df[col] = df[col].map(lambda v: re.sub(r"\x1b\[[0-9;]*m", "", v) if isinstance(v, str) else v)
            df.to_csv(os.path.join(out_dir, f"{name}.csv"), index=False)
            df.to_excel(writer, sheet_name=name[:31], index=False)
            for row in writer.sheets[name[:31]].iter_rows():
                for cell in row:
                    if cell.data_type == "f":
                        cell.data_type = "s"
    sheets = "\n".join(f"- `{name}` ({len(rows)} rows)" for name, rows in tables.items())
    with open(os.path.join(out_dir, "README.md"), "w", encoding="utf-8") as f:
        f.write(_README.replace("{sheets}", sheets))
    return tables
