# Bioindustrial-Park: BioSTEAM's Premier Biorefinery Models and Results
# Copyright (C) 2026-, Yu Zhou,
#                      Yalin Li <mailto.yalin.li@gmail.com>
#
# This module is under the UIUC open-source license. See
# github.com/BioSTEAMDevelopmentGroup/biosteam/blob/master/LICENSE.txt
# for license details.

"""
cost_gwp_breakdown_att.py
----------------------
Breakdown of the ATT H2 minimum selling price and GWP100 for the baseline
(scenario 1: presscake feed, NaOH 1 g/g, PSA, fresh lime, NLR scale) and the
alternative scenarios 2-4 (recycled lime; waste lime; waste lime with full CO2
capture and no PSA) of ``analyses/att/scenarios.py``. MSP by cost type and group, CAPEX by equipment and process area,
OPEX by group, and GWP100 by contributor. The numbers come from
``analyses/att/breakdown.py`` (one simulation per scenario; see its docstring
for the definitions).

Kept as its own script, like cost_breakdown_3hp.py: the ATT system sets its
own chemical set and must not share a Python process with the other systems.

Outputs (relative to this script's directory), each with a ``case`` column:
    ../results/tables/cost_breakdown_att_msp.csv         MSP by group and cost type
    ../results/tables/cost_breakdown_att_capex.csv       installed cost by equipment item
    ../results/tables/cost_breakdown_att_capex_area.csv  installed cost by area + allocated MSP
    ../results/tables/cost_breakdown_att_opex.csv        annual operating cost by group
    ../results/tables/cost_breakdown_att_gwp.csv         GWP100 by contributor
    ../results/tables/cost_breakdown_att_u2_checks.csv   U2 balance checks
    ../results/tables/cost_breakdown_summary_att.csv     one row per case
    ../results/figures/fig_cost_gwp_breakdown_att.png        MSP / CAPEX / OPEX / GWP panels

Run from the repo root:
    python biorefineries/sabre/analyses/cost_gwp_breakdown_att.py
"""

import sys
import textwrap
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from biorefineries.sabre.analyses.att.breakdown import CASES, CASE_LABELS, FIGURE_CASES, build_att_breakdown

TABLES_OUT = SCRIPT_DIR.parent / "results" / "tables"
FIGURES_OUT = SCRIPT_DIR.parent / "results" / "figures"
TABLES_OUT.mkdir(parents=True, exist_ok=True)
FIGURES_OUT.mkdir(parents=True, exist_ok=True)

# One color per case (categorical slots 1-2, dataviz reference palette, light mode).
CASE_COLORS = {"s1": "#2a78d6", "s2": "#eb6834", "s3": "#1c9e5b", "s4": "#8f5bd1", "s5": "#c49a14"}
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
    "Biogenic carbon stored in landfilled solids (credit)": "Stored biogenic carbon (landfilled solids)",
    "CaCO3 cake disposal": "CaCO3 cake disposal (fresh-lime case)",
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


