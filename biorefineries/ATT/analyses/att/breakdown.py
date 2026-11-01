# Bioindustrial-Park: BioSTEAM's Premier Biorefinery Models and Results
# Copyright (C) 2026-, Yu Zhou,
#                      Yalin Li <mailto.yalin.li@gmail.com>
#
# This module is under the UIUC open-source license. See
# github.com/BioSTEAMDevelopmentGroup/biosteam/blob/master/LICENSE.txt
# for license details.

"""
Breakdown of the ATT H2 minimum selling price (MSP) and GWP100 of the scenarios of ``analyses/att/scenarios.py``
at their capacity, with their lime and CaCO3 assumptions (scenarios.tea_config / lca_overrides). Configurations:

* ``fresh_sargassum`` ATT plant fed with wet fresh Sargassum (NLR scale: 3 million wet t/yr): P1 press
                      (municipal biosolids screw press), D0 dryer and the ATT process; the press liquid is the raw
                      juice for biostimulant production (transferred at zero price).
* ``presscake``       ATT plant fed with the presscake of a biostimulant plant (normally a waste), without P1.

* MSP by cost type and group: SaBReTEA's cash-flow table levelized at the
  solved MSP (NPV = 0), so the parts add up to the MSP. CAPEX-related =
  capital outlays (net of the loan), debt service and income tax; the rest
  are operating costs (materials, utilities, waste treatment and disposal,
  fixed operating cost). The natural gas group is net of the tail-gas offset.
* CAPEX: installed cost of each equipment item and of each process area,
  with the CAPEX-related MSP allocated to the areas in proportion to their
  installed cost (an allocation, not a separate calculation).
* OPEX: annual operating cost (undiscounted) by group and its share. It includes
  waste treatment and disposal, which SaBReTEA books as negative sales.
* GWP100: contribution of each input, with the stage totals.

Written by ``analyses/cost_gwp_breakdown_att.py`` to ``results/tables`` and
``results/figures``.
"""
import numpy as np
import pandas as pd

from biorefineries.ATT.analyses.att import inventory as inv
from biorefineries.ATT.analyses.att import scenarios as scen
from biorefineries.ATT.analyses.att import lca
from biorefineries.ATT.analyses.att import tea as tea_mod

__all__ = ("build_att_breakdown", "COST_TYPES", "CONFIGURATIONS", "CASES", "FIGURE_CASES", "CASE_LABELS", "LIME_LABELS")

# The scenarios of analyses/att/scenarios.py (ATT Scenario 1, 'att_s1').
CASES = scen.SCENARIOS
FIGURE_CASES = tuple(CASES)
CASE_LABELS = scen.CASE_LABELS
LIME_LABELS = scen.SHORT_LABELS
CONFIGURATIONS = {
    "fresh_sargassum": "Fresh Sargassum feed (press P1, dryer D0)",
    "presscake": "Presscake feed (presscake of a biostimulant plant, no P1)",
}

