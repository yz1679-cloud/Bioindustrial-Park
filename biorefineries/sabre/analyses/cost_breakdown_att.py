# Bioindustrial-Park: BioSTEAM's Premier Biorefinery Models and Results
# Copyright (C) 2026-, Yalin Li <mailto.yalin.li@gmail.com>
#
# This module is under the UIUC open-source license. See
# github.com/BioSTEAMDevelopmentGroup/biosteam/blob/master/LICENSE.txt
# for license details.

"""
cost_breakdown_att.py
----------------------
Breakdown of the ATT H2 minimum selling price and GWP100 at the SaBRe
reference scale (baseline gas closure Gas-C): MSP by cost type and group,
CAPEX by equipment and process area, OPEX by group, and GWP100 by
contributor. The numbers come from ``analyses/att/breakdown.py`` (one
simulation of the baseline; see its docstring for the definitions).

Kept as its own script, like cost_breakdown_3hp.py: the ATT system sets its
own chemical set and must not share a Python process with the other systems.

Outputs (relative to this script's directory):
    ../results/tables/cost_breakdown_att_msp.csv         MSP by group and cost type
    ../results/tables/cost_breakdown_att_capex.csv       installed cost by equipment item
    ../results/tables/cost_breakdown_att_capex_area.csv  installed cost by area + allocated MSP
    ../results/tables/cost_breakdown_att_opex.csv        annual operating cost by group
    ../results/tables/cost_breakdown_att_gwp.csv         GWP100 by contributor and stage
    ../results/tables/cost_breakdown_summary_att.csv     one-row summary
    ../results/figures/fig_cost_breakdown_att.png        MSP / CAPEX / OPEX / GWP panels

Run from the repo root:
    python biorefineries/sabre/analyses/cost_breakdown_att.py
"""

import sys
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from biorefineries.sabre.analyses.att.breakdown import build_att_breakdown

TABLES_OUT = SCRIPT_DIR.parent / "results" / "tables"
FIGURES_OUT = SCRIPT_DIR.parent / "results" / "figures"
TABLES_OUT.mkdir(parents=True, exist_ok=True)
FIGURES_OUT.mkdir(parents=True, exist_ok=True)

# Categorical slots 1-5 in fixed order (dataviz reference palette, light mode).
TYPE_COLORS = {
    "Materials": "#2a78d6",
    "Utilities": "#eb6834",
    "Waste treatment and disposal": "#1baf7a",
    "Fixed operating cost": "#eda100",
    "CAPEX-related": "#e87ba4",
}
EMISSION_COLOR, OFFSET_COLOR = "#6b6a66", "#008300"   # neutral grey; slot 6 green (not a cost-type color)
INK, INK_2, SURFACE, GRID = "#0b0b0b", "#52514e", "#fcfcfb", "#e4e3df"

_SHORT = {
    "Natural gas boiler (LP steam): combustion": "Natural gas, LP steam boiler: combustion",
    "Natural gas boiler (LP steam): upstream supply": "Natural gas, LP steam boiler: upstream",
    "Natural gas U2: combustion": "Natural gas, U2: combustion",
    "Natural gas U2: upstream supply": "Natural gas, U2: upstream",
    "Natural gas displaced by PSA tail gas (burned in U2)": "Natural gas displaced by tail gas",
    "Electricity: outside unit models (agitators, EC1 vacuum)": "Electricity: agitators, EC1 vacuum",
    "Electricity: cooling tower and CW pumps": "Electricity: cooling tower, pumps",
    "Sargassum feedstock (0 in baseline)": "Sargassum (0 in baseline)",
    "PSA off-gas handling (0; fate unresolved)": "PSA off-gas handling (0)",
    "CaCO3 filter cake disposal (TEA Case A)": "CaCO3 cake disposal (Case A)",
    "Fixed operating cost (4 % FCI)": "Fixed operating cost (4 % of FCI)",
    "Capital (FCI + WC, net of loan)": "Capital (FCI + WC, net of loan)",
}


def _style():
    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 10, "axes.titlesize": 11, "axes.labelsize": 10,
        "xtick.labelsize": 9, "ytick.labelsize": 9, "figure.dpi": 150, "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE, "text.color": INK, "axes.labelcolor": INK_2, "xtick.color": INK_2,
        "ytick.color": INK, "axes.edgecolor": GRID, "axes.linewidth": 0.8,
    })


