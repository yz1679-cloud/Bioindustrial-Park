# Bioindustrial-Park: BioSTEAM's Premier Biorefinery Models and Results
# Copyright (C) 2026-, Yu Zhou,
#                      Yalin Li <mailto.yalin.li@gmail.com>
#
# This module is under the UIUC open-source license. See
# github.com/BioSTEAMDevelopmentGroup/biosteam/blob/master/LICENSE.txt
# for license details.

"""
att_balance_1kg.py
------------------
Mass, electron and energy balance of the ATT route per 1 kg of dry raw
Sargassum (ATT-only configuration: raw Sargassum, press P1, dryer D0, U2),
at the baseline settings of att.yaml: NaOH dose that captures all the CO2
generated (2 NaOH per CO2, gas CO2 = 0), no PSA. Both lime cases are run
(recycled lime: kiln K1 + slaker S1; fresh lime: all Ca(OH)2 bought, cake
disposed).

Output: ../results/tables/att_balance_1kg_raw.csv

Run from the repo root:
    python biorefineries/sabre/analyses/att_balance_1kg.py
"""
import sys
import warnings
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from biorefineries.sabre.analyses.att import inventory as inv, key_metrics as km
from biorefineries.sabre.systems import _att_system

OUT = SCRIPT_DIR.parent / "results" / "tables" / "att_balance_1kg_raw.csv"
MW = dict(H2=2.01588, C=12.011, NaOH=39.99711, CaOH2=74.09268)
ORGANIC_EXCLUDED = ("Water", "Ash")


def _organic_formula(stream):
    """Atoms of the organics (water and ash excluded) per C, and their mass fractions of the dry solids."""
    atoms = {}
    for ID in stream.chemicals.IDs:
        if ID in ORGANIC_EXCLUDED or not float(stream.imass[ID]):
            continue
        for element, n in stream.chemicals[ID].atoms.items():
            atoms[element] = atoms.get(element, 0.0) + n * float(stream.imol[ID])
    C = atoms["C"]
    dry = float(stream.F_mass - stream.imass["Water"])
    return {e: atoms.get(e, 0.0) / C for e in "CHONS"}, {e: atoms.get(e, 0.0) * dict(C=12.011, H=1.008, O=15.999, N=14.007, S=32.06)[e] / dry for e in "CHONS"}


def simulate(lime_recycle):
    warnings.filterwarnings("ignore")
    return inv._simulate(_att_system.create_att_system(dry_sargassum_kgph=1.0, configuration="att_only",
                                                        lime_recycle=lime_recycle), 1.0)


