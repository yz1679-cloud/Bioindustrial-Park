# Bioindustrial-Park: BioSTEAM's Premier Biorefinery Models and Results
# Copyright (C) 2026-, Yu Zhou,
#                      Yalin Li <mailto.yalin.li@gmail.com>
#
# This module is under the UIUC open-source license. See
# github.com/BioSTEAMDevelopmentGroup/biosteam/blob/master/LICENSE.txt
# for license details.

"""
att_s2_marine.py
----------------
ATT Scenario 2 (shipboard ATT with marine waste heat recovery): heat source and sink ledgers, allocation, WHR
equipment, energy performance and load sensitivity, the S1/S2 TEA comparison for Mode A (7920 h underway,
idealized) and Mode B (8 h/d underway = 2640 h), floating-cost / heat / hours sensitivities, incremental GWP and
the accounting checks. One simulation of the (unchanged) ATT S1 process at its capacity.

Outputs: biorefineries/ATT/results/tables/att_s2_*.csv (root: paths.results_root)

Run from the repo root:
    python biorefineries/ATT/analyses/att_s2_marine.py
"""
import sys
import warnings
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from biorefineries.ATT.analyses import marine_tea as mt
from biorefineries.ATT.analyses import marine_whr as mw
from biorefineries.ATT.analyses import scenarios as scen
from biorefineries.ATT.analyses.paths import output_dir

OUT = output_dir("tables")
ALL = ("jacket", "scavenge", "exhaust")
CASES = (("S2 floating, no WHR", ()), ("S2 floating, exhaust WHR", ("exhaust",)),
         ("S2 floating, exhaust + scavenge + jacket WHR", ALL))


def mode_tea_cases(system, ref, cfg=None):
    """S2 TEA cases of each operating mode (marine_whr.yaml), each at its own hours AND engine load."""
    rows = []
    for mode, hours, load in mt.operating_modes(cfg):
        for name, src in CASES:
            row, _ = mt.evaluate_case(system, ref, name, sources=src, hours=hours, load=load)
            rows.append(dict(row, mode=mode, engine_load=load))
    return rows