def _hbar(ax, labels, values, colors, label_fmt, xlabel, title, pad=0.18):
    """Horizontal bars, largest on top, direct value labels, no legend box."""
    y = list(range(len(values)))[::-1]
    ax.barh(y, values, color=colors, height=0.62, edgecolor=SURFACE, linewidth=1.5)
    lo, hi = min(0.0, min(values)), max(values)
    span = hi - lo
    for yi, v, text in zip(y, values, label_fmt):
        # Labels sit to the right of the bar end; for a negative bar, to the right of zero.
        ax.text(max(v, 0.0) + 0.012 * span, yi, text, va="center", ha="left", fontsize=8.5, color=INK)
    ax.set_yticks(y)
    ax.set_yticklabels([_SHORT.get(l, l) for l in labels])
    ax.set_xlim(lo - pad * span * (lo < 0), hi + pad * 1.6 * span)
    ax.set_xlabel(xlabel)
    ax.set_title(title, loc="left", color=INK)
    ax.axvline(0, color=INK_2, linewidth=0.8)
    ax.xaxis.grid(True, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.tick_params(axis="y", length=0)


def plot_breakdown(tables, path):
    _style()
    s = tables["summary"]
    fig, axes = plt.subplots(2, 2, figsize=(14.5, 9.2))

    ax = axes[0, 0]
    d = tables["MSP_by_type"]
    _hbar(ax, d["cost_type"], d["USD_per_kg_H2"], [TYPE_COLORS[t] for t in d["cost_type"]],
          [f"{v:.2f}  ({sh:.0%})" for v, sh in zip(d["USD_per_kg_H2"], d["share_of_MSP"])],
          "USD per kg H2 (levelized at the MSP)", f"(a) H2 MSP by cost type (total {s['MSP_USD_per_kg_H2']:.2f} USD/kg)")

    ax = axes[0, 1]
    d = tables["CAPEX_by_area"]
    _hbar(ax, d["area"], d["installed_MUSD"], [TYPE_COLORS["CAPEX-related"]] * len(d),
          [f"{v:.1f}  ({sh:.0%})" for v, sh in zip(d["installed_MUSD"], d["share_of_FCI"])],
          "Installed cost, MUSD", f"(b) CAPEX by process area (FCI {s['FCI_MUSD']:.0f} MUSD)")

    ax = axes[1, 0]
    d = tables["OPEX_by_group"]
    d = d[d["MUSD_per_yr"].abs() > 1e-9]
    _hbar(ax, d["group"], d["MUSD_per_yr"], [TYPE_COLORS[t] for t in d["cost_type"]],
          [f"{v:.1f}  ({sh:.0%})" for v, sh in zip(d["MUSD_per_yr"], d["share_of_AOC"])],
          "MUSD per year", f"(c) OPEX by group (annual operating cost {s['AOC_MUSD_per_yr']:.0f} MUSD/yr)")

    ax = axes[1, 1]
    d = tables["GWP_by_contributor"]
    major = d[d["kgCO2e_per_kg_H2"].abs() >= 0.01 * abs(s["GWP_kgCO2e_per_kg_H2"])]
    rest = d["kgCO2e_per_kg_H2"].sum() - major["kgCO2e_per_kg_H2"].sum()
    labels = list(major["contributor"]) + (["Others"] if abs(rest) > 1e-12 else [])
    values = list(major["kgCO2e_per_kg_H2"]) + ([rest] if abs(rest) > 1e-12 else [])
    shares = [v / s["GWP_kgCO2e_per_kg_H2"] for v in values]
    _hbar(ax, labels, values, [OFFSET_COLOR if v < 0 else EMISSION_COLOR for v in values],
          [f"{v:.1f}  ({sh:.0%})" for v, sh in zip(values, shares)], "kg CO2e per kg H2",
          f"(d) H2 GWP100 by contributor (net {s['GWP_kgCO2e_per_kg_H2']:.1f} kg CO2e/kg)")

    handles = [Patch(facecolor=c, edgecolor=SURFACE, label=t) for t, c in TYPE_COLORS.items()]
    handles += [Patch(facecolor=EMISSION_COLOR, edgecolor=SURFACE, label="GWP: emission"),
                Patch(facecolor=OFFSET_COLOR, edgecolor=SURFACE, label="GWP: natural gas offset")]
    fig.legend(handles=handles, loc="lower center", ncol=7, frameon=False, fontsize=9, labelcolor=INK_2)
    fig.suptitle("ATT H2 (baseline Gas-C, SaBRe reference scale): cost and GWP100 breakdown", fontsize=12,
                 color=INK, x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0.04, 1, 0.96))
    fig.savefig(path, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)


def write_tables(tables):
    names = {"MSP_by_group": "cost_breakdown_att_msp.csv", "CAPEX_by_equipment": "cost_breakdown_att_capex.csv",
             "CAPEX_by_area": "cost_breakdown_att_capex_area.csv", "OPEX_by_group": "cost_breakdown_att_opex.csv",
             "GWP_by_contributor": "cost_breakdown_att_gwp.csv"}
    for key, name in names.items():
        tables[key].to_csv(TABLES_OUT / name, index=False)
    pd.DataFrame([tables["summary"]]).set_index("scenario").to_csv(TABLES_OUT / "cost_breakdown_summary_att.csv")


if __name__ == "__main__":
    tables = build_att_breakdown()
    write_tables(tables)
    plot_breakdown(tables, FIGURES_OUT / "fig_cost_breakdown_att.png")
    print(f"Saved tables to {TABLES_OUT}")
    print(f"Saved figure to {FIGURES_OUT / 'fig_cost_breakdown_att.png'}")
    print("\nATT summary:")
    for k, v in tables["summary"].items():
        print(f"  {k:<36}{v:,.4f}" if isinstance(v, float) else f"  {k:<36}{v}")
    for key in ("MSP_by_type", "CAPEX_by_area", "OPEX_by_group", "GWP_by_stage"):
        print(f"\n{key}:")
        print(tables[key].to_string(index=False, float_format=lambda x: f"{x:,.3f}"))
