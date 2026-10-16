"""
Breakdown of the ATT H2 minimum selling price (MSP) and GWP100 at the SaBRe
reference scale, for the baseline gas closure (Gas-C, uniform_redox_scaling).

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

Reuses att.scenarios (one simulation of Gas-C); nothing is recomputed here.
Written by ``analyses/cost_breakdown_att.py`` to ``results/tables`` and
``results/figures``.
"""
import pandas as pd

from biorefineries.sabre.analyses.att import final as fin
from biorefineries.sabre.analyses.att import scenarios as scn

__all__ = ("build_att_breakdown", "COST_TYPES")

# Cost groups of att.scenarios._cost_group -> cost type.
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
    "CaCO3 filter cake disposal (TEA Case A)": "Waste treatment and disposal",
    "PSA off-gas handling (0; fate unresolved)": "Waste treatment and disposal",
    "Fixed operating cost (4 % FCI)": "Fixed operating cost",
    "Capital (FCI + WC, net of loan)": "CAPEX-related",
    "Financing (debt service)": "CAPEX-related",
    "Income tax": "CAPEX-related",
}
_OPEX_TYPES = ("Materials", "Utilities", "Waste treatment and disposal", "Fixed operating cost")
_FCI_ROW = "Installed equipment cost = DPI = TDC = FCI"


def _msp_tables(R):
    rows = {}
    for r in R["dcf"]:
        if r["group"] == "Solver residual":
            continue
        rows[r["group"]] = rows.get(r["group"], 0.0) + r["USD_per_kg_H2"]
    msp = R["msp"]
    by_group = pd.DataFrame(
        [dict(group=g, cost_type=COST_TYPES[g], USD_per_kg_H2=v, share_of_MSP=v / msp) for g, v in rows.items()]
    ).sort_values(["cost_type", "USD_per_kg_H2"], ascending=[True, False]).reset_index(drop=True)
    by_type = by_group.groupby("cost_type", as_index=False)[["USD_per_kg_H2", "share_of_MSP"]].sum()
    by_type = by_type.sort_values("USD_per_kg_H2", ascending=False).reset_index(drop=True)
    return by_group, by_type


def _capex_tables(R, capital_msp):
    fci = R["tea_totals"]["FCI"]
    rows = []
    for x in R["capex"]:
        if x["item"].startswith(("Installed equipment cost", "Working capital", "Total capital")):
            continue
        first = x["item"].split()[0].rstrip(":")
        area = scn._AREAS.get("U3P" if first == "PSA" else first, "Other")
        if x["installed_cost"]:
            rows.append(dict(item=x["item"], area=area, installed_MUSD=x["installed_cost"] / 1e6,
                             share_of_FCI=x["installed_cost"] / fci))
    equipment = pd.DataFrame(rows).sort_values("installed_MUSD", ascending=False).reset_index(drop=True)
    areas = equipment.groupby("area", as_index=False)[["installed_MUSD", "share_of_FCI"]].sum()
    areas["capital_related_MSP_USD_per_kg_H2"] = areas["share_of_FCI"] * capital_msp
    areas = areas.sort_values("installed_MUSD", ascending=False).reset_index(drop=True)
    return equipment, areas


def _opex_table(R, h2_kg_yr):
    groups = {}
    for x in R["opex_table"]:
        if x["category"] in ("capital", "total"):
            continue
        g = scn._cost_group(x["item"], x["category"])
        groups[g] = groups.get(g, 0.0) + x["USD_per_yr"]
    aoc = sum(groups.values())
    df = pd.DataFrame([dict(group=g, cost_type=COST_TYPES[g], MUSD_per_yr=v / 1e6, USD_per_kg_H2=v / h2_kg_yr,
                            share_of_AOC=v / aoc) for g, v in groups.items()])
    return df.sort_values("MUSD_per_yr", ascending=False).reset_index(drop=True)


def _gwp_tables(R):
    rows = [r for r in R["gwp"] if not r["item"].startswith("TOTAL")]
    total = R["gwp"][-1]["GWP_kgCO2e_per_kg_H2"]
    by_item = pd.DataFrame([dict(contributor=r["item"], stage=r["stage"], kgCO2e_per_kg_H2=r["GWP_kgCO2e_per_kg_H2"],
                                 share_of_total=r["GWP_kgCO2e_per_kg_H2"] / total) for r in rows])
    by_item = by_item.sort_values("kgCO2e_per_kg_H2", ascending=False).reset_index(drop=True)
    by_stage = by_item.groupby("stage", as_index=False)[["kgCO2e_per_kg_H2", "share_of_total"]].sum()
    by_stage = by_stage.sort_values("kgCO2e_per_kg_H2", ascending=False).reset_index(drop=True)
    return by_item, by_stage, total


def build_att_breakdown():
    """One simulation of the baseline (Gas-C); returns a dict of DataFrames and a summary dict."""
    label, method, note = fin.GAS_SCENARIOS[0]
    R = scn._evaluate(label, method, note)
    h2_kg_yr = R["dcf_basis"]["h2_kg_yr"]
    msp_group, msp_type = _msp_tables(R)
    capital_msp = float(msp_group.loc[msp_group["cost_type"] == "CAPEX-related", "USD_per_kg_H2"].sum())
    capex_equipment, capex_area = _capex_tables(R, capital_msp)
    opex = _opex_table(R, h2_kg_yr)
    gwp_item, gwp_stage, gwp_total = _gwp_tables(R)
    t = R["tea_totals"]
    summary = dict(scenario=label, closure=method, MSP_USD_per_kg_H2=R["msp"], GWP_kgCO2e_per_kg_H2=gwp_total,
                   H2_t_per_yr=h2_kg_yr / 1e3, FCI_MUSD=t["FCI"] / 1e6, working_capital_MUSD=t["WC"] / 1e6,
                   TCI_MUSD=t["TCI"] / 1e6, AOC_MUSD_per_yr=float(opex["MUSD_per_yr"].sum()),
                   TEA_VOC_plus_FOC_MUSD_per_yr=(t["VOC"] + t["FOC"]) / 1e6,
                   capital_related_MSP_USD_per_kg_H2=capital_msp)
    return dict(summary=summary, MSP_by_group=msp_group, MSP_by_type=msp_type, CAPEX_by_equipment=capex_equipment,
                CAPEX_by_area=capex_area, OPEX_by_group=opex, GWP_by_contributor=gwp_item, GWP_by_stage=gwp_stage)