# Cost group -> cost type.
COST_TYPES = {
    "NaOH makeup": "Materials",
    "Ca(OH)2": "Materials",
    "Process water": "Materials",
    "Sargassum feedstock (0 in baseline)": "Materials",
    "Natural gas, U2 furnace": "Utilities",
    "LP steam (agent price)": "Utilities",
    "Cooling water (agent price)": "Utilities",
    "Electricity": "Utilities",
    "Neutralization (H2SO4)": "Waste treatment and disposal",
    "Wastewater treatment": "Waste treatment and disposal",
    "Ash/char cake disposal": "Waste treatment and disposal",
    "CaCO3 cake disposal": "Waste treatment and disposal",
    "CaCO3 byproduct sales": "Coproduct revenue",
    "Marine WHR: purchased heat displaced": "Utilities",
    "PSA off-gas handling (0; fate unresolved)": "Waste treatment and disposal",
    "Biostimulant juice transfer (coproduct)": "Waste treatment and disposal",
    "Fixed operating cost (4 % FCI)": "Fixed operating cost",
    "Capital (FCI + WC, net of loan)": "CAPEX-related",
    "Financing (debt service)": "CAPEX-related",
    "Income tax": "CAPEX-related",
}
_AREAS = {
    "P1": "Feed dewatering (P1)", "D0": "Feed drying (D0)", "M1": "Feed mixing (M1)", "U2": "ATT reactor (U2)",
    "U3HX": "Gas cooling and drying (U3HX, U3C, U3D)", "U3C": "Gas cooling and drying (U3HX, U3C, U3D)",
    "U3D": "Gas cooling and drying (U3HX, U3C, U3D)", "U3P": "PSA (U3P)", "U3K": "H2 compression (U3K)",
    "RC1": "Residue cooling (RC1)", "D1": "Residue slurry (D1)", "F1": "Residue filtration (F1)",
    "W2": "F2 washing and refiltration", "F2R": "F2 washing and refiltration",
    "C1": "Causticization (C1)", "F2": "CaCO3 filtration (F2)", "SP1": "Liquor split (SP1)",
    "EC1": "NaOH evaporation (EC1)", "K1": "Lime kiln (K1)", "S1": "Lime slaking (S1)",
    "SCRUB": "CO2 scrubber and filter (SCRUB, F3)", "F3": "CO2 scrubber and filter (SCRUB, F3)",
    "FCI": "Floating process CAPEX adjustment (FCI factor)", "WHR": "Marine waste heat recovery (WHR)",
}


def _cost_group(item, category):
    solid = tea_mod._T["prices"]["solid_waste_streams"]
    if category == "FOC":
        return "Fixed operating cost (4 % FCI)"
    if category == "juice":
        return "Biostimulant juice transfer (coproduct)"
    for prefix, group in (("NaOH", "NaOH makeup"), ("Ca(OH)2", "Ca(OH)2"), ("Process water", "Process water"),
                          ("Sargassum", "Sargassum feedstock (0 in baseline)"),
                          ("Utility: natural_gas", "Natural gas, U2 furnace"),
                          ("Natural gas", "Natural gas, U2 furnace"),
                          ("Utility: low_pressure_steam", "LP steam (agent price)"),
                          ("Utility: cooling_water", "Cooling water (agent price)"),
                          ("Electricity", "Electricity"), ("Purge neutralization", "Neutralization (H2SO4)"),
                          ("P1 power", "Electricity"),
                          ("CaCO3 sales", "CaCO3 byproduct sales"),
                          ("Marine WHR: pump", "Electricity"),
                          ("Marine WHR: ", "Marine WHR: purchased heat displaced"),
                          ("CaCO3 cake", "CaCO3 cake disposal"),
                          ("PSA off-gas", "PSA off-gas handling (0; fate unresolved)")):
        if item.startswith(prefix):
            return group
    if item == "Disposal: scrubber_cake":
        return "CaCO3 cake disposal"
    if item.startswith("Disposal: "):
        return "Ash/char cake disposal" if item.split(": ")[1] in solid else "Wastewater treatment"
    raise KeyError(item)


def _dcf_breakdown(sys, result):
    """Levelize SaBReTEA's cash-flow table at the solved MSP (NPV = 0)."""
    tea = result["tea"]
    hours = sys.operating_hours
    product = inv._streams(sys)[tea_mod._T["product"]]
    h2_kg_yr = float(product.imass["H2"]) * hours       # per kg of H2 (the product gas also holds CH4 and CO)
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
    S = df["Sales [MM$]"].to_numpy() * 1e6
    pv_f = float((S / tea.sales * DF).sum())
    pv_h2 = h2_kg_yr * pv_f  # discounted kg H2
    li_construction = 0.0
    if tea.finance_interest and not tea.accumulate_interest_during_construction:
        li_construction = float((df["Loan interest payment [MM$]"].to_numpy()[:start] * DF[:start]).sum()) * 1e6

    rows = []

    def add(component, group, pv_usd, basis):
        rows.append(dict(component=component, group=group, PV_MUSD=pv_usd / 1e6, USD_per_kg_H2=pv_usd / pv_h2,
                         basis=basis))

    for r in tea_mod._opex_table(sys, result):
        if r["category"] in ("materials", "utilities", "extra VOC"):
            add(r["item"], _cost_group(r["item"], r["category"]), r["USD_per_yr"] * pv_v, "VOC item x PV(VOC profile)")
        elif r["category"] in ("waste disposal", "CaCO3 cake", "CaCO3 sales", "off-gas", "juice"):
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
    msp = result["msp"]
    for r in rows:
        r["share_of_MSP"] = r["USD_per_kg_H2"] / msp
    return rows, h2_kg_yr


