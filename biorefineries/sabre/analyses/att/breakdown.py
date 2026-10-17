# Bioindustrial-Park: BioSTEAM's Premier Biorefinery Models and Results
# Copyright (C) 2026-, Yu Zhou,
#                      Yalin Li <mailto.yalin.li@gmail.com>
#
# This module is under the UIUC open-source license. See
# github.com/BioSTEAMDevelopmentGroup/biosteam/blob/master/LICENSE.txt
# for license details.

"""
Breakdown of the ATT H2 minimum selling price (MSP) and GWP100 at the SaBRe
reference scale for the two cases:

* ``att_only``   ATT plant fed with wet Sargassum (NLR scale: 3 million wet t/yr): P1 press
                 (municipal biosolids screw press), D0 dryer and the ATT
                 process; the press liquid is the raw juice for biostimulant
                 production (transferred at zero price).
* ``integrated`` ATT plant fed with the presscake of a biostimulant plant
                 (normally a waste), without P1.

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

Written by ``analyses/cost_breakdown_att.py`` to ``results/tables`` and
``results/figures``.
"""
import numpy as np
import pandas as pd

from biorefineries.sabre.analyses.att import inventory as inv
from biorefineries.sabre.analyses.att import lca
from biorefineries.sabre.analyses.att import tea as tea_mod

__all__ = ("build_att_breakdown", "COST_TYPES", "CONFIGURATIONS", "CASES", "FIGURE_CASES", "CASE_LABELS", "LIME_LABELS")

# (configuration, lime_recycle) per case. ATT-only is kept, but the figures compare fresh vs recycled lime
# in the ATT-integration configuration (FIGURE_CASES).
CASES = {
    "integrated_fresh": ("integrated", False),
    "integrated_recycled": ("integrated", True),
    "att_only_fresh": ("att_only", False),
    "att_only_recycled": ("att_only", True),
}
FIGURE_CASES = ("integrated_fresh", "integrated_recycled")
CASE_LABELS = {
    "integrated_fresh": "ATT-integration, fresh Ca(OH)2 (cake disposed)",
    "integrated_recycled": "ATT-integration, recycled lime (kiln + slaker)",
    "att_only_fresh": "ATT-only, fresh Ca(OH)2 (cake disposed)",
    "att_only_recycled": "ATT-only, recycled lime (kiln + slaker)",
}
LIME_LABELS = {"integrated_fresh": "Fresh Ca(OH)2", "integrated_recycled": "Recycled lime",
               "att_only_fresh": "Fresh Ca(OH)2", "att_only_recycled": "Recycled lime"}
CONFIGURATIONS = {
    "att_only": "ATT-only (wet Sargassum)",
    "integrated": "ATT-integration (presscake)",
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
    "C1": "Causticization (C1)", "F2": "CaCO3 filtration (F2)", "SP1": "Liquor split (SP1)",
    "EC1": "NaOH evaporation (EC1)", "K1": "Lime kiln (K1)", "S1": "Lime slaking (S1)",
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
                          ("CaCO3 cake", "CaCO3 cake disposal"),
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
        elif r["category"] in ("waste disposal", "CaCO3 cake", "off-gas", "juice"):
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


def build_att_breakdown(configuration="integrated", lime_recycle=True):
    """
    One simulation of a case; returns a dict of DataFrames and a summary dict.

    lime_recycle False buys all the Ca(OH)2 and disposes of the CaCO3 cake at the solid-waste price
    (TEA Case A: the 520 kt/yr cake has to go somewhere); True recycles the lime through the kiln.
    """
    sys = tea_mod.create_att_tea_system(configuration, lime_recycle=lime_recycle)
    estimates = inv.get_att_cost_estimates(sys)
    result = tea_mod.evaluate_att_tea(sys, estimates, caco3=None if lime_recycle else dict(fraction=0.0))
    dcf, h2_kg_yr = _dcf_breakdown(sys, result)
    msp_group, msp_type = _msp_tables(dcf, result["msp"])
    capital_msp = float(msp_group.loc[msp_group["cost_type"] == "CAPEX-related", "USD_per_kg_H2"].sum())
    capex_equipment, capex_area = _capex_tables(sys, result, capital_msp)
    opex = _opex_table(sys, result, h2_kg_yr)
    applied = lca.apply_att_gwp(sys, estimates=estimates)
    contributions = lca.get_att_gwp_contributions(sys, applied)
    gwp_item, gwp_stage, gwp_total = _gwp_tables(contributions)
    credit = lca.get_att_landfill_credit(sys)
    gwp_item = pd.concat([gwp_item, pd.DataFrame([dict(contributor=lca.LANDFILL_CREDIT_ITEM, stage="Potential credit (not in net)",
                                                       counted_in_net=False, kgCO2e_per_kg_H2=credit["GWP_kgCO2e_per_kg_H2"],
                                                       share_of_total=credit["GWP_kgCO2e_per_kg_H2"] / gwp_total)])],
                         ignore_index=True)
    t = result["tea"]
    dry = inv._dry_feed_kgph(sys)
    summary = dict(configuration=configuration, lime="recycled" if lime_recycle else "fresh",
                   description=CONFIGURATIONS[configuration] + ", " + ("recycled lime" if lime_recycle else "fresh lime"),
                   dry_feed_t_per_day=dry * 24 / 1e3,
                   MSP_USD_per_kg_H2=result["msp"], GWP_kgCO2e_per_kg_H2=gwp_total,
                   GWP_landfill_credit_kgCO2e_per_kg_H2=credit["GWP_kgCO2e_per_kg_H2"],
                   GWP_with_landfill_credit_kgCO2e_per_kg_H2=gwp_total + credit["GWP_kgCO2e_per_kg_H2"],
                   H2_t_per_yr=h2_kg_yr / 1e3, FCI_MUSD=t.FCI / 1e6, working_capital_MUSD=t.working_capital / 1e6,
                   TCI_MUSD=t.TCI / 1e6, AOC_MUSD_per_yr=float(opex["MUSD_per_yr"].sum()),
                   capital_related_MSP_USD_per_kg_H2=capital_msp,
                   TEA_VOC_plus_FOC_MUSD_per_yr=(t.VOC + t.FOC) / 1e6)
    return dict(summary=summary, MSP_by_group=msp_group, MSP_by_type=msp_type, CAPEX_by_equipment=capex_equipment,
                CAPEX_by_area=capex_area, OPEX_by_group=opex, GWP_by_contributor=gwp_item, GWP_by_stage=gwp_stage,
                U2_balance_checks=pd.DataFrame(inv.get_att_u2_balance_checks(sys)))
