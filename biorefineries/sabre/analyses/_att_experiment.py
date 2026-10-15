"""
UCLA ATT experimental reference dataset and laboratory-scale screening LCA.

All experimental values come from data/att_experiment.yaml, a cell-referenced
transcription of "ATT Inputs and Assumptions_261005.xlsx" (checked against the
workbook by verify_att_experiment_workbook when the file is available). The
workbook reports LCA inputs (functional unit, emission factors, boundary) but
no GWP results; the laboratory LCA here is a clearly labeled screening
estimate built only from measured inputs plus a thermodynamic lower bound for
heating. It is NOT comparable with the industrial LCA without harmonization.
"""
import os

import thermosteam as tmo

from biorefineries.sabre.utils import load_assumptions

__all__ = (
    "get_att_experimental_gas_yields",
    "get_att_experimental_conditions",
    "get_att_experimental_conversions",
    "verify_att_experiment_workbook",
    "get_att_lab_screening_lca",
    "build_att_experiment_tables",
)

EXP = load_assumptions("att_experiment.yaml")
_FEEDSTOCK = load_assumptions("feedstock.yaml")
GASES = ("H2", "CH4", "CO", "CO2")
_MW = {"H2": 2.01588, "CH4": 16.04246, "CO": 28.0101, "CO2": 44.0095, "Gas4": 28.0101}
_E = {"H2": 2, "CH4": 8, "CO": 2, "CO2": 0}
_STP_ML_PER_MMOL = 22.414         # ideal gas, 0 C and 1 atm
_N2_DENSITY_G_PER_L = 1.2506      # 0 C, 1 atm
_SHEET1 = EXP["experimental_results"]["sheet"]
_SHEET2 = EXP["energy_analysis"]["sheet"]


def get_att_experimental_gas_yields():
    er = EXP["experimental_results"]
    cols = er["column_cells"]
    rows = []
    for case, d in er["cases"].items():
        for gas in (*GASES, "Gas4"):
            rows.append(dict(case=case, description=d["description"], gas=gas, yield_mmol_per_g_daf=d[gas],
                             source=f"{_SHEET1}!{cols[gas]}{d['row']}", status="MEASURED (UCLA)",
                             note="ignored in the model (CO on 2nd GC column)" if gas == "Gas4" else ""))
    return rows


def get_att_experimental_conditions():
    er, ea = EXP["experimental_results"], EXP["energy_analysis"]
    rows = [dict(group="Experiment", item="Conditions", value=er["conditions"]["text"], unit="",
                 source=f"{_SHEET1}!{er['conditions']['cell']}", status="REPORTED")]
    for case, d in er["cases"].items():
        for k in ("seaweed_g", "naoh_g", "water_g"):
            rows.append(dict(group=f"Experiment {case}", item=k, value=d[k], unit="g",
                             source=f"{_SHEET1}!{er['column_cells'][k]}{d['row']}", status="REPORTED"))
    for note in er["notes"]:
        rows.append(dict(group="Experiment", item="Note", value=note, unit="", source="data/att_experiment.yaml",
                         status="CONTEXT"))
    for group in ("feedstock", "process", "emission_factors", "boundary"):
        for k, d in ea[group].items():
            rows.append(dict(group=f"Energy-analysis sheet: {group}", item=k, value=d["value"],
                             unit=d.get("unit", ""), source=f"{_SHEET2}!{d['cell']}",
                             status="COLLABORATOR ASSUMPTION" if group != "emission_factors" else "COLLABORATOR EF",
                             note=" | ".join(str(d[x]) for x in ("note", "range") if x in d)))
    rows.append(dict(group="Energy-analysis sheet", item="LCA results reported", value=ea["results_reported"],
                     unit="", source=_SHEET2, status="FINDING"))
    return rows


