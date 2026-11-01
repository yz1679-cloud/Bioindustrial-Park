# Bioindustrial-Park: BioSTEAM's Premier Biorefinery Models and Results
# Copyright (C) 2026-, Yu Zhou,
#                      Yalin Li <mailto.yalin.li@gmail.com>
#
# This module is under the UIUC open-source license. See
# github.com/BioSTEAMDevelopmentGroup/biosteam/blob/master/LICENSE.txt
# for license details.

"""
ATT Scenario 2 floating TEA (data/marine_tea.yaml) on the unchanged S1 process and TEA (analyses/att/tea.py,
breakdown.py), with marine WHR (marine_whr.py) and its incremental GWP (marine_lca.py):

* process CAPEX = S1 installed capital (units + S1 estimate items) x capex_multiplier (USER); WHR equipment is
  added AFTER the multiplier (no double marine factor);
* FOC = labor_multiplier x S1 labor (fixed USD/yr; S1 labor = assumed share of the S1 FOC, which lumps labor,
  maintenance and overhead) + (1 - share) x 4 % x FCI (maintenance/overhead scale with the floating FCI);
* the recovered heat replaces purchased LP steam (and U2 furnace gas for the feed preheater) at the S1 utility
  prices; the WHR pumps add electricity;
* operating hours (Mode A 7920 h underway, Mode B 2640 h) scale the annual production and the variable costs.
Everything else (materials, disposal, CaCO3 sales at the configured price, financing) is the S1 TEA.
"""
from biorefineries.ATT.analyses.att import marine_lca
from biorefineries.ATT.analyses.att import marine_whr
from biorefineries.ATT.analyses.att import tea as tea_mod
from biorefineries.ATT.analyses.att.breakdown import build_att_breakdown
from biorefineries.ATT.utils import load_assumptions

import biosteam as bst

__all__ = ("load_tea_config", "land_reference", "evaluate_case", "operating_modes")


def load_tea_config():
    return load_assumptions("marine_tea.yaml")["marine_tea"]


def _summary_row(case, t, labor, whr_capex, hours, extra=None):
    s, o = t["summary"], t["OPEX_by_group"]
    by_type = o.groupby("cost_type")["MUSD_per_yr"].sum()
    foc = float(o.loc[o["cost_type"] == "Fixed operating cost", "MUSD_per_yr"].sum()) * 1e6
    row = dict(case=case, hours=hours, H2_t_per_yr=s["H2_t_per_yr"], dry_feed_t_per_yr=s["dry_feed_t_per_day"] / 24.0 * hours,
               FCI_USD=s["FCI_MUSD"] * 1e6, WHR_CAPEX_USD=whr_capex,
               process_CAPEX_USD=s["FCI_MUSD"] * 1e6 - whr_capex,
               labor_OPEX_USD_per_yr=labor, FOC_nonlabor_USD_per_yr=foc - labor,
               energy_OPEX_USD_per_yr=float(by_type.get("Utilities", 0.0)) * 1e6,
               materials_USD_per_yr=float(by_type.get("Materials", 0.0)) * 1e6,
               waste_disposal_USD_per_yr=float(by_type.get("Waste treatment and disposal", 0.0)) * 1e6,
               CaCO3_revenue_USD_per_yr=s.get("CaCO3_sales_revenue_USD_per_yr", 0.0),
               AOC_net_USD_per_yr=s["AOC_MUSD_per_yr"] * 1e6, MSP_USD_per_kg_H2=s["MSP_USD_per_kg_H2"],
               GWP_kgCO2e_per_kg_H2=s["GWP_kgCO2e_per_kg_H2"], results_status=s["results_status"])
    row.update(extra or {})
    return row


def operating_modes(cfg=None):
    """(label, hours/yr, engine load) of the marine_whr.yaml operating modes (A underway reference, B profile)."""
    modes = (marine_whr.load_whr_config() if cfg is None else cfg)["operating_modes"]
    a, b = modes["A_underway_reference"], modes["B_operational_profile"]
    hours_b = float(b["hours_per_day_underway"]) * float(b["days_per_year"])
    return ((f"A: {float(a['hours_per_year']):.0f} h underway (idealized)", float(a["hours_per_year"]),
             float(a["engine_load"])),
            (f"B: {hours_b:.0f} h ({float(b['hours_per_day_underway']):g} h/d underway)", hours_b,
             float(b["engine_load"])))


