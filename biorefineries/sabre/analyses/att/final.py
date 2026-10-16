"""
Final ATT results: (C) industrial-scale BioSTEAM material/energy/TEA/LCA with
the baseline U2 closure (att.yaml), and (D) gas-yield comparisons. Reuses
att.reporting, att.inventory and att.thermodynamics.
Writes ATT_Final_Results.xlsx (all sheets), README.md and the D CSVs to
att_outputs/comparison/ and the C CSVs to att_outputs/full_scale/summary/.
"""
import os
import warnings

from biorefineries.sabre.analyses.att import reporting as rep
from biorefineries.sabre.analyses.att import inventory as inv
from biorefineries.sabre.analyses.att import tea as tea_mod
from biorefineries.sabre.analyses.att.thermodynamics import evaluate_att_u2_variant, get_att_u2_energy_uncertainty
from biorefineries.sabre.utils import load_assumptions

__all__ = ("build_att_final_results", "export_att_final_results")

_ATT = load_assumptions("att.yaml")["att"]
METHODS = ("uniform_redox_scaling", "h2_priority", "experimental_fixed", "h2_measured_ch4_max", "uniform_co2_free")
# Selected element-balanced gas-yield scenarios (selected feasible modeling
# scenarios, not global physical bounds or confidence intervals). "Gas-A" is
# unrelated to TEA Case A (CaCO3 filter cake disposed, no revenue).
GAS_SCENARIOS = (
    ("Gas-C", "uniform_redox_scaling",
     "Uniform scaling, s = 0.5998: all four measured gases x s; remaining C as char; measured ratios preserved"),
    ("Gas-Cprime", "uniform_co2_free",
     "H2, CH4, CO uniformly scaled; CO2 determined by carbon closure (~31x measured gas CO2); char = 0"),
    ("Gas-A", "h2_measured_ch4_max",
     "Experimental H2 and CO preserved; maximum feasible CH4 with char = 0 and feed N retained in the "
     "residue; CO2 ~54x measured"),
)
OFFGAS_FATE = ("BURNED: PSA off-gas assumed collected and burned in the U2 burner (simple natural gas offset, up to "
               "U2's fuel demand); no burner, flue gas or capital modeled; no CH4 emission; biogenic CO2 GWP 0")


def _small(method):
    from biorefineries.sabre.systems._att_system import create_att_system
    return inv._simulate(create_att_system(dry_sargassum_kgph=1.0, u2_gas_closure=method), 1.0)


def _gas_comparison(systems):
    measured = {k: float(v) for k, v in _ATT["reactor"]["cases"]["Ni-CatATT"]["gas_yield_mmol_per_g_daf"].items()}
    rows = []
    for gas in ("H2", "CH4", "CO", "CO2"):
        row = dict(gas=gas, experimental_mmol_per_g_daf=measured[gas],
                   experimental_ratio_to_H2=measured[gas] / measured["H2"])
        for m, sys in systems.items():
            y = inv._units(sys)["U2"]._model_gas_yield_mmol_per_g_daf
            row[f"{m}_mmol_per_g_daf"] = y[gas]
            row[f"{m}_ratio_to_H2"] = y[gas] / y["H2"] if y["H2"] else float("nan")
            row[f"{m}_deviation"] = y[gas] / measured[gas] - 1 if measured[gas] else float("nan")
        rows.append(row)
    status = {}
    for m, sys in systems.items():
        U2 = inv._units(sys)["U2"]
        status[m] = (f"s = {U2._gas_scale_factor:.4f}" if m == "uniform_redox_scaling" else "") + \
                    (" | ELEMENT/REDOX CLOSED" if not U2._unresolved_element_kmolph else
                     f" | NOT CLOSED: O {list(U2._unresolved_element_kmolph.values())[0] * 1e3 / U2._daf_sargassum_kgph:.1f} mmol/g daf")
    rows.append(dict(gas="status", experimental_mmol_per_g_daf=float("nan"), experimental_ratio_to_H2=float("nan"),
                     **{f"{m}_mmol_per_g_daf": status[m] for m in systems}))
    return rows


