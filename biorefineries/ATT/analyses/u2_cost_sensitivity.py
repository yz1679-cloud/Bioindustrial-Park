# Bioindustrial-Park: BioSTEAM's Premier Biorefinery Models and Results
# Copyright (C) 2026-, Yu Zhou,
#                      Yalin Li <mailto.yalin.li@gmail.com>
#
# This module is under the UIUC open-source license. See
# github.com/BioSTEAMDevelopmentGroup/biosteam/blob/master/LICENSE.txt
# for license details.

"""
u2_cost_sensitivity.py
----------------------
Sensitivity of the ATT S1 MSP to the cost of the reactor U2.

No ATT reactor design exists in the literature (reviews name the reactor as an open problem), so the reactor is a
placeholder: a vertical pressure vessel sized on a 1 h hold-up (att.yaml cost_estimates.U2_vessel) heated by a natural-gas
furnace. The vessel is only a small part of U2 (the furnace is the rest), so this module shows what a more expensive reactor
would do to the MSP. Cases (all other inputs are the S1 baseline):

* ``baseline``: U2 as modeled;
* ``reactor body x f``: the installed cost of the vessel and its platforms (not the furnace) multiplied by f;
* ``U2 total x f``: the installed cost of the whole of U2 (furnace included) multiplied by f;
* ``rotary kiln analog``: the vessel replaced by a rotary kiln costed like the other kilns of the model (the REE roaster RO1,
  ``ATTReeRoaster``): the drum-dryer correlation on a shell area of 3.14 m2 per t/d of feed solids, a refractory factor of
  2, bare-module factor 2.06 and the dryer's drive power, which is priced as electricity. The solids rate of U2 is
  the feed without its water. This is a cost analogy, not a reactor design.

The extra capital is added to the fixed capital investment (so the working capital and the fixed operating cost follow it);
the energy and material balances are those of the baseline.

Outputs: biorefineries/ATT/results/tables/att_u2_cost_sensitivity.csv (root: paths.results_root)

Run from the repo root:
    python -m biorefineries.ATT.analyses.u2_cost_sensitivity
"""
import warnings

import biosteam as bst
import pandas as pd

from biorefineries.ATT.analyses import inventory as inv
from biorefineries.ATT.analyses import scenarios as scen
from biorefineries.ATT.analyses import tea as tea_mod
from biorefineries.ATT.analyses.paths import output_dir

__all__ = ("kiln_analog", "get_att_u2_cost_sensitivity")

BODY_FACTORS = (1.0, 2.0, 5.0, 10.0)
TOTAL_FACTORS = (1.5, 2.0, 3.0)
# Rotary-kiln cost basis of ATTReeRoaster (BioSTEAM DrumDryer: 0.52 x 2.268 MUSD at 1235.35 m2, CE 525.4, 2007).
KILN_AREA_M2_PER_T_PER_DAY = 3.14
KILN_REFRACTORY_FACTOR = 2.0
KILN_F_BM = 2.06
KILN_DRYER_PURCHASE_USD = 0.52 * 2268000.0
KILN_DRYER_AREA_M2 = 1235.35
KILN_DRYER_CE = 525.4
KILN_DRYER_POWER_KW = 938.866
KILN_COST_EXPONENT = 0.6


def kiln_analog(U2):
    """Installed cost [USD] and drive power [kW] of the rotary kiln that replaces the vessel of ``U2`` (see the module doc)."""
    feed = U2.ins[0]
    solids_t_per_day = float(feed.F_mass - feed.imass["Water"]) * 24.0 / 1e3
    ratio = KILN_AREA_M2_PER_T_PER_DAY * solids_t_per_day / KILN_DRYER_AREA_M2
    purchase = (KILN_DRYER_PURCHASE_USD * bst.CE / KILN_DRYER_CE * ratio ** KILN_COST_EXPONENT * KILN_REFRACTORY_FACTOR)
    return purchase * KILN_F_BM, KILN_DRYER_POWER_KW * ratio ** KILN_COST_EXPONENT


def get_att_u2_cost_sensitivity(case="att_s1"):
    """One row per case: U2 installed cost, FCI, S1 MSP and the change from the baseline MSP."""
    spec = scen.ALL_SCENARIOS[case]
    sys = scen.create(spec)
    config = scen.tea_config(spec, None)
    U2 = inv._units(sys)["U2"]
    furnace = float(U2.installed_costs["Furnace"])
    body = float(U2.installed_cost) - furnace              # vessel and platforms
    rows = []

    def solve(name, extra_capital=0.0, extra_power_kW=0.0, note=""):
        hours = float(sys.operating_hours)
        capital = [(f"U2 sensitivity: {name}", extra_capital, "u2_sensitivity")] if extra_capital else []
        voc = [(f"U2 sensitivity: {name}, electricity", extra_power_kW * bst.PowerUtility.price * hours)] if extra_power_kW else []
        result = tea_mod.evaluate_att_tea(sys, **config, extra_capital=capital, extra_voc=voc)
        rows.append(dict(case=name, U2_installed_MUSD=(furnace + body + extra_capital) / 1e6, extra_power_kW=extra_power_kW, FCI_MUSD=result["tea"].FCI / 1e6,
                         MSP_USD_per_kg_H2=result["msp"], note=note))

    solve("baseline", note="vertical vessel and furnace, as modeled")
    for f in BODY_FACTORS[1:]:
        solve(f"reactor body x{f:g}", (f - 1.0) * body, note="vessel and platforms only; furnace unchanged")
    for f in TOTAL_FACTORS:
        solve(f"U2 total x{f:g}", (f - 1.0) * (furnace + body), note="furnace and vessel")
    kiln_cost, kiln_kW = kiln_analog(U2)
    solve("rotary kiln analog", kiln_cost - body, kiln_kW, note="kiln replaces the vessel; cost analogy, not a design")
    df = pd.DataFrame(rows)
    base = float(df.loc[df["case"] == "baseline", "MSP_USD_per_kg_H2"].iloc[0])
    df["delta_MSP_USD_per_kg_H2"] = df["MSP_USD_per_kg_H2"] - base
    df["delta_MSP_pct"] = 100.0 * df["delta_MSP_USD_per_kg_H2"] / base
    tea_mod.evaluate_att_tea(sys, **config)     # leave the simulated system at its baseline TEA state
    return df


if __name__ == "__main__":
    warnings.filterwarnings("ignore")
    df = get_att_u2_cost_sensitivity()
    out = output_dir("tables")
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "att_u2_cost_sensitivity.csv", index=False)
    with pd.option_context("display.width", 260, "display.max_columns", 40):
        print(df.round(4).to_string(index=False))
    print(f"Saved {out / 'att_u2_cost_sensitivity.csv'}")