def land_reference(sys, f2_sales=True):
    """ATT S1 land-based TEA (the reference); returns its summary row and the S1 labor estimate."""
    cfg = load_tea_config()
    t = build_att_breakdown("att_s1", sys=sys, f2_sales=f2_sales)
    foc_s1 = float(tea_mod._FIN["foc_frac_of_fci"]) * t["summary"]["FCI_MUSD"] * 1e6
    labor = float(cfg["s1_labor_share_of_foc"]) * foc_s1
    return dict(row=_summary_row("S1 land", t, labor, 0.0, sys.operating_hours),
                FOC_USD_per_yr=foc_s1, FCI_USD=t["summary"]["FCI_MUSD"] * 1e6)


def evaluate_case(sys, ref, case, sources=marine_whr.SOURCE_IDS, hours=7920.0, capex_multiplier=None,
                  labor_multiplier=None, labor_share=None, whr_capex_factor=1.0, whr_overrides=None, load=None,
                  f2_sales=True):
    """
    One ATT S2 case on the simulated S1 process ``sys`` (``ref`` = land_reference(sys)). ``sources``: WHR sources
    used (() = floating without WHR). Returns (summary row, whr result or None).
    """
    cfg = load_tea_config()
    mult = float(cfg["capex_multiplier"] if capex_multiplier is None else capex_multiplier)
    lab_mult = float(cfg["labor_multiplier"] if labor_multiplier is None else labor_multiplier)
    share = float(cfg["s1_labor_share_of_foc"] if labor_share is None else labor_share)
    foc_rate = float(tea_mod._FIN["foc_frac_of_fci"])
    labor_s1 = share * foc_rate * ref["FCI_USD"]
    whr = None
    extra_capital, extra_voc = [], []
    if sources:
        whr = marine_whr.evaluate_whr(sys, enabled=tuple(sources), load=load, overrides=whr_overrides,
                                      capex_factor=whr_capex_factor)
        extra_capital = list(whr["equipment"])
        steam = sum(a["assigned_kW"] * a["usd_per_kWh"] for a in whr["assignments"] if "steam" in a["sink_utility"])
        gas = sum(a["assigned_kW"] * a["usd_per_kWh"] for a in whr["assignments"] if "natural_gas" in a["sink_utility"])
        extra_voc = [("Marine WHR: purchased LP steam displaced", -steam * hours),
                     ("Marine WHR: U2 furnace natural gas displaced (feed preheat)", -gas * hours),
                     ("Marine WHR: pump electricity", whr["pump_kW"] * bst.PowerUtility.price * hours)]
    kwargs = dict(fci_factor=mult, operating_hours=hours, extra_capital=extra_capital, extra_voc=extra_voc,
                  foc_frac_of_fci=foc_rate * (1.0 - share), foc_fixed=lab_mult * labor_s1)
    t = build_att_breakdown("att_s2", sys=sys, tea_kwargs=kwargs, f2_sales=f2_sales)
    whr_capex = sum(v for _, v, _ in extra_capital)
    d_gwp = marine_lca.whr_gwp_change(sys, whr)["delta_kgCO2e_per_kg_H2"] if whr else 0.0
    extra = dict(capex_multiplier=mult, labor_multiplier=lab_mult, labor_share_of_S1_FOC=share,
                 whr_sources="+".join(sources) if sources else "none", whr_capex_factor=whr_capex_factor,
                 WHR_utilized_kW=whr["utilized_kW"] if whr else 0.0, WHR_pump_kW=whr["pump_kW"] if whr else 0.0,
                 GWP_WHR_change_kgCO2e_per_kg_H2=d_gwp)
    row = _summary_row(case, t, lab_mult * labor_s1, whr_capex, hours, extra)
    row["GWP_kgCO2e_per_kg_H2"] = t["summary"]["GWP_kgCO2e_per_kg_H2"] + d_gwp     # incremental process GWP
    return row, whr
