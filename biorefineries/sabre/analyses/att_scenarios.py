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
Four ATT-integration scenarios (presscake feed, no P1):

    1  NaOH 1 g/g (the team's lab dose), PSA, fresh Ca(OH)2, NLR scale
    2  NaOH 1 g/g, PSA, recycled lime (kiln + slaker), NLR scale
    3  NaOH 1 g/g, PSA, waste lime, scale set by the waste supply
    4  NaOH for full CO2 capture (2.995 g/g, gas CO2 = 0), no PSA, waste lime, same scale as 3

Waste lime: a Ca(OH)2 source that needs no recalcination (carbide lime from acetylene generation), assumed pure,
free of cost and of emissions, and delivered at no charge. It replaces all the lime (no kiln; the CaCO3 cake is
disposed as in the fresh-lime case, TEA Case A). Its supply is one reference-size carbide plant: 80 kt/yr CaC2
(Intratec reference electrothermic plant) x 74.09/64.10 = 92.5 kt/yr Ca(OH)2, taken as fully captured. The plant
scale of scenarios 3 and 4 is the one at which scenario 4 (the larger lime user) uses that whole supply.

The NaOH dose and the gas CO2 yield are overridden in this process only (att.yaml is not changed). The net GWP
includes the stored-carbon credit (landfilled carbonate and char).

Output: ../results/tables/att_scenarios.csv

Run from the repo root:
    python biorefineries/sabre/analyses/att_scenarios.py
"""
import sys
import warnings
from contextlib import contextmanager
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from biorefineries.sabre.analyses.att import inventory as inv, lca, tea
from biorefineries.sabre.systems import _att_system
from biorefineries.sabre.units import _att

OUT = SCRIPT_DIR.parent / "results" / "tables" / "att_scenarios.csv"
LAB_DOSE, LAB_GAS_CO2 = 1.0, 22.68                 # the team's lab dose and gas CO2 (mmol/g daf)
FULL_DOSE, FULL_GAS_CO2 = 2.995, 0.0               # 2 NaOH per CO2 generated
CARBIDE_KT_PER_YR = 80.0                           # Intratec reference carbide plant
WASTE_LIME_KG_PER_YR = CARBIDE_KT_PER_YR * 1e6 * 74.09268 / 64.0993

SCENARIOS = {
    "1 fresh lime, PSA, NaOH 1 g/g, NLR scale": dict(dose=LAB_DOSE, co2=LAB_GAS_CO2, psa=True, lime="fresh", scale="NLR"),
    "2 recycled lime, PSA, NaOH 1 g/g, NLR scale": dict(dose=LAB_DOSE, co2=LAB_GAS_CO2, psa=True, lime="recycled", scale="NLR"),
    "3 waste lime, PSA, NaOH 1 g/g, waste scale": dict(dose=LAB_DOSE, co2=LAB_GAS_CO2, psa=True, lime="waste", scale="waste"),
    "4 waste lime, no PSA, full CO2 capture, waste scale": dict(dose=FULL_DOSE, co2=FULL_GAS_CO2, psa=False, lime="waste",
                                                               scale="waste"),
}


@contextmanager
def naoh_dose(dose, gas_co2):
    cases = [m._ATT["cases"]["Ni-CatATT"] for m in (_att_system, _att)]
    old = [(c["naoh_kg_per_kg_daf"], c["gas_yield_mmol_per_g_daf"]["CO2"]) for c in cases]
    for c in cases:
        c["naoh_kg_per_kg_daf"], c["gas_yield_mmol_per_g_daf"]["CO2"] = dose, gas_co2
    try:
        yield
    finally:
        for c, (d, g) in zip(cases, old):
            c["naoh_kg_per_kg_daf"], c["gas_yield_mmol_per_g_daf"]["CO2"] = d, g


def build(spec, dry_kgph):
    """Simulate one scenario at dry_kgph (kg/h of dry presscake)."""
    return inv._simulate(_att_system.create_att_system(
        dry_sargassum_kgph=dry_kgph, configuration="integrated", lime_recycle=spec["lime"] == "recycled",
        psa=spec["psa"]), dry_kgph)


def waste_scale_dry_kgph():
    """Dry presscake feed (kg/h) at which scenario 4 consumes the whole waste-lime supply."""
    spec = SCENARIOS["4 waste lime, no PSA, full CO2 capture, waste scale"]
    with naoh_dose(spec["dose"], spec["co2"]):
        small = build(spec, 1000.0)
    lime_per_dry = float(inv._streams(small)["lime"].imass["CaOH2"]) / 1000.0
    hours = tea.OPERATING_DAYS_PER_YEAR * 24.0
    return WASTE_LIME_KG_PER_YR / hours / lime_per_dry


def evaluate(name, spec, waste_dry_kgph):
    warnings.filterwarnings("ignore")
    ref = inv.get_att_reference_scale("integrated")
    dry_kgph = ref["dry_feed_kgph"] if spec["scale"] == "NLR" else waste_dry_kgph
    waste = spec["lime"] == "waste"
    with naoh_dose(spec["dose"], spec["co2"]):
        system = build(spec, dry_kgph)
        system.operating_hours = ref["operating_hours_per_year"]
        est = inv.get_att_cost_estimates(system)
        result = tea.evaluate_att_tea(system, est, price_overrides={"CaOH2": 0.0} if waste else None,
                                      caco3=None if spec["lime"] == "recycled" else dict(fraction=0.0))
        applied = lca.apply_att_gwp(system, estimates=est, overrides={"CaOH2_limestone": 0.0} if waste else None)
        contributions = lca.get_att_gwp_contributions(system, applied)
        credit = lca.get_att_landfill_credit(system)
        stored = lca.get_att_stored_carbon_credit(system)
    s, hours = inv._streams(system), system.operating_hours
    net = contributions[-1]["GWP_kgCO2e_per_kg_H2"]
    t = result["tea"]
    h2 = float(s["h2_product"].imass["H2"]) * hours
    return dict(
        scenario=name, dry_feed_t_per_day=dry_kgph * 24 / 1e3, H2_t_per_yr=h2 / 1e3,
        NaOH_dose_kg_per_kg_daf=spec["dose"], PSA=spec["psa"],
        fresh_NaOH_t_per_yr=float(s["fresh_naoh_solid"].imass["NaOH"]) * hours / 1e3,
        Ca_OH_2_used_t_per_yr=float(s["lime"].imass["CaOH2"]) * hours / 1e3,
        Ca_OH_2_price_USD_per_t=0.0 if waste else float(tea._prices()["CaOH2"]) * 1e3,
        MSP_USD_per_kg_H2=result["msp"], FCI_MUSD=t.FCI / 1e6,
        GWP_kgCO2e_per_kg_H2=net, stored_carbon_credit_in_net_kgCO2e_per_kg_H2=stored,
        GWP_without_stored_carbon_credit_kgCO2e_per_kg_H2=net - stored,
        landfill_CH4_credit_alternative_kgCO2e_per_kg_H2=credit["GWP_kgCO2e_per_kg_H2"],
        GWP_with_landfill_CH4_credit_instead_kgCO2e_per_kg_H2=net - stored + credit["GWP_kgCO2e_per_kg_H2"])


if __name__ == "__main__":
    waste_kgph = waste_scale_dry_kgph()
    rows = [evaluate(name, spec, waste_kgph) for name, spec in SCENARIOS.items()]
    df = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    print(f"Waste-lime supply {WASTE_LIME_KG_PER_YR / 1e6:.1f} kt Ca(OH)2/yr -> scale {waste_kgph * 24 / 1e3:.0f} dry t/d")
    with pd.option_context("display.width", 250, "display.max_columns", 20):
        print(df.round(2).T.to_string(header=False))
    print(f"Saved {OUT}")