def _msp_tables(rows, msp):
    by = {}
    for r in rows:
        if r["group"] == "Solver residual":
            continue
        by[r["group"]] = by.get(r["group"], 0.0) + r["USD_per_kg_H2"]
    by_group = pd.DataFrame(
        [dict(group=g, cost_type=COST_TYPES[g], USD_per_kg_H2=v, share_of_MSP=v / msp) for g, v in by.items()
         if g != "Biostimulant juice transfer (coproduct)" or v != 0.0]
    ).sort_values(["cost_type", "USD_per_kg_H2"], ascending=[True, False]).reset_index(drop=True)
    by_type = by_group.groupby("cost_type", as_index=False)[["USD_per_kg_H2", "share_of_MSP"]].sum()
    by_type = by_type.sort_values("USD_per_kg_H2", ascending=False).reset_index(drop=True)
    return by_group, by_type


def _capex_tables(sys, result, capital_msp):
    tea = result["tea"]
    rows = []
    for x in tea_mod._capex_table(sys, result):
        if x["item"].startswith(("Installed equipment cost", "Working capital", "Total capital")):
            continue
        first = x["item"].split()[0].rstrip(":")
        area = _AREAS.get("U3P" if first == "PSA" else first, "Other")
        if x["installed_cost"]:
            rows.append(dict(item=x["item"], area=area, installed_MUSD=x["installed_cost"] / 1e6,
                             share_of_FCI=x["installed_cost"] / tea.FCI))
    equipment = pd.DataFrame(rows).sort_values("installed_MUSD", ascending=False).reset_index(drop=True)
    areas = equipment.groupby("area", as_index=False)[["installed_MUSD", "share_of_FCI"]].sum()
    areas["capital_related_MSP_USD_per_kg_H2"] = areas["share_of_FCI"] * capital_msp
    areas = areas.sort_values("installed_MUSD", ascending=False).reset_index(drop=True)
    return equipment, areas


def _opex_table(sys, result, h2_kg_yr):
    groups = {}
    for x in tea_mod._opex_table(sys, result):
        if x["category"] in ("capital", "total"):
            continue
        g = _cost_group(x["item"], x["category"])
        groups[g] = groups.get(g, 0.0) + x["USD_per_yr"]
    groups = {g: v for g, v in groups.items() if g != "Biostimulant juice transfer (coproduct)" or v != 0.0}
    aoc = sum(groups.values())
    df = pd.DataFrame([dict(group=g, cost_type=COST_TYPES[g], MUSD_per_yr=v / 1e6, USD_per_kg_H2=v / h2_kg_yr,
                            share_of_AOC=v / aoc) for g, v in groups.items()])
    return df.sort_values("MUSD_per_yr", ascending=False).reset_index(drop=True)


def _gwp_tables(contributions):
    rows = [r for r in contributions if not r["item"].startswith("TOTAL")]
    total = contributions[-1]["GWP_kgCO2e_per_kg_H2"]
    by_item = pd.DataFrame([dict(contributor=r["item"], stage=r["stage"], kgCO2e_per_kg_H2=r["GWP_kgCO2e_per_kg_H2"],
                                 share_of_total=r["GWP_kgCO2e_per_kg_H2"] / total) for r in rows])
    by_item = by_item.sort_values("kgCO2e_per_kg_H2", ascending=False).reset_index(drop=True)
    by_stage = by_item.groupby("stage", as_index=False)[["kgCO2e_per_kg_H2", "share_of_total"]].sum()
    by_stage = by_stage.sort_values("kgCO2e_per_kg_H2", ascending=False).reset_index(drop=True)
    by_item.insert(2, "counted_in_net", True)
    return by_item, by_stage, total


