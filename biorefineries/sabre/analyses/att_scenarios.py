# Bioindustrial-Park: BioSTEAM's Premier Biorefinery Models and Results
# Copyright (C) 2026-, Yu Zhou,
#                      Yalin Li <mailto.yalin.li@gmail.com>
#
# This module is under the UIUC open-source license. See
# github.com/BioSTEAMDevelopmentGroup/biosteam/blob/master/LICENSE.txt
# for license details.

"""
att_scenarios.py
----------------
Summary table of the four ATT scenarios of ``analyses/att/scenarios.py`` (ATT-only configuration; s1 is the
baseline, s2-s4 are alternatives): scale, H2, NaOH and lime use, MSP, FCI and GWP100 (net, with the stored-carbon
credit, and the alternatives for the landfill-CH4 counterfactual).

Output: ../results/tables/att_scenarios.csv

Run from the repo root:
    python biorefineries/sabre/analyses/att_scenarios.py
"""
import sys
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from biorefineries.sabre.analyses.att.breakdown import build_att_breakdown
from biorefineries.sabre.analyses.att import scenarios as scen

OUT = SCRIPT_DIR.parent / "results" / "tables" / "att_scenarios.csv"


if __name__ == "__main__":
    rows = []
    for case in scen.SCENARIOS:
        t = build_att_breakdown(case)
        s, g = t["summary"], t["GWP_by_contributor"]
        stored = float(g.loc[g["stage"] == "Stored biogenic carbon", "kgCO2e_per_kg_H2"].sum())
        rows.append(dict(
            scenario=s["scenario"], dry_feed_t_per_day=s["dry_feed_t_per_day"], H2_t_per_yr=s["H2_t_per_yr"],
            NaOH_dose_kg_per_kg_daf=s["NaOH_kg_per_kg_daf"], PSA=s["PSA"], lime=s["lime"],
            fresh_NaOH_t_per_yr=s["fresh_NaOH_t_per_yr"], Ca_OH_2_used_t_per_yr=s["Ca_OH_2_used_t_per_yr"],
            MSP_USD_per_kg_H2=s["MSP_USD_per_kg_H2"], FCI_MUSD=s["FCI_MUSD"],
            GWP_kgCO2e_per_kg_H2=s["GWP_kgCO2e_per_kg_H2"], stored_carbon_credit_in_net_kgCO2e_per_kg_H2=stored,
            GWP_without_stored_carbon_credit_kgCO2e_per_kg_H2=s["GWP_kgCO2e_per_kg_H2"] - stored,
            landfill_CH4_credit_alternative_kgCO2e_per_kg_H2=s["GWP_landfill_credit_kgCO2e_per_kg_H2"],
            GWP_with_landfill_CH4_credit_instead_kgCO2e_per_kg_H2=s["GWP_with_landfill_credit_kgCO2e_per_kg_H2"]))
    df = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    with pd.option_context("display.width", 250, "display.max_columns", 20):
        print(df.round(2).set_index("scenario").T.to_string())
    print(f"Saved {OUT}")
