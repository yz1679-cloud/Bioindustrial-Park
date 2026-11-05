# Bioindustrial-Park: BioSTEAM's Premier Biorefinery Models and Results
# Copyright (C) 2026-, Yu Zhou,
#                      Yalin Li <mailto.yalin.li@gmail.com>
#
# This module is under the UIUC open-source license. See
# github.com/BioSTEAMDevelopmentGroup/biosteam/blob/master/LICENSE.txt
# for license details.

"""
ree_sensitivity.py
------------------
Sensitivity of ATT S1 and S2 (Mode A, all WHR) to the REO grade of the roasted REE product. The collaborators' case of a
seaweed soaked in a concentrated REE solution gives a 98 wt % REO product (tea.yaml ree_grade_sensitivity).

Only the grade changes: the REO mass of the product stays at ``overall_recovery`` of the REE of the dilute wastewater
(att.yaml downstream.ree_recovery) and the mineral filler that dilutes it shrinks, so the roaster, the oxalate filter and the
mass sent to the roaster get smaller. A larger REE loading of the seaweed (more REO per kg of char) is NOT modeled. The product
is sold on its REO content, so the REO price is swept as well: a 98 % product may sell above the mixed concentrate.

Outputs: biorefineries/ATT/results/tables/att_ree_grade_sensitivity.csv (root: paths.results_root)

Run from the repo root:
    python -m biorefineries.ATT.analyses.ree_sensitivity
"""
import warnings
from unittest import mock

import pandas as pd

from biorefineries.ATT.analyses import inventory as inv
from biorefineries.ATT.analyses import marine_tea as mt
from biorefineries.ATT.analyses import scenarios as scen
from biorefineries.ATT.analyses import tea as tea_mod
from biorefineries.ATT.analyses.paths import output_dir
from biorefineries.ATT.utils import load_assumptions

__all__ = ("get_att_ree_grade_sensitivity", "breakeven_prices", "concentrated_soak_params", "nd_soak_case", "get_att_ree_loading_sensitivity")

ALL = ("jacket", "scavenge", "exhaust")


def concentrated_soak_params(loading_mg_per_g, native_ppm=None):
    """
    ``ree_params`` of a seaweed soaked in a concentrated REE solution: ``loading_mg_per_g`` mg of TREE captured per g of dry seaweed
    (the dilute AMD case is 0.56). The seaweed keeps its native TREE (att.yaml: 737 ppm minus the 560 ppm captured from the AMD),
    the initial REE per g of seaweed is the captured loading (100 % capture, as the AMD case), and the HCl and oxalic acid follow the
    REE stoichiometry instead of the lab doses per kg of char; the oxalate cake is washed free of the entrained salts (ideal wash, wash water
    not modeled) so that the product can reach the grade. The loading is an INPUT: the concentration of the starting water and
    the seaweed dose are not known.
    """
    cfg = load_assumptions("att.yaml")["att"]["downstream"]["ree_recovery"]
    dose = float(cfg["seaweed_dose_g_per_L"])
    if native_ppm is None:
        native_ppm = float(cfg["seaweed_TREE_ppm"]) - float(cfg["wastewater_TREE_mg_per_L"]) / dose * 1e3
    return dict(seaweed_TREE_ppm=native_ppm + float(loading_mg_per_g) * 1e3,
                wastewater_TREE_mg_per_L=float(loading_mg_per_g) * dose, scale_reagents_with_REE=True,
                precipitate_wash_efficiency=1.0)


