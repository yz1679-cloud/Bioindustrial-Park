"""
Final ATT results: (A) original UCLA experimental data, (B) laboratory-scale
screening LCA, (C) industrial-scale BioSTEAM material/energy/TEA/LCA with the
baseline U2 closure (att.yaml), and (D) comparisons. Reuses att.experiment,
att.reporting, att.inventory and att.thermodynamics.
Writes att_final/ATT_Final_Results.xlsx, one CSV per sheet and README.md.
"""
import os
import warnings

from biorefineries.sabre.analyses.att import reporting as rep
from biorefineries.sabre.analyses.att import experiment as exp
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
OFFGAS_FATE = ("UNRESOLVED: PSA off-gas assumed collected; final fate (combustion, utilization or venting) not "
               "modeled; no treatment equipment or cost (placeholder sensitivity only); no CH4 emission, combustion "
               "CO2 or credit in GWP; biogenic CO2 GWP 0")


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


def _lab_vs_model(sys_small, lab_rows, ref):
    U2 = inv._units(sys_small)["U2"]
    daf = float(U2._daf_sargassum_kgph)
    s = inv._streams(sys_small)
    case = _ATT["reactor"]["cases"]["Ni-CatATT"]
    q_lab = next(r["amount_per_run"] for r in lab_rows if r["item"] == "Total heat, lower bound") / 0.5  # kJ/g = MJ/kg
    rows = [
        ("NaOH charged per kg daf", 2.0, float(U2.ins[0].imass["NaOH"]) / daf, "kg/kg daf", "same loading"),
        ("NaOH consumed per kg daf", 2.0, float(s["fresh_naoh_solid"].F_mass) / daf, "kg/kg daf",
         "lab single pass; model recovers 78 % (makeup only)"),
        ("Ca(OH)2 per kg daf", 0.0, float(s["lime"].F_mass) / daf, "kg/kg daf", "lab has no causticization"),
        ("Water/steam into reactor per kg daf", 7.2, float(U2.ins[0].imass["Water"]) / daf, "kg/kg daf",
         "lab flow-through steam; model = 50 % moisture + recycle-liquor water"),
        ("H2 at reactor outlet per kg daf", float(case["gas_yield_mmol_per_g_daf"]["H2"]) * 2.01588e-3,
         float(U2.outs[0].imass["H2"]) / daf, "kg/kg daf", "model = s x measured"),
        ("Reactor heat per kg daf", q_lab, U2._utility_heat_duty_kJph / daf / 1e3, "MJ/kg daf",
         "lab: theoretical lower bound (no reaction heat); model: U2 utility incl. reaction and 5 % loss"),
        ("Electricity per kg daf (full scale)", float("nan"),
         ref.power_utility.rate / float(inv._units(ref)["U2"]._daf_sargassum_kgph), "kWh/kg daf",
         "lab not reported; model value from the full-scale run (1 kg/h has minimum-size artifacts)"),
    ]
    return [dict(quantity=a, laboratory=b, model_1kgph=c, unit=d, note=e) for a, b, c, d, e in rows]


def _lca_comparison(lab_rows, ind):
    total = next(r for r in ind["05_gwp100"] if r["view"] == "by input" and r["item"].startswith("TOTAL"))
    lab = {r["item"]: r["GWP_g_CO2e_per_g_H2"] for r in lab_rows if r["category"] == "Result"}
    return [
        dict(case="Laboratory screening: NaOH + heat by natural gas (lower bound)",
             GWP_kgCO2e_per_kg_H2=lab["Screening GWP: NaOH + heat by natural gas"],
             boundary="single run, single-pass NaOH, theoretical heat only; excludes furnace losses, N2, catalyst",
             comparable="NO (different boundary, no recovery loop, heat lower bound)"),
        dict(case="Laboratory screening: NaOH + heat by electricity (lower bound)",
             GWP_kgCO2e_per_kg_H2=lab["Screening GWP: NaOH + heat by electricity"],
             boundary="as above, 100 % efficient electric heating", comparable="NO"),
        dict(case="Industrial BioSTEAM baseline (cradle-to-gate, partial: no collection/transport)",
             GWP_kgCO2e_per_kg_H2=total["GWP_kgCO2e_per_kg_H2"],
             boundary="P1-D0 preparation, U2, U3/PSA, NaOH recovery with causticization, utilities, waste treatment",
             comparable="reference industrial result"),
    ]


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