def _s_feasibility(sys):
    """s for defensible residue assumptions (U2 inlet fixed; unit-level)."""
    U2 = inv._units(sys)["U2"]
    rows = []
    for name, atoms in (("CH0.5O0.1 (baseline char)", None), ("CH0.3O0.05", {"C": 1, "H": 0.3, "O": 0.05}),
                        ("CH0.8O0.2", {"C": 1, "H": 0.8, "O": 0.2})):
        r = evaluate_att_u2_variant(sys, char_atoms=atoms)
        rows.append(dict(assumption=f"char formula {name}", s=r["scale_factor_s"], note="NaOH conversion 100 %"))
    base = U2.naoh_to_na2co3_conversion
    try:
        for x in (0.9, 0.8):
            U2.naoh_to_na2co3_conversion = x
            U2._run()
            rows.append(dict(assumption=f"NaOH -> Na2CO3 conversion {x}", s=U2._gas_scale_factor,
                             note="less carbonate -> more char C -> fewer electrons for gases"))
    finally:
        U2.naoh_to_na2co3_conversion = base
        U2._run()
    rows.append(dict(assumption="Result", s=U2._gas_scale_factor,
                     note="s is unique for each residue assumption (C, H, O + electrons); 100 % conversion and "
                          "the baseline char give the maximum defensible s"))
    return rows


def _gas_scenarios():
    """Full-scale results of the selected element-balanced gas-yield scenarios."""
    from biorefineries.sabre.analyses.att import lca
    from biorefineries.sabre.systems._att_system import create_att_system

    scale = inv.get_att_reference_scale()
    baseline = _ATT["reactor"]["material_balance"]["gas_closure_method"]
    rows = []
    gwp_ch4 = lca._LCA["indicative_gwp100"]["CH4_non_fossil"]["value"]
    for label, method, note in GAS_SCENARIOS:
        sys = inv._simulate(create_att_system(dry_sargassum_kgph=scale["dry_feed_kgph"], u2_gas_closure=method),
                            scale["dry_feed_kgph"])
        sys.operating_hours = scale["operating_hours_per_year"]
        est = inv.get_att_cost_estimates(sys)
        U2 = inv._units(sys)["U2"]
        s = inv._streams(sys)
        dry = inv._dry_feed_kgph(sys)
        y = U2._model_gas_yield_mmol_per_g_daf
        util = {r["item"]: r["per_kg_dry"] for r in inv.get_att_purchased_utilities(sys, est)}
        check = inv.check_att_inventory(sys)
        msp = tea_mod.evaluate_att_tea(sys, est)["msp"]
        msp_a = tea_mod.evaluate_att_tea(sys, est, caco3=dict(fraction=0.0))["msp"]
        tea_mod.evaluate_att_tea(sys, est)
        applied = lca.apply_att_gwp(sys, estimates=est)
        total = lca.get_att_gwp_contributions(sys, applied)[-1]
        h2 = float(s["h2_product"].imass["H2"]) / dry
        residue = U2.outs[1]
        char = residue.chemicals["Char"]
        char_C_fraction = char.atoms["C"] * 12.011 / char.MW
        offgas_ch4 = float(s["u3_tail_gas"].imass["CH4"]) / dry
        rows.append({
            "scenario": label, "closure": method, "basis": note,
            "status": "BASELINE" if method == baseline else "ALTERNATIVE SCENARIO (not baseline)",
            "H2_mmol_per_g_daf": y["H2"], "CH4_mmol_per_g_daf": y["CH4"], "CO_mmol_per_g_daf": y["CO"],
            "CO2_mmol_per_g_daf": y["CO2"], "scale_factor_s": U2._gas_scale_factor,
            # Char = CH0.5O0.1 pseudo-component (residue.imass["Char"]); carbon
            # = Char kmol x 1 C x 12.011. Feed N and S retained as CharN/CharS.
            "char_mass_kg_per_kg_dry": float(residue.imass["Char"]) / dry,
            "char_carbon_kg_C_per_kg_dry": float(residue.imol["Char"]) * char.atoms["C"] * 12.011 / dry,
            "char_carbon_mass_fraction": char_C_fraction,
            "residue_N_S_kg_per_kg_dry": float(residue.imass["CharN"] + residue.imass["CharS"]) / dry,
            "H2_product_kg_per_kg_dry": h2, "H2_product_t_per_yr": h2 * dry * sys.operating_hours / 1e3,
            "offgas_CH4_kg_per_kg_dry": offgas_ch4,
            "U2_utility_MJ_per_kg_dry": U2._utility_heat_duty_kJph / dry / 1e3,
            "natural_gas_total_MJ_per_kg_dry": util["U2 natural gas: fuel input (LHV)"]
            + util["LP steam: boiler natural gas (LHV)"],
            "electricity_kWh_per_kg_dry": util["Electricity: total"],
            "NaOH_makeup_kg_per_kg_dry": float(s["fresh_naoh_solid"].F_mass) / dry,
            "CaOH2_kg_per_kg_dry": float(s["lime"].F_mass) / dry,
            "MSP_TEA_reference_USD_per_kg_H2": msp, "MSP_TEA_CaseA_CaCO3_disposal_USD_per_kg_H2": msp_a,
            "GWP_kgCO2e_per_kg_H2": total["GWP_kgCO2e_per_kg_H2"],
            "GWP_kgCO2e_per_kg_dry": total["GWP_kgCO2e_per_kg_dry"],
            "offgas_fate": OFFGAS_FATE,
            "offgas_CH4_if_vented_kgCO2e_per_kg_H2_NOT_IN_GWP": offgas_ch4 * gwp_ch4 / h2,
            "mass_relative_error": check["mass_relative_error"],
            "max_element_relative_error": max(abs(v) for v in check["element_relative_error"].values()),
        })
    return rows