def get_att_experimental_conversions(case="Ni-CatATT", model_daf_frac=None):
    """Per-run, per-mass and model-basis conversions of the reported data."""
    d = EXP["experimental_results"]["cases"][case]
    daf_g = float(d["seaweed_g"])        # advisor-confirmed daf basis
    rows = []

    def add(item, value, unit, basis, status="CALCULATED from measured"):
        rows.append(dict(case=case, item=item, value=value, unit=unit, basis=basis, status=status))

    add("Sargassum per run (daf)", daf_g, "g", "reported 0.5 g; daf basis advisor-confirmed", "REPORTED")
    add("NaOH per run", d["naoh_g"], "g", "reported", "REPORTED")
    add("NaOH : daf", d["naoh_g"] / daf_g, "g/g daf", "NaOH / daf")
    add("Steam per run", d["water_g"], "g", "0.03 mL/min x 1 h (reported 3.6 g)", "REPORTED")
    add("Steam : daf", d["water_g"] / daf_g, "g/g daf", "steam / daf")
    add("N2 carrier per run", 50 * 60 / 1000, "L", "50 mL/min x 60 min (laboratory only)")
    add("N2 carrier per run", 50 * 60 / 1000 * _N2_DENSITY_G_PER_L, "g", "x 1.2506 g/L (0 C, 1 atm)")
    total_gas_g = 0.0
    for gas in GASES:
        y = float(d[gas])
        mmol = y * daf_g
        g = mmol * _MW[gas] / 1000
        total_gas_g += g
        add(f"{gas} per run", mmol, "mmol", "yield x 0.5 g daf")
        add(f"{gas} per run", g, "g", "x molar mass")
        add(f"{gas} per run (gas volume)", mmol * _STP_ML_PER_MMOL, "mL (0 C, 1 atm)", "ideal gas")
        add(f"{gas} per kg daf", y * _MW[gas] / 1000, "kg/kg daf", "yield x molar mass")
        add(f"{gas} / H2 molar ratio", y / float(d["H2"]), "mol/mol", "experimental ratio")
        if model_daf_frac:
            add(f"{gas} at 1 kg dry/h (model basis)", y * model_daf_frac * _MW[gas] / 1000, "kg/h",
                f"yield x {model_daf_frac:.4f} kg daf/h (SaBRe ash)")
    add("Measured gas mass per run", total_gas_g, "g", "sum of four gases")
    add("Measured gas mass / daf", total_gas_g / daf_g, "g/g daf", "")
    add("Available electrons in measured gases", sum(_E[g] * float(d[g]) for g in GASES), "mmol e-/g daf",
        "H2 x2, CH4 x8, CO x2 (diagnostic)")
    return rows


def verify_att_experiment_workbook(path=None):
    """Compare data/att_experiment.yaml with the source workbook cell by cell."""
    path = path or EXP["source_workbook"]["local_path"]
    if not os.path.exists(path):
        return [dict(check="Source workbook available", value=path, status="NOT AVAILABLE (YAML used as transcribed)")]
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    rows = []
    er = EXP["experimental_results"]
    ws = wb[_SHEET1]
    for case, d in er["cases"].items():
        for k, col in er["column_cells"].items():
            cell = f"{col}{d['row']}"
            got = ws[cell].value
            ok = got == d[k] if isinstance(d[k], str) else abs(float(got) - float(d[k])) <= 1e-12 * max(1.0, abs(float(d[k])))
            rows.append(dict(check=f"{_SHEET1}!{cell} ({case} {k})", value=str(got), status="PASS" if ok else "FAIL"))
    ws2 = wb[_SHEET2]
    for group in ("feedstock", "process", "emission_factors"):
        for k, d in EXP["energy_analysis"][group].items():
            got = ws2[d["cell"]].value
            ok = (got == d["value"]) if isinstance(d["value"], str) else abs(float(got) - float(d["value"])) < 1e-12
            rows.append(dict(check=f"{_SHEET2}!{d['cell']} ({k})", value=str(got), status="PASS" if ok else "FAIL"))
    return rows


def _heat_lower_bound_kJ(daf_g, naoh_g, water_g, T_K):
    """Sensible + latent heat to bring the charge from 25 C to T (no reaction)."""
    from biorefineries.sabre._chemicals import create_chemicals
    chems = create_chemicals(set_thermo=False)
    thermo = tmo.Thermo(chems)
    out = {}
    water = tmo.Stream(None, Water=water_g / 1000, units="kg/hr", thermo=thermo, phase="l", T=298.15)
    H0 = water.H
    water.phase, water.T = "g", T_K
    out["Steam (25 C liquid -> vapor at T)"] = water.H - H0
    naoh = tmo.Stream(None, NaOH=naoh_g / 1000, units="kg/hr", thermo=thermo, phase="s", T=298.15)
    H0 = naoh.H
    naoh.phase, naoh.T = "l", T_K
    out["NaOH (25 C solid -> molten at T)"] = naoh.H - H0
    comp = {k: v for k, v in _FEEDSTOCK["dry_composition"].items() if k != "Ash"}
    total = sum(comp.values())
    seaweed = tmo.Stream(None, units="kg/hr", thermo=thermo, phase="s", T=298.15,
                         **{k: v / total * daf_g / 1000 for k, v in comp.items()})
    H0 = seaweed.H
    seaweed.T = T_K
    out["Sargassum daf (sensible, SaBRe pseudo-components)"] = seaweed.H - H0
    return out