def _differences():
    rows = [
        ("Feed basis", "0.5 g daf per run (ash not reported)", "1,990 dry t/d, SaBRe ash 34.53 %, moisture 86.73 %"),
        ("Gas yields", "measured H2, CH4, CO, CO2", "s x measured (s = 0.5998), element- and redox-closed"),
        ("Water", "3.6 g steam per run (7.2 g/g daf), flow-through", "feed moisture 50 % + recycle liquor water"),
        ("NaOH", "1 g per run, single pass", "2 kg/kg daf charged, 78 % recovered, makeup only"),
        ("Carrier/catalyst", "N2 50 mL/min; Ni-soaked feed + Ni/ZrO2", "no carrier; catalyst not modeled"),
        ("Heat", "electric furnace (energy not reported)", "natural-gas furnace (U2), steam (D0, C1, EC1)"),
        ("Downstream", "none", "gas cooling, drying, PSA, H2 compression, causticization, evaporation"),
        ("LCA boundary", "screening: NaOH + heat lower bound", "cradle-to-gate excl. collection/transport"),
        ("Functional unit", "g H2 measured per run", "kg H2 product (PSA, 20 bar)"),
        ("Allocation", "none", "none (no CaCO3, CH4 or off-gas credit)"),
    ]
    return [dict(aspect=a, laboratory_experiment=b, industrial_model=c) for a, b, c in rows]


def _unvalidated():
    return [dict(item=a, status=b, effect=c) for a, b, c in (
        ("U2 feed HHV 16.9 MJ/kg daf (literature, not measured)", "UNVALIDATED", "U2 utility 8.1-9.7 MJ/kg dry range"),
        ("U2 pseudo-component Hf (re-referenced to HHV)", "ENGINEERING", "included in the HHV range"),
        ("U2 char formula / Hf (Channiwala-Parikh)", "ASSUMED", "s 0.59-0.60; duty within the uncertainty range"),
        ("U2 gas yields = s x measured", "RECONCILED (not measured)", "H2 product and MSP scale with s"),
        ("EC1 NaOH(aq) properties (Olsson)", "VALIDATED (boiling points, Cp, dilution heat)", "+/-1.7 % duty"),
        ("EC1 Na2CO3 solubility near 50 wt% NaOH", "SINGLE SOURCE", "<10 kJ/kg dry"),
        ("C1 concentrated-solution enthalpy", "BOUNDED, not modeled", "-0.2 to +1.2 % of plant heat"),
        ("P1 power 37.2 kWh/t wet (BioSTEAM)", "PENDING DECISION", "alternative 5 kWh/t dry lowers MSP and GWP"),
        ("PSA off-gas (mainly CH4) final fate", "UNRESOLVED (collected; treatment not modeled)",
         "GWP excludes CH4 emission; indicative venting impact in D7 (not in GWP)"),
        ("PSA capital", "PRELIMINARY (+/-50 %)", "small MSP effect"),
    )]