def _unvalidated():
    return [dict(item=a, status=b, effect=c) for a, b, c in (
        ("U2 feed HHV 16.9 MJ/kg daf (literature, not measured)", "UNVALIDATED", "U2 utility 8.1-9.7 MJ/kg dry range"),
        ("U2 pseudo-component Hf (re-referenced to HHV)", "ENGINEERING", "included in the HHV range"),
        ("U2 char formula / Hf (Channiwala-Parikh)", "ASSUMED", "s 0.59-0.60; duty within the uncertainty range"),
        ("U2 gas yields = s x measured", "RECONCILED (not measured)", "H2 product and MSP scale with s"),
        ("EC1 simple model (latent heat, constant boiling-point elevation)", "ASSUMED",
         "heat of concentration (~6 % of EC1 duty) lumped into the U2 term"),
        ("EC1 dissolved Na2CO3 fraction (5 %)", "SINGLE SOURCE", "<10 kJ/kg dry"),
        ("NaOH heat of solution 1113 kJ/kg (U2 inlet correction)", "SOURCES 1048-1113 kJ/kg", "about +/-5 % of the U2 correction"),
        ("C1 concentrated-solution enthalpy", "BOUNDED, not modeled", "-0.2 to +1.2 % of plant heat"),
        ("P1 power 37.2 kWh/t wet (BioSTEAM)", "PENDING DECISION", "alternative 5 kWh/t dry lowers MSP and GWP"),
        ("PSA off-gas (mainly CH4) burned in the U2 burner", "SIMPLE OFFSET (no burner modeled)",
         "natural gas displaced up to U2's fuel demand; indicative venting impact in D7 (not in GWP)"),
        ("PSA capital", "PRELIMINARY (+/-50 %)", "small MSP effect"),
    )]


def build_att_final_results():
    warnings.filterwarnings("ignore")
    systems = {m: _small(m) for m in METHODS}
    base_small = systems["uniform_redox_scaling"]
    ind = rep.build_att_consolidated_results()
    ref = tea_mod.create_att_tea_system()
    check = inv.check_att_inventory(ref)
    audit = ([dict(item="Overall mass relative error", value=check["mass_relative_error"])]
             + [dict(item=f"Element {e} relative error", value=v) for e, v in check["element_relative_error"].items()]
             + [dict(item=f"Unit {r['unit']} worst mass/element error",
                     value=max(abs(r["mass_relative_error"]),
                               *(abs(r[f"{e}_relative_error"]) for e in ("C", "H", "O", "N", "Na", "Ca"))))
                for r in inv.get_att_unit_balances(ref)])
    unc = get_att_u2_energy_uncertainty(ref)
    dry = inv._dry_feed_kgph(ref)
    u2_unc = [dict(item="U2 status", value=unc["range_status"]),
              dict(item="U2 baseline utility [MJ/kg dry]", value=unc["baseline"]["external_heating_kJph"] / dry / 1e3),
              dict(item="U2 primary range (HHV 16.3-18.1) [MJ/kg dry]",
                   value=str([round(x / dry / 1e3, 3) for x in unc["primary_sensitivity_range_kJph"]["external_heating"]])),
              dict(item="U2 secondary range (HHV 15.7-19.5) [MJ/kg dry]",
                   value=str([round(x / dry / 1e3, 3) for x in
                              unc["secondary_sensitivity_range_literature_HHV_kJph"]["external_heating"]])),
              dict(item="Excluded from range", value="; ".join(unc["excluded_from_range"]))]
    tables = {
        "C1_Process_Materials": ind["01_process_materials"],
        "C2_Mass_Element_Audit": audit,
        "C3_Unit_Energy_Balance": inv.get_att_unit_energy_balance(ref),
        "C4_Utilities": inv.get_att_purchased_utilities(ref, inv.get_att_cost_estimates(ref)),
        "C5_U2_Energy_Uncertainty": u2_unc,
        "C6_Heat_Recovery_Optional": rep._heat_integration(ref),
        "C7_TEA_CAPEX": ind["02_tea_capex"],
        "C8_TEA_OPEX_Reference": ind["03_tea_opex_reference"],
        "C8b_TEA_OPEX_Case_A": ind["03b_tea_opex_case_A"],
        "C9_MSP_Cases": ind["04_msp_cases"],
        "C10_GWP100": ind["05_gwp100"],
        "C11_Sensitivities": ind["06_sensitivities"],
        "C12_Collection_Transport": ind["07_collection_transport"],
        "C13_TEA_LCA_Consistency": ind["08_consistency_checks"],
        "C14_Unvalidated_Assumptions": _unvalidated(),
        "D1_Gas_Yields_and_Ratios": _gas_comparison(systems),
        "D2_Scale_Factor_Feasibility": _s_feasibility(base_small),
        "D6_Key_Findings": ind["00_key_findings"],
        "D7_Gas_Yield_Scenarios": _gas_scenarios(),
    }
    return tables