def nd_soak_case(feedwater="0.01 M"):
    """
    The collaborators' Nd-soaked seaweed (att.yaml downstream.ree_recovery.nd_soak_data): ``(loading_mg_Nd_per_g, ree_params, grade)`` for
    the feedwater "100 ppb", "0.001 M", "0.01 M" or "0.1 M". The loading is the Nd wt % of the ATT residue times the residue yield per g of
    dry seaweed (an assumption), the seaweed has no Nd of its own, the REE is Nd (Nd2O3: 1.1664 kg REO per kg Nd), the recovery is the
    0.01 M run's 60.3 % from the feedwater and the product grade is its 98.82 % Nd2O3.
    """
    d = load_assumptions("att.yaml")["att"]["downstream"]["ree_recovery"]["nd_soak_data"]
    loading = float(d["Nd_wt_pct_of_ATT_residue"][feedwater]) / 100.0 * float(d["residue_g_per_g_dry_seaweed"]) * 1e3
    params = concentrated_soak_params(loading, native_ppm=0.0)
    params.update(REO_per_TREE=336.48 / (2.0 * 144.242), REE_molar_mass=144.242, overall_recovery=float(d["overall_Nd_recovery"]))
    return loading, params, float(d["product_Nd2O3_purity"])


def _config():
    return tea_mod._T["ree_grade_sensitivity"]


def _tea_rows(system, price):
    """S1 summary and S2 (Mode A, all WHR) row of the simulated process ``system`` at the REO price ``price`` [USD/kg REO]."""
    with mock.patch.dict(tea_mod._T["prices"]["REO"], {"value": float(price)}):
        ref = mt.s1_reference(system)
        s2, _ = mt.evaluate_case(system, ref, "S2", sources=ALL, hours=7920.0, load=0.75)
    return ref["row"], s2


def get_att_ree_grade_sensitivity(grades=None, prices=None):
    """
    One row per (REO grade, REO price): the product (kg/h, REO, mineral filler), the LC1 and RO1 installed costs, and S1 and S2
    (Mode A, all WHR) MSP, GWP and FCI. ``grades`` [REO wt fraction] and ``prices`` [USD/kg REO] default to tea.yaml
    ree_grade_sensitivity (the price list always starts with the baseline price). The first rows are the process without REE recovery.
    """
    cfg = _config()
    grades = list(cfg["grades_REO_wt_frac"] if grades is None else grades)
    base_price = float(tea_mod._T["prices"]["REO"]["value"])
    prices = [base_price] + [float(p) for p in (cfg["prices_usd_per_kg_REO"] if prices is None else prices) if float(p) != base_price]
    rows = []

    off = scen.create(scen.ATT_S2, ree_recovery=False)
    s1, s2 = _tea_rows(off, base_price)
    rows.append(dict(REE_recovery=False, REO_grade=None, REO_price_usd_per_kg=None, product_kgph=0.0, REO_kgph=0.0, filler_kgph=0.0,
                     LC1_MUSD=0.0, RO1_MUSD=0.0,
                     S1_MSP=s1["MSP_USD_per_kg_H2"], S1_GWP=s1["GWP_kgCO2e_per_kg_H2"], S1_FCI_MUSD=s1["FCI_USD"] / 1e6,
                     S2_MSP=s2["MSP_USD_per_kg_H2"], S2_GWP=s2["GWP_kgCO2e_per_kg_H2"], S2_FCI_MUSD=s2["FCI_USD"] / 1e6))
    for grade in grades:
        system = scen.create(scen.ATT_S2, ree_grade=grade)
        st, u = inv._streams(system), inv._units(system)
        product = st["ree_product"]
        physical = dict(REE_recovery=True, REO_grade=float(grade), product_kgph=float(product.F_mass), REO_kgph=float(product.imass["REO"]),
                        filler_kgph=float(product.imass["Ash"]), LC1_MUSD=u["LC1"].installed_cost / 1e6, RO1_MUSD=u["RO1"].installed_cost / 1e6)
        for price in prices:
            s1, s2 = _tea_rows(system, price)
            rows.append(dict(physical, REO_price_usd_per_kg=price,
                             S1_MSP=s1["MSP_USD_per_kg_H2"], S1_GWP=s1["GWP_kgCO2e_per_kg_H2"], S1_FCI_MUSD=s1["FCI_USD"] / 1e6,
                             S2_MSP=s2["MSP_USD_per_kg_H2"], S2_GWP=s2["GWP_kgCO2e_per_kg_H2"], S2_FCI_MUSD=s2["FCI_USD"] / 1e6))
    return pd.DataFrame(rows)