def build_att_final_results():
    warnings.filterwarnings("ignore")
    systems = {m: _small(m) for m in METHODS}
    base_small = systems["uniform_redox_scaling"]
    daf_frac = float(inv._units(base_small)["U2"]._daf_sargassum_kgph) / inv._dry_feed_kgph(base_small)
    A = exp.build_att_experiment_tables(daf_frac)
    lab = A.pop("B1_Lab_Screening_LCA")
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
        "A1_Experimental_Gas_Yields": A["A1_Experimental_Gas_Yields"],
        "A2_Experimental_Conditions": A["A2_Experimental_Conditions"],
        "A3_Experimental_Conversions": A["A3_Conversions_NiCatATT"],
        "A4_Workbook_Verification": A["A4_Workbook_Verification"],
        "B1_Lab_Screening_LCA": lab,
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
        "D3_Lab_vs_Model_Material_Energy": _lab_vs_model(base_small, lab, ref),
        "D4_LCA_Lab_vs_Industrial": _lca_comparison(lab, ind),
        "D5_Boundary_Differences": _differences(),
        "D6_Key_Findings": ind["00_key_findings"],
        "D7_Gas_Yield_Scenarios": _gas_scenarios(),
    }
    return tables


_README = """# ATT final results

Generated by `biorefineries/sabre/test/run_att_final.py`
(`biorefineries/sabre/analyses/att/final.py`).

- **A (sheets A1-A4):** original UCLA data transcribed in
  `biorefineries/sabre/data/att_experiment.yaml` with sheet!cell references and
  verified against "ATT Inputs and Assumptions_261005.xlsx" (A4).
- **B (B1):** laboratory screening LCA per run and per g measured H2. The
  workbook reports no LCA results; B1 uses measured inputs, the collaborators'
  emission factors and a thermodynamic lower bound for heating. Not comparable
  with C (see D4, D5).
- **C (C1-C14):** industrial BioSTEAM model at the SaBRe scale (15,000 wet t/d,
  330 d/yr) with the baseline U2 closure: all four measured gases x s
  (s = 0.5998), element- and redox-closed. Model gas yields are engineering
  predictions, not measurements.
- **D (D1-D7):** experimental vs simulated gas yields and ratios, scale-factor
  feasibility, lab vs model material/energy, lab vs industrial LCA,
  boundary differences, key findings, and D7: selected element-balanced
  gas-yield scenarios at full scale: Gas-C (uniform_redox_scaling, s = 0.5998,
  baseline), Gas-Cprime (uniform_co2_free) and Gas-A (h2_measured_ch4_max,
  H2-prioritized). Gas-Cprime and Gas-A set char = 0 and exceed the measured
  gas CO2; they are selected feasible modeling scenarios, not global physical
  bounds or confidence intervals. Gas-A is unrelated to TEA Case A (CaCO3
  filter cake disposed). D7 reports char mass (CH0.5O0.1) and char carbon
  separately. PSA off-gas fate is UNRESOLVED: no CH4 emission or treatment is
  included in GWP/MSP; the indicative venting impact is reported, not added.

Reproduce (after regenerating att_tea/ and att_lca/):

```
.venv/Scripts/python.exe biorefineries/sabre/test/run_att_final.py --out att_final
```

## Sheets

{sheets}
"""


def export_att_final_results(out_dir="att_final"):
    import pandas as pd

    tables = build_att_final_results()
    os.makedirs(out_dir, exist_ok=True)
    with pd.ExcelWriter(os.path.join(out_dir, "ATT_Final_Results.xlsx")) as writer:
        for name, rows in tables.items():
            df = pd.DataFrame(rows)
            df.to_csv(os.path.join(out_dir, f"{name}.csv"), index=False)
            df.to_excel(writer, sheet_name=name[:31], index=False)
            # Notes such as "= delivered / burner efficiency" are text, not formulas.
            for row in writer.sheets[name[:31]].iter_rows():
                for cell in row:
                    if cell.data_type == "f":
                        cell.data_type = "s"
    sheets = "\n".join(f"- `{name}` ({len(rows)} rows)" for name, rows in tables.items())
    with open(os.path.join(out_dir, "README.md"), "w", encoding="utf-8") as f:
        f.write(_README.replace("{sheets}", sheets))
    return tables