def balance(sys):
    s, u = inv._streams(sys), inv._units(sys)
    U2, C1 = u["U2"], u["C1"]
    raw, cake, juice = s["att_sargassum_feed"], s["pressed_sargassum"], s["biostimulant_juice"]
    feed, (gas, residue) = U2.ins[0], U2.outs
    daf = float(U2._daf_sargassum_kgph)
    rows = []

    def add(section, item, value, unit, note=""):
        rows.append(dict(section=section, item=item, value=value, unit=unit, note=note))

    # 1. Raw Sargassum and press cake ------------------------------------------------
    dry_raw = float(raw.F_mass - raw.imass["Water"])
    add("1 Feed", "Raw Sargassum, dry", dry_raw, "kg")
    add("1 Feed", "  ash", float(raw.imass["Ash"]), "kg")
    add("1 Feed", "  organic (daf)", dry_raw - float(raw.imass["Ash"]), "kg")
    add("1 Feed", "Raw Sargassum, wet (14.3 % solids)", float(raw.F_mass), "kg")
    f_raw, w_raw = _organic_formula(raw)
    f_cake, w_cake = _organic_formula(cake)
    add("1 Feed", "Empirical formula of the raw organics (per C)",
        "CH{H:.3f}O{O:.3f}N{N:.4f}S{S:.5f}".format(**f_raw), "-", "C/H/O/N/S in the model chemicals; O is by composition")
    add("1 Feed", "  CHN of the raw dry solids (C / H / N)", f"{w_raw['C']*100:.2f} / {w_raw['H']*100:.2f} / {w_raw['N']*100:.2f}",
        "wt %", "preprint Table 1: 26.94 / 3.34 / 1.26")
    add("1 Feed", "Press cake, wet (23.7 % solids)", float(cake.F_mass), "kg", "P1 screw press, att.yaml")
    add("1 Feed", "  dry solids", float(cake.F_mass - cake.imass["Water"]), "kg", "component-wise retention")
    add("1 Feed", "  ash", float(cake.imass["Ash"]), "kg")
    add("1 Feed", "  organic (daf, to U2)", daf, "kg")
    add("1 Feed", "Press liquid (juice), wet", float(juice.F_mass), "kg", "carries 0.048 kg ash and the mannitol/protein lost")
    add("1 Feed", "Empirical formula of the cake organics (per C)",
        "CH{H:.3f}O{O:.3f}N{N:.4f}S{S:.5f}".format(**f_cake), "-")
    add("1 Feed", "Feed HHV of the cake organics", float(U2.feed_HHV_MJ_per_kg_daf), "MJ/kg daf", "att.yaml energy_basis")

    # 2. Gas yield and the H2 limit --------------------------------------------------
    atoms = U2._organic_atoms_kmolph
    e_feed = 4 * atoms["C"] + atoms["H"] - 2 * atoms["O"]          # kmol e-/h, reference CO2 and H2O
    per_g = 1e3 / daf
    h2, ch4, co = (float(gas.imol[i]) for i in ("H2", "CH4", "CO"))
    add("2 Gas", "Electron capacity of the cake organics (4C + H - 2O)", e_feed * per_g, "mmol e-/g daf")
    for name in ("H2", "CH4", "CO", "CO2"):
        add("2 Gas", f"Current gas yield, {name}", float(gas.imol[name]) * per_g, "mmol/g daf",
            "team's slate (measured at 1 g/g NaOH); CO2 is 0 with all CO2 captured as carbonate" if name != "CO2" else
            "all CO2 captured as carbonate (the team's slate at 1 g/g NaOH had 22.68)")
    add("2 Gas", "Theoretical H2 limit (all electrons to H2, C -> CO2)", e_feed / 2 * per_g, "mmol H2/g daf")
    add("2 Gas", "Current H2 / theoretical limit", h2 / (e_feed / 2), "-")
    add("2 Gas", "H2 at the U2 outlet", h2 * MW["H2"], "kg per kg raw dry")
    add("2 Gas", "Theoretical H2 limit", e_feed / 2 * MW["H2"], "kg per kg raw dry")
    add("2 Gas", "H2 in the product gas", float(s["h2_product"].imass["H2"]), "kg per kg raw dry",
        "no PSA: all the H2 (98.6 mol %, the rest CH4 and CO) is product")
    add("2 Gas", "Reducing power in H2 / CH4 + CO / unidentified", f"{2*h2/e_feed:.3f} / {(8*ch4+2*co)/e_feed:.3f} / "
        f"{1-(2*h2+8*ch4+2*co)/e_feed:.3f}", "fraction of electrons")

    # 3. NaOH --------------------------------------------------------------------------
    carbonate = float(residue.imol["Na2CO3"] - feed.imol["Na2CO3"])
    co2_total = float(gas.imol["CO2"]) + carbonate
    gross = float(feed.imass["NaOH"])
    makeup = float(s["fresh_naoh_solid"].imass["NaOH"])
    add("3 NaOH", "CO2 generated", co2_total * per_g, "mmol/g daf", "all captured as Na2CO3")
    add("3 NaOH", "NaOH dose to capture all CO2 (2 per CO2)", 2 * co2_total * per_g, "mmol/g daf")
    add("3 NaOH", "NaOH dose to capture all CO2", gross / daf, "kg/kg daf", "the team's lab dose was 1.0")
    add("3 NaOH", "NaOH fed to U2 (fresh + recycled)", gross, "kg per kg raw dry")
    add("3 NaOH", "  fresh makeup", makeup, "kg per kg raw dry")
    add("3 NaOH", "  recycled", gross - makeup, "kg per kg raw dry")
    add("3 NaOH", "NaOH recycle rate (recycled / fed)", 1 - makeup / gross, "-",
        "SP1 whole-liquor recycle 95 %, C1 conversion and the losses set it")

    # 4. Ca(OH)2 -----------------------------------------------------------------------
    na2co3_c1 = float(C1.ins[0].imol["Na2CO3"])
    stoich = na2co3_c1 * MW["CaOH2"]
    fed = float(C1.ins[1].imass["CaOH2"])
    fresh = float(s["lime"].imass["CaOH2"])
    add("4 Ca(OH)2", "Stoichiometric Ca(OH)2 to regenerate the NaOH (1 per Na2CO3)", stoich, "kg per kg raw dry")
    add("4 Ca(OH)2", "Ca(OH)2 fed to C1 (1.1 x stoichiometric)", fed, "kg per kg raw dry")
    add("4 Ca(OH)2", "  fresh (bought)", fresh, "kg per kg raw dry")
    add("4 Ca(OH)2", "  recycled (kiln + slaker)", fed - fresh, "kg per kg raw dry")
    add("4 Ca(OH)2", "Ca(OH)2 recycle rate", 1 - fresh / fed, "-")
    add("4 Ca(OH)2", "CaCO3 formed", float(C1.outs[0].imass["CaCO3"]), "kg per kg raw dry")

    # 5. Fate of the feed energy ---------------------------------------------------------
    feed_HHV = float(U2.feed_HHV_MJ_per_kg_daf) * daf               # MJ per kg raw dry
    hhv = {i: km._hhv_MJ_per_kg(i) for i in ("H2", "CH4", "CO")}
    gas_HHV = {i: float(gas.imass[i]) * hhv[i] for i in hhv}
    h2_prod_HHV = float(s["h2_product"].imass["H2"]) * hhv["H2"]
    tail = inv.get_att_tail_gas_offset(sys)
    ng_fuel_LHV = tail["u2_fuel_MJph"] + sum(
        hu.duty for hu in sys.heat_utilities if hu.agent.ID == "low_pressure_steam") / 1e3 / 0.80
    elec = float(sys.power_utility.rate) * 3.6                        # kW -> MJ/h
    heat_u2 = float(U2._heat_duty_kJph) / 1e3                        # MJ/h, net process heat into U2 (incl. reaction)
    add("5 Energy", "Feed HHV (cake organics)", feed_HHV, "MJ per kg raw dry")
    add("5 Energy", "Process heat into U2 (500 C, reaction enthalpy included)", heat_u2, "MJ",
        f"{heat_u2/feed_HHV:.2f} x feed HHV; the gas carries more HHV than the feed because the heat and the "
        "NaOH/carbonate chemistry drive the reaction")
    add("5 Energy", "U2 outlet gas HHV: H2", gas_HHV["H2"], "MJ", f"{gas_HHV['H2']/feed_HHV*100:.0f} % of feed HHV")
    add("5 Energy", "U2 outlet gas HHV: CH4 + CO", gas_HHV["CH4"] + gas_HHV["CO"], "MJ",
        f"{(gas_HHV['CH4']+gas_HHV['CO'])/feed_HHV*100:.0f} % of feed HHV")
    add("5 Energy", "Remainder of (feed HHV + U2 heat): sensible/latent heat of the hot outlets, losses",
        feed_HHV + heat_u2 - sum(gas_HHV.values()), "MJ")
    add("5 Energy", "H2 in the product gas (HHV)", h2_prod_HHV, "MJ", f"{h2_prod_HHV/feed_HHV*100:.0f} % of feed HHV")
    add("5 Energy", "CH4 + CO in the product gas, no credit (HHV)", gas_HHV["CH4"] + gas_HHV["CO"], "MJ",
        "no PSA, no tail gas: nothing displaces natural gas")
    add("5 Energy", "Purchased fuel: natural gas for U2/kiln + LP steam boiler (LHV)", ng_fuel_LHV, "MJ",
        f"{ng_fuel_LHV/feed_HHV:.2f} MJ per MJ of feed HHV")
    add("5 Energy", "Purchased electricity", elec, "MJ")
    add("5 Energy", "H2 product HHV / (feed HHV + purchased fuel + electricity)", h2_prod_HHV / (feed_HHV + ng_fuel_LHV + elec), "-")
    return rows


if __name__ == "__main__":
    cases = {"recycled lime": balance(simulate(True)), "fresh lime": balance(simulate(False))}
    base, other = cases["recycled lime"], cases["fresh lime"]
    table = pd.DataFrame([dict(section=a["section"], item=a["item"], value_recycled_lime=a["value"],
                               value_fresh_lime=b["value"], unit=a["unit"], note=a["note"])
                          for a, b in zip(base, other)])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(OUT, index=False)
    with pd.option_context("display.max_colwidth", 70, "display.width", 250):
        print(table.drop(columns="note").to_string(index=False, float_format=lambda x: f"{x:.4g}"))
    print(f"Saved {OUT}")