_README = """# ATT final results

Generated by `python -m biorefineries.sabre.test.run_att_final`
(`biorefineries/sabre/analyses/att/final.py`).

This folder holds the complete comparison workbook `ATT_Final_Results.xlsx`
(sheets C and D) and the D1, D2, D6 and D7 CSVs. The C sheets are also
written as CSV to `../full_scale/summary/`.

- **C (C1-C14):** industrial BioSTEAM model at the SaBRe scale (15,000 wet t/d,
  330 d/yr) with the baseline U2 closure: all four measured gases x s
  (s = 0.5998), element- and redox-closed. Model gas yields are engineering
  predictions, not measurements.
- **D (D1, D2, D6, D7):** measured vs simulated gas yields and ratios,
  scale-factor feasibility, key findings, and D7: selected element-balanced
  gas-yield scenarios at full scale: Gas-C (uniform_redox_scaling, s = 0.5998,
  baseline), Gas-Cprime (uniform_co2_free) and Gas-A (h2_measured_ch4_max,
  H2-prioritized). Gas-Cprime and Gas-A set char = 0 and exceed the measured
  gas CO2; they are selected feasible modeling scenarios, not global physical
  bounds or confidence intervals. Gas-A is unrelated to TEA Case A (CaCO3
  filter cake disposed). D7 reports char mass (CH0.5O0.1) and char carbon
  separately. The PSA off-gas is burned in the U2 burner (natural gas offset,
  no burner equipment modeled): no CH4 emission is included in GWP; the
  indicative venting impact is reported, not added.

Reproduce all ATT results in dependency order (from any directory):

```
python -m biorefineries.sabre.test.run_att_all
```

## Sheets

{sheets}
"""


def _write_tables(out_dir, workbook, tables, csv_names):
    """Workbook with all ``tables``; one CSV for each name in ``csv_names``."""
    import pandas as pd

    os.makedirs(out_dir, exist_ok=True)
    with pd.ExcelWriter(os.path.join(out_dir, workbook), engine="openpyxl") as writer:
        for name, rows in tables.items():
            df = pd.DataFrame(rows)
            if name in csv_names:
                df.to_csv(os.path.join(out_dir, f"{name}.csv"), index=False)
            df.to_excel(writer, sheet_name=name[:31], index=False)
            # Notes such as "= delivered / burner efficiency" are text, not formulas.
            for row in writer.sheets[name[:31]].iter_rows():
                for cell in row:
                    if cell.data_type == "f":
                        cell.data_type = "s"


def export_att_final_results(out_dir=None, summary_dir=None):
    """
    ATT_Final_Results.xlsx with all sheets (C-D), README.md and the D
    comparison CSVs go to ``out_dir`` (default att_outputs/comparison). The
    full-scale sheets C1-C14 are written as CSV to ``summary_dir`` (default
    att_outputs/full_scale/summary; ``out_dir`` when only ``out_dir`` is given).
    """
    import pandas as pd
    from biorefineries.sabre.analyses.att.paths import output_dir

    if summary_dir is None:
        summary_dir = out_dir if out_dir is not None else output_dir("summary")
    out_dir = os.fspath(out_dir or output_dir("comparison"))
    summary_dir = os.fspath(summary_dir)
    tables = build_att_final_results()
    _write_tables(out_dir, "ATT_Final_Results.xlsx", tables, [n for n in tables if n.startswith("D")])
    os.makedirs(summary_dir, exist_ok=True)
    for name, rows in tables.items():
        if name.startswith("C"):
            pd.DataFrame(rows).to_csv(os.path.join(summary_dir, f"{name}.csv"), index=False)
    sheets = "\n".join(f"- `{name}` ({len(rows)} rows)" for name, rows in tables.items())
    with open(os.path.join(out_dir, "README.md"), "w", encoding="utf-8") as f:
        f.write(_README.replace("{sheets}", sheets))