def _grouped_hbar(ax, frames, label_col, value_col, label_fmt, xlabel, title, min_abs=0.0):
    """Horizontal bars, one per case within each category, largest category on top."""
    cats = {}
    for case, d in frames.items():
        for lab, v in zip(d[label_col], d[value_col]):
            cats.setdefault(lab, {})[case] = v
    cats = {k: v for k, v in cats.items() if max(abs(x) for x in v.values()) > min_abs}
    order = sorted(cats, key=lambda k: max(cats[k].values()), reverse=True)
    h = 0.8 / len(frames)
    allv = [x for k in cats for x in cats[k].values()]
    span = max(abs(x) for x in allv) if allv else 1.0
    lo = min([0.0] + allv)
    for i, lab in enumerate(order):
        y0 = len(order) - 1 - i
        for j, case in enumerate(frames):
            if case not in cats[lab]:
                continue
            v = cats[lab][case]
            y = y0 + 0.4 - h * (j + 0.5)
            ax.barh(y, v, height=h * 0.9, color=CASE_COLORS[case], edgecolor=SURFACE, linewidth=1.0)
            ax.text(max(v, 0.0) + 0.012 * span, y, label_fmt(v), va="center", ha="left", fontsize=6.8, color=INK)
    ax.set_yticks(range(len(order)))
    ax.set_yticklabels([_SHORT.get(l, l) for l in order[::-1]])
    ax.set_xlim(lo * 1.2 if lo < 0 else 0, span * 1.22)
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
    summ = {c: t["summary"] for c, t in tables.items()}
    fig, axes = plt.subplots(2, 2, figsize=(17, 15))
    both = lambda f: " / ".join(f(s) for s in summ.values())

    _grouped_hbar(axes[0, 0], {c: t["MSP_by_type"] for c, t in tables.items()}, "cost_type", "USD_per_kg_H2",
                  lambda v: f"{v:.2f}", "USD per kg H2 (levelized at the MSP)",
                  "(a) H2 MSP by cost type (" + both(lambda s: f"{s['MSP_USD_per_kg_H2']:.2f}") + " USD/kg)")
    _grouped_hbar(axes[0, 1], {c: t["CAPEX_by_area"] for c, t in tables.items()}, "area", "installed_MUSD",
                  lambda v: f"{v:.1f}", "Installed cost, MUSD",
                  "(b) CAPEX by process area (FCI " + both(lambda s: f"{s['FCI_MUSD']:.0f}") + " MUSD)")
    _grouped_hbar(axes[1, 0], {c: t["OPEX_by_group"] for c, t in tables.items()}, "group", "MUSD_per_yr",
                  lambda v: f"{v:.1f}", "MUSD per year",
                  "(c) OPEX by group (annual operating cost " + both(lambda s: f"{s['AOC_MUSD_per_yr']:.0f}") + " MUSD/yr)",
                  min_abs=1e-9)
    _grouped_hbar(axes[1, 1], {c: t["GWP_by_contributor"].query("counted_in_net") for c, t in tables.items()},
                  "contributor", "kgCO2e_per_kg_H2",
                  lambda v: f"{v:.1f}", "kg CO2e per kg H2",
                  "(d) H2 GWP100 by contributor (net " + both(lambda s: f"{s['GWP_kgCO2e_per_kg_H2']:.1f}") + " kg CO2e/kg)",
                  min_abs=0.01 * max(abs(s["GWP_kgCO2e_per_kg_H2"]) for s in summ.values()))
    avoided = " / ".join(f"{s['GWP_avoided_emission_total_kgCO2e_per_kg_H2']:.1f}" for s in summ.values())
    stored = " / ".join(f"{s['GWP_avoided_emission_total_kgCO2e_per_kg_H2'] - s['GWP_avoided_CH4_extra_credit_kgCO2e_per_kg_H2']:.1f}"
                        for s in summ.values())
    note = textwrap.fill(f"Net includes the stored carbon ({stored}). Avoided emission if rotted on the beach: {avoided} kg CO2e/kg H2 "
                         "(stored CO2 + avoided CH4, net of its CO2; not in the net)", width=95)
    axes[1, 1].set_title(axes[1, 1].get_title(loc="left"), loc="left", color=INK, pad=8 + 11.5 * len(note.splitlines()))
    axes[1, 1].text(0.0, 1.012, note, transform=axes[1, 1].transAxes, ha="left", va="bottom", fontsize=8, color=INK_2)

    handles = [Patch(facecolor=CASE_COLORS[c], edgecolor=SURFACE, label=CASE_LABELS[c]) for c in tables]
    fig.legend(handles=handles, loc="lower center", ncol=2, frameon=False, fontsize=9.5, labelcolor=INK_2)
    fig.suptitle("ATT H2: cost and GWP100 breakdown, baseline (1) and alternative scenarios (2-4)",
                 fontsize=12, color=INK, x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0.06, 1, 0.96))
    fig.savefig(path, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)


def write_tables(tables):
    names = {"MSP_by_group": "cost_breakdown_att_msp.csv", "CAPEX_by_equipment": "cost_breakdown_att_capex.csv",
             "CAPEX_by_area": "cost_breakdown_att_capex_area.csv", "OPEX_by_group": "cost_breakdown_att_opex.csv",
             "GWP_by_contributor": "cost_breakdown_att_gwp.csv", "U2_balance_checks": "cost_breakdown_att_u2_checks.csv"}
    for key, name in names.items():
        columns = ["case"] + list(next(iter(tables.values()))[key].columns)
        pd.concat([t[key].assign(case=c) for c, t in tables.items()], ignore_index=True)[columns].to_csv(
            TABLES_OUT / name, index=False)
    pd.DataFrame([dict(case=c, **t["summary"]) for c, t in tables.items()]).set_index("case").to_csv(
        TABLES_OUT / "cost_breakdown_summary_att.csv")


if __name__ == "__main__":
    tables = {c: build_att_breakdown(c) for c in CASES}     # the four scenarios of analyses/att/scenarios.py
    write_tables(tables)
    plot_breakdown(tables, FIGURES_OUT / "fig_cost_gwp_breakdown_att.png")
    print(f"Saved tables to {TABLES_OUT}")
    print(f"Saved figure to {FIGURES_OUT / 'fig_cost_gwp_breakdown_att.png'}")
    for c, t in tables.items():
        print(f"\n=== {CASE_LABELS[c]} ===")
        for k, v in t["summary"].items():
            print(f"  {k:<36}{v:,.4f}" if isinstance(v, float) else f"  {k:<36}{v}")
        for key in ("MSP_by_type", "CAPEX_by_area", "OPEX_by_group", "GWP_by_stage"):
            print(f"\n{key}:")
            print(t[key].to_string(index=False, float_format=lambda x: f"{x:,.3f}"))
