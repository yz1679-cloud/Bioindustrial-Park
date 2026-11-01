# Bioindustrial-Park: BioSTEAM's Premier Biorefinery Models and Results
# Copyright (C) 2026-, Yu Zhou,
#                      Yalin Li <mailto.yalin.li@gmail.com>
#
# This module is under the UIUC open-source license. See
# github.com/BioSTEAMDevelopmentGroup/biosteam/blob/master/LICENSE.txt
# for license details.

"""
att_caco3_sales.py
------------------
ATT Scenario 1 CaCO3 byproduct sales (att_tea.yaml caco3_sales): the recovered CaCO3 of each cake stream (component
mass, dry and wet cake, dry-basis purity), the previous treatment (whole cakes disposed, no sales) and the MSP at
the sensitivity prices (0, 100, 315 USD/t). One process simulation; only the CaCO3 price changes between the
sensitivity cases (overridden per call, the configuration file is not changed).

Output: biorefineries/ATT/outputs/tables/att_s1_caco3_sales.csv (and _recovery.csv)

Run from the repo root:
    python biorefineries/ATT/analyses/att_caco3_sales.py
"""
import sys
import warnings
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from biorefineries.ATT.analyses.att import inventory as inv
from biorefineries.ATT.analyses.att import scenarios as scen
from biorefineries.ATT.analyses.att import tea as tea_mod
from biorefineries.ATT.analyses.att.breakdown import build_att_breakdown

OUT = SCRIPT_DIR.parent / "outputs" / "tables"
SUMMARY_KEYS = ("H2_t_per_yr", "CaCO3_price_USD_per_t", "CaCO3_sold_t_per_yr", "CaCO3_sales_revenue_USD_per_yr",
                "CaCO3_cake_disposal_USD_per_yr", "AOC_MUSD_per_yr", "MSP_USD_per_kg_H2", "FCI_MUSD", "results_status")


def caco3_recovery(system):
    """Recovered CaCO3 per cake stream that is a system product (component mass, not the wet cake)."""
    s = inv._streams(system)
    hours = system.operating_hours
    rows = []
    for ID in tea_mod._T["caco3_sales"]["streams"]:
        if ID not in s or s[ID] not in system.products:
            continue
        cake = s[ID]
        wet, water, caco3 = float(cake.F_mass), float(cake.imass["Water"]), float(cake.imass["CaCO3"])
        rows.append(dict(stream=ID, CaCO3_kgph=caco3, CaCO3_t_per_yr=caco3 * hours / 1e3, wet_cake_kgph=wet,
                         dry_cake_kgph=wet - water, CaCO3_purity_dry_basis=caco3 / (wet - water),
                         CaCO3_purity_insoluble_solids_basis=caco3 / (caco3 + float(cake.imass["CaOH2"])),
                         water_kgph=water, CaOH2_kgph=float(cake.imass["CaOH2"]), NaOH_kgph=float(cake.imass["NaOH"]),
                         Na2CO3_kgph=float(cake.imass["Na2CO3"])))
    total = {k: sum(r[k] for r in rows) for k in rows[0] if k != "stream" and not k.startswith("CaCO3_purity")}
    total.update(stream="total", CaCO3_purity_dry_basis=total["CaCO3_kgph"] / total["dry_cake_kgph"],
                 CaCO3_purity_insoluble_solids_basis=total["CaCO3_kgph"] / (total["CaCO3_kgph"] + total["CaOH2_kgph"]))
    return rows + [total]


if __name__ == "__main__":
    warnings.filterwarnings("ignore")
    system = scen.create(scen.ATT_S1)
    recovery = pd.DataFrame(caco3_recovery(system))
    cfg = tea_mod._T["caco3_sales"]
    rows = []
    enabled = cfg["enabled"]
    try:          # previous treatment, for comparison only: both cakes disposed whole, no sales
        cfg["enabled"] = False
        rows.append(dict(case="previous: no sales, whole cakes disposed",
                         **{k: build_att_breakdown("att_s1", sys=system)["summary"][k] for k in SUMMARY_KEYS}))
    finally:
        cfg["enabled"] = enabled
    for price in cfg["sensitivity_prices_usd_per_metric_ton"]:
        rows.append(dict(case=f"CaCO3 sold at {price:g} USD/t (non-CaCO3 cake mass disposed)",
                         **{k: build_att_breakdown("att_s1", caco3_price=price, sys=system)["summary"][k]
                            for k in SUMMARY_KEYS}))
    build_att_breakdown("att_s1", sys=system)      # leave the configured baseline prices on the system
    df = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    recovery.to_csv(OUT / "att_s1_caco3_recovery.csv", index=False)
    df.to_csv(OUT / "att_s1_caco3_sales.csv", index=False)
    with pd.option_context("display.width", 250, "display.max_columns", 30):
        print(recovery.round(5).to_string(index=False))
        print(df.round(4).to_string(index=False))
    print(f"Saved {OUT / 'att_s1_caco3_recovery.csv'} and {OUT / 'att_s1_caco3_sales.csv'}")