def build_att_breakdown(case="att_s1", caco3_price=None, sys=None, tea_kwargs=None, f2_sales=True):
    """
    One simulation of a scenario of analyses/att/scenarios.py; returns a dict of DataFrames and a summary dict.

    ATT Scenario 1 takes free, burden-free waste lime and sells the CaCO3 of its cakes (att_tea.yaml caco3_sales;
    the rest of each cake is disposed). ``caco3_price`` [USD/t] overrides the configured price for this call only;
    ``sys`` reuses an already simulated system of the scenario. ``tea_kwargs``: extra evaluate_att_tea keywords
    (the ATT S2 floating/WHR hooks, analyses/att/marine_tea.py); None = the land-based TEA.
    """
    spec = scen.ALL_SCENARIOS[case]
    if spec.get("marine") and tea_kwargs is None:
        raise ValueError(f"{case} is a marine scenario: use analyses/att/marine_tea.py (floating TEA and WHR).")
    return _build(case, spec, scen.create(spec) if sys is None else sys, caco3_price, tea_kwargs, f2_sales)


def _build(case, spec, sys, caco3_price=None, tea_kwargs=None, f2_sales=True):
    estimates = inv.get_att_cost_estimates(sys)
    # Lime price and CaCO3 treatment of the scenario (scenarios.tea_config, the single source).
    config = scen.tea_config(spec, caco3_price, f2_sales=f2_sales)
    sales_cfg, sell = config["caco3_sales"], config["caco3_sales"] is not None
    result = tea_mod.evaluate_att_tea(sys, estimates, **config, **(tea_kwargs or {}))
    sales = result["caco3_sales"]
    hours_yr = sys.operating_hours
    dcf, h2_kg_yr = _dcf_breakdown(sys, result)
    msp_group, msp_type = _msp_tables(dcf, result["msp"])
    capital_msp = float(msp_group.loc[msp_group["cost_type"] == "CAPEX-related", "USD_per_kg_H2"].sum())
    capex_equipment, capex_area = _capex_tables(sys, result, capital_msp)
    opex = _opex_table(sys, result, h2_kg_yr)
    applied = lca.apply_att_gwp(sys, estimates=estimates, overrides=scen.lca_overrides(spec))
    contributions = lca.get_att_gwp_contributions(sys, applied)
    gwp_item, gwp_stage, gwp_total = _gwp_tables(contributions)
    credit = lca.get_att_avoided_emission(sys)
    gwp_item = pd.concat([gwp_item, pd.DataFrame([dict(contributor=lca.AVOIDED_CH4_ITEM, stage="Extra credit (not in net)",
                                                       counted_in_net=False, kgCO2e_per_kg_H2=credit["CH4_extra_kgCO2e_per_kg_H2"],
                                                       share_of_total=credit["CH4_extra_kgCO2e_per_kg_H2"] / gwp_total)])],
                         ignore_index=True)
    t = result["tea"]
    dry = inv._dry_feed_kgph(sys)
    stored_net = lca.get_att_stored_carbon_credit(sys)                     # credit in the net GWP
    stored_with_char = lca.get_att_stored_carbon_credit(sys, include_char=True)
    u2_checks = pd.DataFrame(inv.get_att_u2_balance_checks(sys))
    u2_fail = bool(u2_checks["status"].dropna().astype(str).str.startswith("FAIL").any())
    U2 = inv._units(sys)["U2"]
    summary = dict(scenario=spec["label"], lime=spec["lime"], PSA=spec["psa"], NaOH_kg_per_kg_dry=spec["naoh_kg_per_kg_dry"],
                   U2_balance_status="FAIL (unresolved; see U2_balance_checks)" if u2_fail else "PASS",
                   results_status=("PROVISIONAL (U2 elemental/energy balance unresolved)" if u2_fail else
                                   "PROVISIONAL (assumed U2 residual-product composition and thermo)"
                                   if U2.residual_carbon_fate in ("lumped", "char") else "model result"),
                   U2_residual_product=(f"{U2.residual_carbon_fate}: CH{U2._residual_product_formula['H']:.4g}"
                                        f"O{U2._residual_product_formula['O']:.4g}"
                                        if U2._residual_product_formula else U2.residual_carbon_fate),
                   U2_heat_duty_MJ_per_kg_dry=float(U2._heat_duty_kJph) / 1e3 / dry,
                   CaCO3_sales=("enabled" if sell else "off"),
                   CaCO3_price_USD_per_t=sales_cfg["price_usd_per_metric_ton"] if sell else float("nan"),
                   CaCO3_recovered_t_per_yr=sum(r["caco3_kgph"] for r in sales.values()) * hours_yr / 1e3,
                   CaCO3_sold_t_per_yr=sum(r["sold_caco3_kgph"] for r in sales.values()) * hours_yr / 1e3,
                   CaCO3_sales_revenue_USD_per_yr=sum(r["revenue_usd_ph"] for r in sales.values()) * hours_yr,
                   CaCO3_cake_disposal_USD_per_yr=(sum(r["disposal_usd_ph"] for r in sales.values()) * hours_yr if sell else
                                                   float(opex.loc[opex["group"] == "CaCO3 cake disposal", "MUSD_per_yr"].sum()) * 1e6),
                   NaOH_recycled_t_per_yr=float(inv._streams(sys)["naoh_recycle"].imass["NaOH"]) * sys.operating_hours / 1e3,
                   GWP_stored_carbon_credit_in_net_kgCO2e_per_kg_H2=stored_net,
                   GWP_without_storage_credit_kgCO2e_per_kg_H2=gwp_total - stored_net,
                   GWP_with_provisional_residue_storage_credit_kgCO2e_per_kg_H2=gwp_total - stored_net + stored_with_char,
                   description=spec["label"],
                   fresh_NaOH_t_per_yr=float(inv._streams(sys)["fresh_naoh_solid"].imass["NaOH"]) * sys.operating_hours / 1e3,
                   Ca_OH_2_used_t_per_yr=sum(float(inv._streams(sys)[ID].imass["CaOH2"]) for ID in ("lime", "scrubber_lime")
                                             if ID in inv._streams(sys)) * sys.operating_hours / 1e3,
                   dry_feed_t_per_day=dry * 24 / 1e3,
                   MSP_USD_per_kg_H2=result["msp"], GWP_kgCO2e_per_kg_H2=gwp_total,
                   GWP_avoided_CH4_extra_credit_kgCO2e_per_kg_H2=credit["CH4_extra_kgCO2e_per_kg_H2"],
                   GWP_avoided_emission_total_kgCO2e_per_kg_H2=credit["total_kgCO2e_per_kg_H2"],
                   GWP_with_avoided_CH4_credit_kgCO2e_per_kg_H2=gwp_total + credit["CH4_extra_kgCO2e_per_kg_H2"],
                   H2_t_per_yr=h2_kg_yr / 1e3, FCI_MUSD=t.FCI / 1e6, working_capital_MUSD=t.working_capital / 1e6,
                   TCI_MUSD=t.TCI / 1e6, AOC_MUSD_per_yr=float(opex["MUSD_per_yr"].sum()),
                   capital_related_MSP_USD_per_kg_H2=capital_msp,
                   TEA_VOC_plus_FOC_MUSD_per_yr=(t.VOC + t.FOC) / 1e6)
    return dict(summary=summary, MSP_by_group=msp_group, MSP_by_type=msp_type, CAPEX_by_equipment=capex_equipment,
                CAPEX_by_area=capex_area, OPEX_by_group=opex, GWP_by_contributor=gwp_item, GWP_by_stage=gwp_stage,
                U2_balance_checks=u2_checks)