def get_att_ree_loading_sensitivity(loadings=(5.0, 20.0, 50.0), grade=0.98, prices=None):
    """
    The collaborators' concentrated-soak case: one row per (REE loading of the seaweed [mg TREE/g dry], REO price) with the product
    at ``grade`` REO. Columns as in ``get_att_ree_grade_sensitivity`` plus the reagent flows and the REE mass balance. Needs
    ``ree_params`` (see ``concentrated_soak_params``); the loading is an input, not a result.
    """
    base_price = float(tea_mod._T["prices"]["REO"]["value"])
    prices = [base_price] + [float(p) for p in (_config()["prices_usd_per_kg_REO"] if prices is None else prices) if float(p) != base_price]
    rows = []
    for loading in loadings:
        system = scen.create(scen.ATT_S2, ree_grade=grade, ree_params=concentrated_soak_params(loading))
        st, u = inv._streams(system), inv._units(system)
        product, cake = st["ree_product"], u["LC1"].ins[0]
        physical = dict(loading_mg_TREE_per_g=float(loading), REO_grade=float(grade), char_REO_kgph=float(cake.imass["REO"]),
                        product_kgph=float(product.F_mass), REO_kgph=float(product.imass["REO"]), filler_kgph=float(product.imass["Ash"]),
                        HCl31_kgph=float(st["fresh_hcl"].F_mass), oxalic_kgph=float(st["fresh_oxalic_acid"].F_mass),
                        oxalate_ceiling=float(u["LC1"]._stoich_ceiling), LC1_MUSD=u["LC1"].installed_cost / 1e6, RO1_MUSD=u["RO1"].installed_cost / 1e6)
        for price in prices:
            s1, s2 = _tea_rows(system, price)
            rows.append(dict(physical, REO_price_usd_per_kg=price,
                             S1_MSP=s1["MSP_USD_per_kg_H2"], S1_GWP=s1["GWP_kgCO2e_per_kg_H2"], S1_FCI_MUSD=s1["FCI_USD"] / 1e6,
                             S2_MSP=s2["MSP_USD_per_kg_H2"], S2_GWP=s2["GWP_kgCO2e_per_kg_H2"], S2_FCI_MUSD=s2["FCI_USD"] / 1e6))
    return pd.DataFrame(rows)


def breakeven_prices(df):
    """
    REO price [USD/kg REO] at which REE recovery gives the MSP of the process without it, per grade (the MSP is linear in the price;
    needs at least two prices per grade). Columns: REO_grade, S1_breakeven, S2_breakeven.
    """
    off = df[~df["REE_recovery"]].iloc[0]
    out = []
    for grade, g in df[df["REE_recovery"]].groupby("REO_grade", sort=False):
        g = g.sort_values("REO_price_usd_per_kg")
        p0, p1 = g.iloc[0], g.iloc[-1]
        row = dict(REO_grade=grade)
        for tag in ("S1", "S2"):
            slope = (p1[f"{tag}_MSP"] - p0[f"{tag}_MSP"]) / (p1["REO_price_usd_per_kg"] - p0["REO_price_usd_per_kg"])
            row[f"{tag}_breakeven"] = p0["REO_price_usd_per_kg"] + (off[f"{tag}_MSP"] - p0[f"{tag}_MSP"]) / slope
        out.append(row)
    return pd.DataFrame(out)


if __name__ == "__main__":
    warnings.filterwarnings("ignore")
    df = get_att_ree_grade_sensitivity()
    out = output_dir("tables")
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "att_ree_grade_sensitivity.csv", index=False)
    with pd.option_context("display.width", 260, "display.max_columns", 40):
        print(df.round(4).to_string(index=False))
        print(breakeven_prices(df).round(2).to_string(index=False))
    print(f"Saved {out / 'att_ree_grade_sensitivity.csv'}")
