# Bioindustrial-Park: BioSTEAM's Premier Biorefinery Models and Results
# Copyright (C) 2026-, Yu Zhou,
#                      Yalin Li <mailto.yalin.li@gmail.com>
#
# This module is under the UIUC open-source license. See
# github.com/BioSTEAMDevelopmentGroup/biosteam/blob/master/LICENSE.txt
# for license details.

"""
att_key_metrics.py
-------------------
Key conversions against theoretical values, material usage, heat duty
waterfalls (by unit operation and by physical origin), low- versus
high-grade heat, external versus internal heat (including the effect of
heat integration) and the energy return on investment of the two ATT
cases (ATT-only and ATT-integration). See ``analyses/att/key_metrics.py``
for the definitions.

Kept as its own script like cost_gwp_breakdown_att.py (the ATT system sets its
own chemical set).

Outputs (relative to this script's directory), each with a ``case`` column:
    ../results/tables/att_key_conversions.csv
    ../results/tables/att_material_usage.csv
    ../results/tables/att_heat_by_unit.csv
    ../results/tables/att_heat_by_origin.csv
    ../results/tables/att_heat_supply_eroi.csv
    ../results/figures/fig_att_heat_by_unit.png
    ../results/figures/fig_att_heat_by_origin.png
    ../results/figures/fig_att_heat_grade_source_eroi.png

Run from the repo root:
    python biorefineries/sabre/analyses/att_key_metrics.py
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

from biorefineries.sabre.analyses.att.key_metrics import CASES, CASE_LABELS, FIGURE_CASES, LIME_LABELS, build_att_key_metrics

TABLES_OUT = SCRIPT_DIR.parent / "results" / "tables"
FIGURES_OUT = SCRIPT_DIR.parent / "results" / "figures"
TABLES_OUT.mkdir(parents=True, exist_ok=True)
FIGURES_OUT.mkdir(parents=True, exist_ok=True)

TEAL, WATER, NEG, TOTAL = "#2f7f8a", "#b0492f", "#5b8c3a", "#1f3a60"     # as in the slides
LOW, HIGH, HXN, TAIL = "#5b9bb8", "#d98a3d", "#9ccf9c", "#2e7d32"
INK, INK_2, SURFACE, GRID = "#0b0b0b", "#52514e", "#fcfcfb", "#e4e3df"
UNIT_LABELS = {"D0": "D0\nfeed dryer", "U2": "U2\nreactor", "C1": "C1\ncausticizing", "EC1": "EC1\nNaOH conc.",
               "U3D": "U3D\ngas dryer", "K1": "K1\nlime kiln"}
SCEN_SHORT = {"No heat integration, tail gas not used": "no integration", "Tail gas burned in U2": "+ tail gas in U2",
              "Tail gas + HXN": "+ tail gas + HXN", "No heat integration": "no integration",
              "Heat integration (HXN)": "with HXN"}


SCEN_COLORS = {"s1": "#2a78d6", "s2": "#eb6834", "s3": "#1c9e5b", "s4": "#8f5bd1"}     # one colour per scenario


def _style():
    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 9.5, "axes.titlesize": 12, "axes.labelsize": 10,
        "figure.dpi": 150, "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "text.color": INK,
        "axes.labelcolor": INK_2, "xtick.color": INK_2, "ytick.color": INK_2, "axes.edgecolor": GRID,
    })


def _waterfall(ax, steps, total, title, note=None, ymax=None, water_steps=()):
    """steps: [(label, value)] in MJ per kg dry seaweed; teal up, green down, red for water_steps, navy total."""
    base = 0.0
    for i, (label, v) in enumerate(steps):
        color = NEG if v < 0 else (WATER if label in water_steps else TEAL)
        lo, hi = (base, base + v) if v >= 0 else (base + v, base)
        ax.bar(i, max(hi - lo, 0.04), bottom=lo, color=color, width=0.62, zorder=3)
        ax.text(i, hi + 0.03 * (ymax or total), f"{v:+.1f}", ha="center", va="bottom", fontsize=9, color=color, weight="bold")
        if i < len(steps):
            ax.plot([i + 0.31, i + 0.69], [base + v, base + v], color="#aaaaaa", lw=0.8, ls="--", zorder=2)
        base += v
    n = len(steps)
    ax.bar(n, total, color=TOTAL, width=0.62, zorder=3)
    ax.text(n, total + 0.03 * (ymax or total), f"{total:.1f}", ha="center", va="bottom", fontsize=10.5, color=TOTAL, weight="bold")
    labels = [s[0] for s in steps] + ["TOTAL"]
    ax.set_xticks(range(n + 1))
    ax.set_xticklabels(labels, fontsize=7.6)
    for i, (label, v) in enumerate(steps):
        ax.text(i, -0.17 * (ymax or total), f"{v / total:.0%}", ha="center", va="top", fontsize=8, color="#888888", transform=ax.transData)
    ax.text(n, -0.17 * (ymax or total), "100%", ha="center", va="top", fontsize=8, color="#555555", weight="bold")
    ax.set_title(title, color=INK, pad=14)
    ax.set_ylim(0, ymax or total * 1.15)
    ax.yaxis.grid(True, color=GRID, lw=0.7, zorder=0)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    if note:
        ax.text(0.03, 0.9, note, transform=ax.transAxes, fontsize=9.5, color=WATER, weight="bold", ha="left", va="top")


def _save(fig, name):
    fig.tight_layout()
    fig.savefig(FIGURES_OUT / name, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)


def plot_by_unit(res):
    _style()
    fig, axes = plt.subplots(2, 2, figsize=(14, 10.5), sharey=True)
    ymax = 1.2 * max(r["heat"]["total"] / r["heat"]["dry"] / 1e3 for r in res.values())
    for ax, (cfg, r) in zip(axes.flat, res.items()):
        h, dry = r["heat"], r["heat"]["dry"]
        steps = [(UNIT_LABELS[k], v / dry / 1e3) for k, v in h["unit"].items()]
        big = sum(v for k, v in h["unit"].items() if k in ("U2", "D0", "EC1")) / h["total"]
        _waterfall(ax, steps, h["total"] / dry / 1e3, CASE_LABELS[cfg], ymax=ymax,
                   note=f"reactor + feed dryer + NaOH concentrator\n= {big:.0%} of the duty")
    for ax in axes[:, 0]:
        ax.set_ylabel("Heating duty before heat integration\n(MJ per kg dry seaweed)")
    fig.suptitle("Heat duty by unit operation: baseline (1) and alternative scenarios (2-4)", fontsize=13, x=0.01, ha="left", color=INK)
    _save(fig, "fig_att_heat_by_unit.png")


def plot_by_origin(res):
    _style()
    fig, axes = plt.subplots(2, 2, figsize=(18, 11.5), sharey=True)
    ymax = 1.2 * max(r["heat"]["total"] / r["heat"]["dry"] / 1e3 for r in res.values())
    short = {"Reaction enthalpy (U2)": "Reaction\nenthalpy", "NaOH heat of solution (not recovered)": "NaOH heat\nof solution",
             "Water heating and vaporization (U2)": "Water vap.\nreactor", "Sensible heat of solids and NaOH (U2)": "Sensible\nheat (U2)",
             "Water evaporation, feed dryer (D0)": "Water evap.\nfeed dryer", "Sensible heat in the dryer (D0)": "Sensible\nheat (D0)",
             "Causticizing (C1)": "Causti-\ncizing", "Water evaporation, NaOH concentrator (EC1)": "Water evap.\nNaOH conc.",
             "Gas-drying regeneration (U3D)": "Gas dryer\nregen.", "Heat losses": "Heat\nlosses",
             "Lime kiln: calcination and cake drying (K1)": "Lime kiln\n(K1)"}
    water = [short[k] for k in short if k.startswith("Water")]
    for ax, (cfg, r) in zip(axes.flat, res.items()):
        h, dry = r["heat"], r["heat"]["dry"]
        steps = [(short[k], v[0] / dry / 1e3) for k, v in h["origin"].items()]
        share = h["water_handling"] / h["total"]
        _waterfall(ax, steps, h["total"] / dry / 1e3, CASE_LABELS[cfg], ymax=ymax, water_steps=water,
                   note=f"water handling = {share:.0%}\nof the heat duty")
    for ax in axes[:, 0]:
        ax.set_ylabel("Heating duty before heat integration\n(MJ per kg dry seaweed)")
    fig.suptitle("Heat duty by physical origin: baseline (1) and alternative scenarios (2-4)", fontsize=13, x=0.01, ha="left", color=INK)
    _save(fig, "fig_att_heat_by_origin.png")


def plot_grade_source(res):
    _style()
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(14.5, 5.8), gridspec_kw=dict(width_ratios=[1.5, 1]))
    rows = []
    for cfg, r in res.items():
        for sc in r["scenarios"]:
            rows.append((cfg, sc, r["scenarios"][sc], r["heat"]["dry"]))
    ys = list(range(len(rows)))[::-1]
    for y, (cfg, sc, d, dry) in zip(ys, rows):
        parts = [("external low-grade", d["ext_low"], LOW, None), ("external high-grade", d["ext_high"], HIGH, None),
                 ("internal: HXN-recovered", d["int_hxn"], HXN, "//"), ("internal: PSA tail gas", d["int_tail"], TAIL, "//")]
        left = 0.0
        for lab, v, c, hatch in parts:
            v = v / dry / 1e3
            if v <= 0:
                continue
            ax.barh(y, v, left=left, color=c, edgecolor="white", hatch=hatch, height=0.62)
            if v > 0.9:
                ax.text(left + v / 2, y, f"{v:.1f}", ha="center", va="center", fontsize=8.5, color="white", weight="bold")
            left += v
        ax.text(left + 0.2, y, f"external {d['ext_total'] / dry / 1e3:.1f}", va="center", fontsize=9, color=INK)
    ax.set_yticks(ys)
    ax.set_yticklabels([f"{LIME_LABELS[c]}\n{SCEN_SHORT[s]}" for c, s, _, _ in rows], fontsize=8.5)
    ax.set_xlabel("Heat demand by supply (MJ per kg dry seaweed)")
    ax.set_title("External versus internal heat, low- versus high-grade", loc="left", color=INK)
    fig.legend(handles=[Patch(facecolor=LOW, label="external, low-grade (<= 100 C)"), Patch(facecolor=HIGH, label="external, high-grade (> 100 C)"),
                        Patch(facecolor=HXN, hatch="//", edgecolor="white", label="internal: recovered by the HXN"),
                        *([Patch(facecolor=TAIL, hatch="//", edgecolor="white", label="internal: PSA tail gas (from the biomass)")]
                          if any(d["int_tail"] > 0 for r in res.values() for d in r["scenarios"].values()) else []),
                        *[Patch(facecolor=SCEN_COLORS[c], label="EROI: " + CASE_LABELS[c]) for c in res]],
               loc="lower center", ncol=2, frameon=False, fontsize=8.8)
    ax.xaxis.grid(True, color=GRID, lw=0.7); ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    colors = SCEN_COLORS
    for y, (cfg, sc, d, dry) in zip(ys, rows):
        ax2.barh(y, d["EROI_heat_delivered"], color=colors[cfg], height=0.62)
        ax2.text(d["EROI_heat_delivered"] + 0.015, y, f"{d['EROI_heat_delivered']:.2f}", va="center", fontsize=9)
    ax2.axvline(1.0, color=INK_2, ls="--", lw=0.9)
    ax2.text(1.0, ys[0] + 0.55, "break-even", ha="right", fontsize=8, color=INK_2, style="italic")
    ax2.set_yticks(ys); ax2.set_yticklabels([])
    ax2.set_xlim(0, 1.15)
    ax2.set_xlabel("EROI = H2 LHV out / external heat in")
    ax2.set_title("Energy return on investment", loc="left", color=INK)
    ax2.xaxis.grid(True, color=GRID, lw=0.7); ax2.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax2.spines[side].set_visible(False)
    fig.suptitle("Heat supply, heat integration and energy return: baseline (1) and alternative scenarios (2-4)", fontsize=13, x=0.01, ha="left", color=INK)
    fig.tight_layout(rect=(0, 0.13, 1, 0.97))
    fig.savefig(FIGURES_OUT / "fig_att_heat_grade_source_eroi.png", bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)


def write_tables(res):
    def cat(frames):
        return pd.concat([f.assign(case=c) for c, f in frames.items()], ignore_index=True).pipe(
            lambda d: d[["case"] + [x for x in d.columns if x != "case"]])
    cat({c: pd.DataFrame(r["conversions"]) for c, r in res.items()}).to_csv(TABLES_OUT / "att_key_conversions.csv", index=False)
    cat({c: pd.DataFrame(r["materials"]) for c, r in res.items()}).to_csv(TABLES_OUT / "att_material_usage.csv", index=False)
    unit_rows, origin_rows, supply_rows = {}, {}, {}
    for c, r in res.items():
        h, dry = r["heat"], r["heat"]["dry"]
        unit_rows[c] = pd.DataFrame([dict(unit=k, MJ_per_kg_dry=v / dry / 1e3, share=v / h["total"]) for k, v in h["unit"].items()]
                                    + [dict(unit="TOTAL", MJ_per_kg_dry=h["total"] / dry / 1e3, share=1.0)])
        origin_rows[c] = pd.DataFrame([dict(origin=k, MJ_per_kg_dry=v / dry / 1e3, low_grade_MJ_per_kg_dry=lo / dry / 1e3,
                                            high_grade_MJ_per_kg_dry=(v - lo) / dry / 1e3, share=v / h["total"]) for k, (v, lo) in h["origin"].items()]
                                      + [dict(origin="TOTAL", MJ_per_kg_dry=h["total"] / dry / 1e3, low_grade_MJ_per_kg_dry=h["low"] / dry / 1e3,
                                              high_grade_MJ_per_kg_dry=h["high"] / dry / 1e3, share=1.0),
                                         dict(origin="Dissolution (D1) Na2CO3 heat of solution: ESTIMATE, not in the model",
                                              MJ_per_kg_dry=h["dissolution_estimate_kJph"] / dry / 1e3)])
        supply_rows[c] = pd.DataFrame([dict(scenario=s, demand_MJ_per_kg_dry=h["total"] / dry / 1e3,
                                            external_low_grade=d["ext_low"] / dry / 1e3, external_high_grade=d["ext_high"] / dry / 1e3,
                                            external_total=d["ext_total"] / dry / 1e3, internal_HXN_recovered=d["int_hxn"] / dry / 1e3,
                                            internal_tail_gas=d["int_tail"] / dry / 1e3, EROI_H2_LHV_over_external_heat=d["EROI_heat_delivered"],
                                            EROI_H2_LHV_over_primary_fuel=d["EROI_fuel"],
                                            EROI_H2_LHV_over_fuel_plus_electricity=d["EROI_fuel_plus_electricity"])
                                       for s, d in r["scenarios"].items()])
    cat(unit_rows).to_csv(TABLES_OUT / "att_heat_by_unit.csv", index=False)
    cat(origin_rows).to_csv(TABLES_OUT / "att_heat_by_origin.csv", index=False)
    cat(supply_rows).to_csv(TABLES_OUT / "att_heat_supply_eroi.csv", index=False)


if __name__ == "__main__":
    res = build_att_key_metrics()                      # the four scenarios of analyses/att/scenarios.py
    write_tables(res)
    plot_by_unit(res)
    plot_by_origin(res)
    plot_grade_source(res)
    print(f"Saved tables to {TABLES_OUT} and figures to {FIGURES_OUT}")