def get_att_lab_screening_lca(case="Ni-CatATT"):
    """
    Screening GWP of one laboratory run, per g of measured H2. Uses only
    measured inputs, the collaborators' emission factors and a thermodynamic
    lower bound for heating (actual furnace electricity was not reported).
    """
    d = EXP["experimental_results"]["cases"][case]
    ef = EXP["energy_analysis"]["emission_factors"]
    daf_g, naoh_g, water_g = float(d["seaweed_g"]), float(d["naoh_g"]), float(d["water_g"])
    h2_g = float(d["H2"]) * daf_g * _MW["H2"] / 1000
    lca = load_assumptions("att_lca.yaml")["lca"]["emission_factors"]
    grid = float(lca["electricity"]["value"])        # kg CO2e/kWh (industrial study factor, for consistency)
    heat = _heat_lower_bound_kJ(daf_g, naoh_g, water_g, 773.15)
    Q = sum(heat.values())
    rows = []

    def add(category, item, amount, unit, EF, EF_unit, gwp_g, status, note=""):
        rows.append(dict(category=category, item=item, amount_per_run=amount, unit=unit, EF=EF, EF_unit=EF_unit,
                         GWP_g_CO2e_per_run=gwp_g, GWP_g_CO2e_per_g_H2=gwp_g / h2_g if gwp_g == gwp_g else gwp_g,
                         status=status, note=note))

    add("Input", "Sargassum (daf)", daf_g, "g", 0.0, "waste biomass", 0.0, "MEASURED", "zero burden (study convention)")
    add("Input", "NaOH (single pass, not recovered)", naoh_g, "g", ef["NaOH"]["value"], "g CO2e/g",
        naoh_g * ef["NaOH"]["value"], "MEASURED amount; collaborator EF", f"EF range {ef['NaOH']['range']}")
    add("Input", "Steam water", water_g, "g", float("nan"), "", float("nan"), "MEASURED amount; water EF negligible")
    add("Input", "N2 carrier", 50 * 60 / 1000 * _N2_DENSITY_G_PER_L, "g", float("nan"), "", float("nan"),
        "CALCULATED amount; EF MISSING", "laboratory carrier, not a process feed")
    add("Input", "Ni/ZrO2 catalyst and Ni impregnation", float("nan"), "g", float("nan"), "", float("nan"),
        "MISSING (mass not reported)")
    for name, kJ in heat.items():
        add("Heat (lower bound)", name, kJ, "kJ", float("nan"), "", float("nan"), "THEORETICAL", "no reaction heat")
    add("Heat (lower bound)", "Total heat, lower bound", Q, "kJ", float("nan"), "", float("nan"), "THEORETICAL",
        "actual electric furnace energy NOT reported")
    ng = ef["natural_gas_heat"]["value"]
    add("Heat supply option", "Natural gas (burner 0.90)", Q / 0.9 / 1000, "MJ fuel", ng, "kg CO2/MJ",
        Q / 0.9 / 1000 * ng * 1000, "SCREENING (lower bound)", "collaborator NG factor, combustion only")
    add("Heat supply option", "Electricity (100 % efficient)", Q / 3600, "kWh", grid, "kg CO2e/kWh",
        Q / 3600 * grid * 1000, "SCREENING (lower bound)", "GREET 2022 US mix (att_lca.yaml); lab furnace far less efficient")
    for gas in GASES:
        g = float(d[gas]) * daf_g * _MW[gas] / 1000
        add("Output", f"{gas} (measured)", g, "g", float("nan"), "", float("nan"), "MEASURED",
            "functional-unit product" if gas == "H2" else "not credited; CH4 fate unknown")
    naoh_gwp = naoh_g * ef["NaOH"]["value"]
    for label, heat_gwp in (("NaOH + heat by natural gas", Q / 0.9 / 1000 * ng * 1000),
                            ("NaOH + heat by electricity", Q / 3600 * grid * 1000)):
        add("Result", f"Screening GWP: {label}", float("nan"), "", float("nan"), "", naoh_gwp + heat_gwp,
            "SCREENING, lower bound, partial boundary",
            "excludes furnace inefficiency, N2, catalyst, CH4 fate; single-pass NaOH")
    add("Result", "H2 per run (measured)", h2_g, "g", float("nan"), "", float("nan"), "MEASURED", "functional unit basis")
    add("Result", "Experimental LCA reported by collaborators", float("nan"), "", float("nan"), "", float("nan"),
        "NOT REPORTED", EXP["energy_analysis"]["results_reported"])
    return rows


def build_att_experiment_tables(model_daf_frac=0.6547):
    return {
        "A1_Experimental_Gas_Yields": get_att_experimental_gas_yields(),
        "A2_Experimental_Conditions": get_att_experimental_conditions(),
        "A3_Conversions_NiCatATT": get_att_experimental_conversions("Ni-CatATT", model_daf_frac),
        "A4_Workbook_Verification": verify_att_experiment_workbook(),
        "B1_Lab_Screening_LCA": get_att_lab_screening_lca("Ni-CatATT"),
    }