def run():
    warnings.filterwarnings("ignore")
    cfg = mw.load_whr_config()
    system = scen.create(scen.ATT_S2)            # identical process to ATT S1
    tables = {}

    whr = mw.evaluate_whr(system)
    tables["heat_sources"] = pd.DataFrame(whr["sources"])
    tables["heat_sinks"] = pd.DataFrame(whr["sinks"])
    tables["heat_allocation"] = pd.DataFrame(whr["assignments"])
    tables["whr_equipment"] = pd.DataFrame(whr["equipment"], columns=["item", "installed_USD", "basis"])
    tables["checks"] = pd.DataFrame(mw.check_whr(whr))

    # Energy performance and engine-load sensitivity (Mode A process rate)
    perf = []
    U2 = next(k for k in whr["sinks"] if k["unit"].startswith("U2 (500"))
    for load in (0.15, 0.50, 0.75, 1.00):
        w = whr if load == 0.75 else mw.evaluate_whr(system, load=load)
        gross = sum(s["gross_kW"] for s in w["sources"])
        perf.append(dict(engine_load=load, gross_waste_heat_kW=gross,
                         recoverable_kW=sum(s["recoverable_kW"] for s in w["sources"]),
                         delivered_kW=sum(s["delivered_kW"] for s in w["sources"]), utilized_kW=w["utilized_kW"],
                         unutilized_delivered_kW=sum(s["delivered_kW"] for s in w["sources"]) - w["utilized_kW"],
                         external_heating_before_kW=w["external_before_kW"], external_heating_after_kW=w["external_after_kW"],
                         external_heating_reduction=w["utilized_kW"] / w["external_before_kW"],
                         purchased_steam_reduction=sum(a["assigned_kW"] for a in w["assignments"] if "steam" in a["sink_utility"])
                         / sum(k["purchased_kW"] for k in w["sinks"] if "steam" in k["utility"]),
                         WHR_pump_kW=w["pump_kW"], U2_fired_duty_kW=U2["purchased_before_hxn_kW"]))
    tables["energy_performance"] = pd.DataFrame(perf)

    # TEA: S1 land and S2 cases, Mode A and Mode B
    ref = mt.land_reference(system)
    rows = [dict(ref["row"], mode="land reference")] + mode_tea_cases(system, ref, cfg)
    tables["tea_cases"] = pd.DataFrame(rows)

    # Sensitivities (S2 with all sources unless stated; Mode A hours unless stated)
    tc = mt.load_tea_config()
    sens = []

    def case(label, **kw):
        row, w = mt.evaluate_case(system, ref, label, **kw)
        sens.append(row)
        return w

    base = case("baseline: x1.25 CAPEX, x2 labor, all WHR, 7920 h", sources=ALL)
    for m in tc["capex_multiplier_sensitivity"]:
        case(f"CAPEX multiplier {m:g}", sources=ALL, capex_multiplier=m)
    for m in tc["labor_multiplier_sensitivity"]:
        case(f"labor multiplier {m:g}", sources=ALL, labor_multiplier=m)
    for sh in tc["s1_labor_share_sensitivity"]:
        case(f"S1 labor share of FOC {sh:g}", sources=ALL, labor_share=sh)
    for f in cfg["equipment"]["capex_factor_sensitivity"]:
        case(f"WHR CAPEX x{f:g}", sources=ALL, whr_capex_factor=f)
    lo_imo = cfg["equipment"]["imo_whr_installed_range_usd"][0]
    case(f"WHR CAPEX = IMO lower bound {lo_imo / 1e6:.1f} MUSD (power WHRS, context)", sources=ALL,
         whr_capex_factor=lo_imo / base["capex_usd"])
    case("scavenge-air recovery disabled (no OEM interface)", sources=("jacket", "exhaust"))
    for T in (220.0, 260.0):
        case(f"exhaust temperature {T:g} C", sources=ALL, whr_overrides={"T_exhaust_C": T})
    for e in (0.85, 0.95):
        case(f"delivery efficiency {e:g}", sources=ALL, whr_overrides={"delivery_efficiency": e})
    for load in (0.50, 1.00):
        case(f"engine load {load:g}", sources=ALL, load=load)
    for h in cfg["operating_modes"]["hours_sensitivity"]:
        case(f"operating hours {h:g}", sources=ALL, hours=h)
        case(f"operating hours {h:g}, no WHR", sources=(), hours=h)
    tables["sensitivity"] = pd.DataFrame(sens)
    return tables


if __name__ == "__main__":
    tables = run()
    OUT.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_csv(OUT / f"att_s2_{name}.csv", index=False)
    with pd.option_context("display.width", 260, "display.max_columns", 40, "display.max_colwidth", 70):
        for name in ("heat_sources", "heat_sinks", "heat_allocation", "whr_equipment", "energy_performance"):
            print(f"== {name}")
            print(tables[name].round(3).to_string(index=False))
        cols = ["mode", "case", "hours", "H2_t_per_yr", "process_CAPEX_USD", "WHR_CAPEX_USD", "FCI_USD",
                "labor_OPEX_USD_per_yr", "energy_OPEX_USD_per_yr", "materials_USD_per_yr", "waste_disposal_USD_per_yr",
                "FOC_nonlabor_USD_per_yr", "CaCO3_revenue_USD_per_yr", "AOC_net_USD_per_yr", "MSP_USD_per_kg_H2",
                "GWP_kgCO2e_per_kg_H2"]
        print("== tea_cases")
        print(tables["tea_cases"][cols].round(3).to_string(index=False))
        print("== sensitivity")
        print(tables["sensitivity"][["case", "hours", "FCI_USD", "WHR_CAPEX_USD", "WHR_utilized_kW", "MSP_USD_per_kg_H2",
                                     "GWP_kgCO2e_per_kg_H2"]].round(3).to_string(index=False))
        print("== checks: all PASS" if (tables["checks"]["status"] == "PASS").all() else tables["checks"].to_string())
    print(f"Saved {OUT}/att_s2_*.csv")
