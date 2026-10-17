# Bioindustrial-Park: BioSTEAM's Premier Biorefinery Models and Results
# Copyright (C) 2026-, Yu Zhou,
#                      Yalin Li <mailto.yalin.li@gmail.com>
#
# This module is under the UIUC open-source license. See
# github.com/BioSTEAMDevelopmentGroup/biosteam/blob/master/LICENSE.txt
# for license details.

"""ATT reporting: consolidated results and the master documentation package.

Consolidated research-stage ATT results (process, TEA, GWP100) on one frozen
system, built only from the inventory (mass/energy), tea (SaBReTEA cases) and
lca (BioSTEAM GWP100) modules. Adds only the collection/transport sensitivity
and TEA-LCA consistency checks. Writes att_outputs/full_scale/summary/att_consolidated_results.xlsx.

The master documentation package (data extraction and traceability only)
builds ATT_Master_Model_Documentation.xlsx, one CSV per sheet and README.md
in att_outputs/documentation/ from the frozen ATT system (SaBRe reference scale) and
the existing analysis functions in inventory, lca, tea and the consolidated
results above. Nothing here changes the process model or the LCA/TEA
parameters; every value is either read from the frozen system, computed by an
existing analysis function, or read from a configuration file (cited by key).
"""
import os

import biosteam as bst

from biorefineries.sabre.analyses.att import inventory as inv
from biorefineries.sabre.analyses.att import lca
from biorefineries.sabre.analyses.att import tea as tea_mod
from biorefineries.sabre.utils import load_assumptions

__all__ = (
    "build_att_documentation",
    "export_att_documentation",
    "build_att_consolidated_results",
    "export_att_consolidated_results",
)


# ==========================================================================
# Master documentation package
# ==========================================================================

FILES = {
    "att.yaml": "biorefineries/sabre/data/att.yaml",
    "feedstock.yaml": "biorefineries/sabre/data/feedstock.yaml",
    "tea.yaml": "biorefineries/sabre/data/tea.yaml",
    "att_lca.yaml": "biorefineries/sabre/data/att_lca.yaml",
    "att_tea.yaml": "biorefineries/sabre/data/att_tea.yaml",
    "preprocessing.yaml": "biorefineries/sabre/data/preprocessing.yaml",
}
WORKBOOK = "ATT_Master_Model_Documentation.xlsx"
EXP, SDB, BSD, LIT, ENG, CALC = ("Experimental (UCLA)", "SaBRe database", "BioSTEAM default", "Literature",
                                 "Engineering assumption", "Model calculation")
NV = "Source not verified"
ORIGIN_SYS = "frozen BioSTEAM system (direct extraction)"


def Y(file, key):
    """Value of a dotted key in a configuration file."""
    d = load_assumptions(file)
    for part in key.split("."):
        d = d[part]
    return d


def _fmt(v):
    if isinstance(v, float):
        return round(v, 10)
    return v


# ---------------------------------------------------------------------------
# Curated parameter register (values are read from configuration files)
# ---------------------------------------------------------------------------

def _register_rows():
    """
    (section, parameter, value, unit, unit_op, description, source_category,
     exact_source, file:key, status, notes, affects, baseline/sensitivity,
     uncertainty, collaborator confirmation)
    """
    r = []

    def add(section, parameter, value, unit, unit_op, description, cat, exact, filekey, status, notes="",
            affects="Process", basis="Baseline", uncertainty="", confirm="No"):
        r.append(dict(section=section, parameter=parameter, value=_fmt(value), unit=unit, process_unit=unit_op,
                      description=description, source_category=cat, exact_source=exact, file_key=filekey,
                      assumption_status=status, notes=notes, affects=affects, baseline_or_sensitivity=basis,
                      uncertainty_or_limitation=uncertainty, collaborator_confirmation_needed=confirm))

    fs = "feedstock.yaml"
    add("Feedstock", "Feedstock type (ATT-only)", Y("att.yaml", "att.feed_preparation.feedstock_type"), "-", "feed",
        "NLR preprint fresh Sargassum", SDB, "NLR preprint (Wiatrowski et al.)", "att.yaml:att.feed_preparation.feedstock_type",
        "ATT-only case; 3 million wet t/yr of fresh Sargassum (NLR scale)")
    add("Feedstock", "Feedstock type (integrated)", Y("att.yaml", "att.feed_preparation.integrated_feedstock_type"), "-",
        "feed", "NLR preprint pressed Sargassum", SDB, "NLR preprint (Wiatrowski et al.)",
        "att.yaml:att.feed_preparation.integrated_feedstock_type",
        "Integrated case: presscake of the biostimulant plant, no P1")
    ftype = Y("att.yaml", "att.feed_preparation.feedstock_type")
    add("Feedstock", "Moisture as harvested", Y(fs, f"feedstock_type.{ftype}.moisture_frac"), "kg/kg wet", "feed",
        "Initial wet-basis moisture", SDB, "NLR preprint", f"feedstock.yaml:feedstock_type.{ftype}.moisture_frac",
        "Preprint value", affects="Process, LCA, TEA")
    add("Feedstock", "Ash", Y(fs, f"feedstock_type.{ftype}.ash_wt_frac_dry"), "kg/kg dry", "feed",
        "Ash content (dry basis)", SDB, "NLR preprint", f"feedstock.yaml:feedstock_type.{ftype}.ash_wt_frac_dry",
        "Preprint value", affects="Process, LCA, TEA")
    for comp, v in Y(fs, f"feedstock_type.{ftype}.dry_composition").items():
        add("Feedstock", f"Dry composition: {comp}", v, "kg/kg dry", "feed", "SaBRe pseudo-component", SDB,
            "NLR preprint, mapped to pseudo-components", f"feedstock.yaml:feedstock_type.{ftype}.dry_composition.{comp}",
            "Preprint-based", affects="Process, LCA, TEA",
            uncertainty="OtherSolids (29 % dry) modeled as glucan-like C6H10O5", confirm="Yes (CHNS-O of sample)")
    add("Scale", "Wet feed capacity", Y("att.yaml", "att.feed_preparation.scale.wet_feed_tonnes_per_year"), "t wet/yr",
        "plant", "NLR preprint plant scale (fresh Sargassum)", SDB, "NLR preprint (3 million wet t/yr)",
        "att.yaml:att.feed_preparation.scale.wet_feed_tonnes_per_year", "Preprint value", affects="LCA, TEA")
    add("Scale", "Operating days", Y("tea.yaml", "operating_days"), "d/yr", "plant", "Annual operation", SDB,
        "SaBRe project assumption", "tea.yaml:operating_days", "Project-wide assumption",
        "7920 h/yr", "LCA, TEA")
    add("Preparation", "P1 press-cake moisture", Y("att.yaml", "att.feed_preparation.press_cake_moisture_wt_frac"),
        "kg/kg wet", "P1", "Mechanical dewatering outlet moisture", ENG, "NLR preprint, screw press on fresh Sargassum",
        "att.yaml:att.feed_preparation.press_cake_moisture_wt_frac", "Specified",
        affects="Process, LCA, TEA", uncertainty="Preprint pilot result")
    add("Preparation", "D0 outlet moisture", Y("att.yaml", "att.feed_preparation.att_sargassum_moisture_wt_frac"),
        "kg/kg wet", "D0", "Thermal drying target before U2", ENG, "Workbook 'assumed (mechanical dewatering)'; "
        "user-confirmed D0 requirement 2026-10-09", "att.yaml:att.feed_preparation.att_sargassum_moisture_wt_frac",
        "Specified", affects="Process, LCA, TEA")
    add("Preparation", "D0 temperature", Y("att.yaml", "att.feed_preparation.dryer_temperature_K"), "K", "D0",
        "Drying air outlet temperature", ENG, NV, "att.yaml:att.feed_preparation.dryer_temperature_K", "Specified")
    add("Preparation", "D0 thermal-duty basis", Y("att.yaml", "att.feed_preparation.dryer.thermal_duty_basis"), "-",
        "D0", "Ideal heat balance (no equipment specific energy)", ENG, "att.yaml dryer comment",
        "att.yaml:att.feed_preparation.dryer.thermal_duty_basis", "Specified",
        "Equipment specific-energy ranges reported, not used", "Process, LCA, TEA",
        uncertainty="Real drum dryers 3.2-6.5 MJ/kg water vs ~3.0 ideal")
    add("Preparation", "P1 power", Y("att.yaml", "att.feed_preparation.press.power_kWh_per_dry_ton"),
        "kWh/t dry solids", "P1", "Municipal biosolids screw press (ATT-only case)", ENG,
        "HUBER municipal screw press, 5 kWh per dry t", "att.yaml:att.feed_preparation.press.power_kWh_per_dry_ton",
        "Specified", "BioSTEAM ScrewPress alternative: 37.2 kWh/t total wet feed (see P1 comparison in the TEA tables)",
        "Process, LCA, TEA", "Baseline")
    add("ATT reaction", "U2 temperature", Y("att.yaml", "att.reactor.target_temperature_K"), "K", "U2",
        "ATT reactor temperature", EXP, "Workbook 'Experimental results' footnote (500 C)",
        "att.yaml:att.reactor.target_temperature_K", "Experimental condition")
    add("ATT reaction", "U2 pressure", 101325.0, "Pa", "U2", "Atmospheric", ENG, NV,
        "biorefineries/sabre/systems/_att_system.py (P=101325)", "Specified in code")
    add("ATT reaction", "Residence time (cost estimate only)", Y("att.yaml", "att.inventory.cost_estimates.U2_vessel.tau_h"),
        "h", "U2", "Vessel sizing for TEA", EXP, "Workbook footnote '1 h hold'",
        "att.yaml:att.inventory.cost_estimates.U2_vessel.tau_h", "Experimental hold time used for sizing",
        affects="TEA")
    add("ATT reaction", "NaOH : daf Sargassum", Y("att.yaml", "att.reactor.cases.Ni-CatATT.naoh_kg_per_kg_daf"),
        "kg/kg daf", "U2", "NaOH loading", EXP, "Experimental team Excel (energy and exergy calculation)",
        "att.yaml:att.reactor.cases.Ni-CatATT.naoh_kg_per_kg_daf", "Experimental team value",
        affects="Process, LCA, TEA")
    add("ATT reaction", "Fresh NaOH form", Y("att.yaml", "att.feed_preparation.fresh_naoh_form"), "-", "M1",
        "Makeup NaOH physical form", ENG, NV, "att.yaml:att.feed_preparation.fresh_naoh_form", "Specified")
    for gas in ("H2", "CH4", "CO", "CO2"):
        add("ATT reaction", f"Specified {gas} yield (Ni-CatATT)",
            Y("att.yaml", f"att.reactor.cases.Ni-CatATT.gas_yield_mmol_per_g_daf.{gas}"), "mmol/g daf", "U2",
            "Gas yield specified to U2", EXP, "Experimental team Excel (energy and exergy calculation)",
            f"att.yaml:att.reactor.cases.Ni-CatATT.gas_yield_mmol_per_g_daf.{gas}",
            "Specified; CO2 is topped up with the carbon not otherwise assigned",
            "Closes the electron balance (see U2 balance checks)",
            "Process, LCA, TEA",
            confirm="Yes (gas quantification)")
    add("ATT reaction", "U2 gas method", Y("att.yaml", "att.reactor.material_balance.gas_closure_method"), "-", "U2",
        "Specified gas yields; water from the oxygen balance; checks on NaOH capacity for CO2, electrons, mass, energy",
        ENG, "User decision 2026-10-16", "att.yaml:att.reactor.material_balance.gas_closure_method",
        "Model specification", "No all-element tracking: unidentified products are not modeled",
        "Process, LCA, TEA")
    add("ATT reaction", "NaOH -> Na2CO3 conversion", Y("att.yaml", "att.reactor.material_balance.naoh_to_na2co3_conversion"),
        "-", "U2", "SPECIFIED conversion (not measured)", ENG, "Workbook energy-analysis sheet: 100 %",
        "att.yaml:att.reactor.material_balance.naoh_to_na2co3_conversion", "Specified (workbook)",
        affects="Process, LCA, TEA", uncertainty="Not experimentally measured", confirm="Yes")
    add("ATT reaction", "Char formula", "CH0.5O0.1", "-", "U2", "Unconverted carbon residue", ENG,
        "biorefineries/sabre/_chemicals.py (Char); Hf from Channiwala-Parikh HHV correlation",
        "att.yaml:att.reactor.material_balance.char_species", "Assumed composition",
        uncertainty="Char not analysed; sensitivity CH0.3O0.05-CH0.8O0.2 in U2 energy analysis")
    add("ATT reaction", "Feed HHV (energy reference)", Y("att.yaml", "att.reactor.energy_basis.feed_HHV_MJ_per_kg_daf"),
        "MJ/kg daf", "U2", "Organic feed Hf re-referenced to this HHV", LIT,
        "Workbook energy-analysis sheet ('literature 15.7-19.5'); primary literature not identified",
        "att.yaml:att.reactor.energy_basis.feed_HHV_MJ_per_kg_daf", "Literature value (source not verified)",
        "Sensitivity 16.3-18.1 (composition-consistent), 15.7-19.5", "Process, LCA, TEA",
        uncertainty="Not measured for the sample", confirm="Yes")
    add("ATT reaction", "Heat loss (U2, C1, EC1)", Y("att.yaml", "att.reactor.heat_loss_fraction"), "of process heat",
        "U2, C1, EC1", "Utility = process heat x 1.05", LIT, "Workbook: 'Gracia-Monforte et al. 2026'",
        "att.yaml:att.reactor.heat_loss_fraction; att.downstream.heat_loss_fraction", "Specified",
        affects="Process, LCA, TEA")
    gt = "att.gas_treatment"
    add("Gas treatment", "U3 condenser temperature", Y("att.yaml", f"{gt}.condenser_temperature_K"), "K", "U3HX/U3C",
        "Gas cooling and condensation", ENG, Y("att.yaml", f"{gt}.condenser_status"),
        f"att.yaml:{gt}.condenser_temperature_K", "Provisional")
    add("Gas treatment", "PSA H2 recovery", Y("att.yaml", f"{gt}.psa_h2_recovery"), "-", "U3P",
        "Ideal-selectivity PSA surrogate", ENG, Y("att.yaml", f"{gt}.psa_status"), f"att.yaml:{gt}.psa_h2_recovery",
        "Provisional", affects="Process, LCA, TEA", confirm="Yes")
    add("Gas treatment", "H2 product pressure", Y("att.yaml", f"{gt}.h2_product_pressure_Pa"), "Pa", "U3K",
        "Compressor outlet", ENG, Y("att.yaml", f"{gt}.h2_compressor_status"), f"att.yaml:{gt}.h2_product_pressure_Pa",
        "Provisional", affects="Process, LCA, TEA", confirm="Yes")
    add("Gas treatment", "H2 compressor efficiency", Y("att.yaml", f"{gt}.h2_compressor_efficiency"), "-", "U3K",
        "Isothermal efficiency", ENG, Y("att.yaml", f"{gt}.h2_compressor_status"),
        f"att.yaml:{gt}.h2_compressor_efficiency", "Provisional")
    ds = "att.downstream"
    add("Downstream", "RC1 residue cooling target", Y("att.yaml", "att.heat_recovery.residue_cooling_target_temperature_K"),
        "K", "RC1", "Residue cooled before dissolution", ENG, NV,
        "att.yaml:att.heat_recovery.residue_cooling_target_temperature_K", "Specified")
    add("Downstream", "D1 dissolution water", Y("att.yaml", f"{ds}.dissolution_water_kg_per_kg_Na2CO3"),
        "kg/kg Na2CO3 into D1", "D1", "Water for Na2CO3 dissolution", LIT, "Workbook: 'commercial causticizing'",
        f"att.yaml:{ds}.dissolution_water_kg_per_kg_Na2CO3", "Workbook value; user-confirmed 2026-10-10",
        affects="Process, LCA, TEA")
    add("Downstream", "Filtration solids recovery", Y("att.yaml", f"{ds}.filtration_solids_recovery"), "-",
        "F1, F2", "Insoluble solids retained", ENG, NV, f"att.yaml:{ds}.filtration_solids_recovery", "Ideal")
    add("Downstream", "F1 cake moisture", Y("att.yaml", f"{ds}.f1_cake_moisture_wt_frac"), "kg/kg wet cake", "F1",
        "Ash/char cake with entrained mother liquor", LIT, "att.yaml comment: 'literature-supported engineering "
        "baseline' (specific reference not recorded)", f"att.yaml:{ds}.f1_cake_moisture_wt_frac",
        "Engineering baseline", affects="Process, LCA, TEA", uncertainty=NV)
    add("Downstream", "F2 cake moisture", Y("att.yaml", f"{ds}.f2_cake_moisture_wt_frac"), "kg/kg wet cake", "F2",
        "CaCO3 cake with entrained liquor", LIT, "att.yaml comment: 'CaCO3/lime-filtration literature review' "
        "(specific reference not recorded)", f"att.yaml:{ds}.f2_cake_moisture_wt_frac", "Engineering baseline",
        affects="Process, LCA, TEA", uncertainty=NV)
    add("Downstream", "C1 conversion", Y("att.yaml", f"{ds}.causticization_conversion"), "-", "C1",
        "SPECIFIED causticizing efficiency (not measured)", LIT, "Workbook: 'commercial causticizing' 85 %",
        f"att.yaml:{ds}.causticization_conversion", "Specified (workbook)", affects="Process, LCA, TEA")
    add("Downstream", "Ca(OH)2 : Na2CO3", Y("att.yaml", f"{ds}.lime_equiv"), "mol/mol stoich.", "C1",
        "Lime excess", LIT, "Workbook: 'commercial causticizing' 1.1", f"att.yaml:{ds}.lime_equiv",
        "Specified (workbook)", affects="Process, LCA, TEA", uncertainty="Largest cost and GWP driver")
    add("Downstream", "C1 temperature", Y("att.yaml", f"{ds}.causticization_temperature_K"), "K", "C1",
        "Causticization temperature", ENG, NV, f"att.yaml:{ds}.causticization_temperature_K", "Specified")
    add("Downstream", "Whole-liquor recycle", Y("att.yaml", f"{ds}.whole_liquor_recycle_fraction"), "-", "SP1",
        "Recycle fraction (purge 5 %)", EXP, "Collaborator '95 % NaOH recycling' read as whole-liquor recycle",
        f"att.yaml:{ds}.whole_liquor_recycle_fraction", "Interpretation, user-accepted",
        affects="Process, LCA, TEA", confirm="Yes")
    add("Downstream", "EC1 temperature", Y("att.yaml", f"{ds}.concentration_temperature_K"), "K", "EC1",
        "Boiling temperature (pressure = water vapor pressure at T - boiling-point elevation)", ENG, "User decision 2026-10-09 (90 C baseline)",
        f"att.yaml:{ds}.concentration_temperature_K", "Specified")
    add("Downstream", "EC1/M1 concentration target", Y("att.yaml", f"{ds}.recycle_naoh_wt_frac"),
        "NaOH/(NaOH+H2O)", "EC1, M1", "Binary basis after makeup", EXP,
        "Workbook 'Water left in recovered NaOH 50 wt%'; basis per user decision 2026-10-09",
        f"att.yaml:{ds}.recycle_naoh_wt_frac", "Specified", affects="Process, LCA, TEA")
    add("Downstream", "EC1 boiling-point elevation", Y("att.yaml", f"{ds}.ec1_boiling_point_elevation_K"), "K", "EC1",
        "Vapor condensation temperature = boiling temperature - elevation", LIT,
        "Olsson, Jernqvist, Aly, Int. J. Thermophys. 18 (1997) 779 (vapor pressure of ~44 wt% NaOH at 90 C)",
        f"att.yaml:{ds}.ec1_boiling_point_elevation_K", "Constant at the baseline outlet concentration",
        uncertainty="supplier boiling-point curves agree within 2.5 K")
    add("Downstream", "EC1 dissolved Na2CO3 fraction", Y("att.yaml", f"{ds}.ec1_na2co3_dissolved_fraction"), "-", "EC1",
        "Fraction of the Na2CO3 fed that stays dissolved; the rest crystallizes", LIT,
        "Wu, Liu, Wu, ACS Omega 5 (2020) 4875 (363.15 K, ~50 wt% NaOH)",
        f"att.yaml:{ds}.ec1_na2co3_dissolved_fraction", "Single-source near 50 wt% NaOH; solid identity unresolved",
        uncertainty="<0.1 % of plant heat")
    add("Downstream", "NaOH heat of solution", Y("att.yaml", f"{ds}.naoh_heat_of_solution_kJ_per_kg"), "kJ/kg NaOH", "U2",
        "Enthalpy correction of the dissolved NaOH in the recycle liquor", LIT,
        "NBS -44.5 kJ/mol; Olsson et al. 1997; OxyChem Caustic Soda Handbook Table 11",
        f"att.yaml:{ds}.naoh_heat_of_solution_kJ_per_kg", "Infinite dilution, same reference as C1",
        uncertainty="1048-1113 kJ/kg in the sources")
    for name, eta, src in (("U2 burner efficiency", Y("att.yaml", "att.energy_sources.natural_gas.burner_efficiency"),
                            "Workbook: 'IPCC 2006; burner eff. 0.90'"),
                           ("Steam boiler efficiency", Y("att_lca.yaml", "lca.natural_gas.boiler_efficiency"),
                            "BioSTEAM BoilerTurbogenerator default boiler_efficiency")):
        add("Energy", name, eta, "-", "U2" if "U2" in name else "steam", "Fuel (LHV) = delivered heat / efficiency",
            EXP if "U2" in name else BSD, src,
            "att.yaml:att.energy_sources.natural_gas.burner_efficiency" if "U2" in name
            else "att_lca.yaml:lca.natural_gas.boiler_efficiency", "Specified", affects="LCA, TEA",
            basis="Baseline (boiler 0.80-0.90 sensitivity)" if "boiler" in name.lower() else "Baseline")
    for k, v in Y("att_lca.yaml", "lca.emission_factors").items():
        add("LCA", f"EF {k}", v["value"], v["unit"], "LCA", v.get("boundary", ""),
            EXP if "collaborators" in v["source"] else LIT, v["source"], f"att_lca.yaml:lca.emission_factors.{k}",
            "Baseline" if k not in ("CaOH2_steel_slag", "marine_fuel") else "Scenario",
            v.get("note", ""), "LCA", f"range {v.get('range', '')}", v.get("status", ""),
            "Yes" if k in ("electricity",) else "No")
    for k, v in Y("att_tea.yaml", "tea.prices").items():
        if isinstance(v, dict):
            add("TEA", f"Price {k}", v["value"], "USD/kg", "TEA", "", LIT if "USGS" in v["source"] else
                (SDB if "tea.yaml" in v["source"] else LIT), v["source"], f"att_tea.yaml:tea.prices.{k}",
                "Baseline" if k != "CaOH2_updated" else "Scenario", v.get("year", ""), "TEA",
                f"range {v.get('range', '')}")
    for k in ("disposal_solid", "disposal_wastewater"):
        add("TEA", f"Price {k}", Y("tea.yaml", f"price.{k}.baseline"), "USD/kg", "TEA", "negative = cost", SDB,
            "SaBRe tea.yaml (notes: biosolids $30-80/dry t; WWT $3-8/m3)", f"tea.yaml:price.{k}.baseline",
            "Baseline", affects="TEA", uncertainty=f"range {Y('tea.yaml', f'price.{k}.range')}")
    add("TEA", "Price sargassum (delivered)", Y("tea.yaml", "price.sargassum.baseline"), "USD/kg wet", "TEA",
        "Collection/transport cost", SDB, Y("tea.yaml", "price.sargassum.source"), "tea.yaml:price.sargassum.baseline",
        "Baseline 0; sensitivity 0-50 USD/t", affects="TEA", confirm="Yes (logistics data)")
    for k, v in Y("tea.yaml", "tea").items():
        add("Financial", k, str(v) if isinstance(v, list) else v, "-", "SaBReTEA", "", SDB,
            "SaBRe tea.yaml (project financial convention)", f"tea.yaml:tea.{k}", "Baseline", affects="TEA")
    psa = Y("att.yaml", "att.gas_treatment.psa_cost")
    add("TEA", "PSA installed cost anchor", psa["anchor_installed_cost_usd"], "USD", "U3P",
        f"{psa['anchor_capacity_t_H2_per_day']} t H2/d, exponent {psa['exponent']}", LIT, psa["source"],
        "att.yaml:att.gas_treatment.psa_cost", psa["status"], affects="TEA", basis="Baseline (+/-50 %)",
        uncertainty="Primary reference and cost year not verified")
    add("TEA", "Equipment cost year", bst.CE, "CEPCI", "all equipment", "BioSTEAM default CE", BSD,
        "BioSTEAM settings (bst.CE)", "att_tea.yaml:tea.cost_year.reference_CE", "Baseline", affects="TEA",
        uncertainty="Prices are 2024-2025; ~2024 CEPCI comparison provided")
    return r


# ---------------------------------------------------------------------------
# System extraction
# ---------------------------------------------------------------------------

_UNIT_INFO = {
    "P1": ("Mechanical dewatering of wet Sargassum (municipal-type screw press; ATT-only case)", "att.yaml:att.feed_preparation.press_cake_moisture_wt_frac"),
    "D0": ("Thermal drying to 50 wt% moisture (steam drum dryer)", "att.yaml:att.feed_preparation.*"),
    "M1": ("Mix dried feed with recycled NaOH liquor", "-"),
    "U2": ("Alkaline thermal treatment at 500 C; NG-fired (auxiliary HXutility furnace)", "att.yaml:att.reactor.*"),
    "U3HX": ("Cool U2 gas to 40 C", "att.yaml:att.gas_treatment.condenser_temperature_K"),
    "U3C": ("Separate condensate at 40 C, 1 atm", "att.yaml:att.gas_treatment.condenser_*"),
    "U3D": ("Dry gas (molecular sieve)", "att.yaml:att.gas_treatment.dryer_water_to_dry_gas_fraction"),
    "U3P": ("PSA surrogate: 90 % H2 to product, rest to off-gas", "att.yaml:att.gas_treatment.psa_*"),
    "U3K": ("Compress dried gas to the 2 MPa H2 delivery pressure (PSA feed pressure if there is a PSA)", "att.yaml:att.gas_treatment.h2_*"),
    "RC1": ("Cool ATT residue to 90 C", "att.yaml:att.heat_recovery.residue_cooling_target_temperature_K"),
    "D1": ("Dissolve Na2CO3 residue in water (3 kg/kg Na2CO3)", "att.yaml:att.downstream.dissolution_water_kg_per_kg_Na2CO3"),
    "F1": ("Remove ash/char cake (pressure filter)", "att.yaml:att.downstream.f1_*"),
    "C1": ("Causticize Na2CO3 with Ca(OH)2 at 90 C", "att.yaml:att.downstream.causticization_*, lime_equiv"),
    "F2": ("Remove CaCO3 cake (rotary vacuum filter)", "att.yaml:att.downstream.f2_*"),
    "SP1": ("Split liquor: 95 % recycle, 5 % purge", "att.yaml:att.downstream.whole_liquor_recycle_fraction"),
    "EC1": ("Evaporate excess water at 90 C (vacuum, single effect)", "att.yaml:att.downstream.concentration_*, recycle_naoh_*"),
}
_ATTRS = ("T", "P", "moisture_content", "conversion", "lime_equiv", "target_temperature_K", "heat_loss_fraction",
          "eta", "compressor_type", "gas_closure_method", "naoh_kg_per_kg_daf",
          "naoh_to_na2co3_conversion", "feed_HHV_MJ_per_kg_daf", "vessel_material", "tau", "V")


def _units_table(sys, estimates):
    rows = []
    for u in sys.units:
        attrs = {}
        for a in _ATTRS:
            v = getattr(u, a, None)
            if isinstance(v, (int, float, str)) and not isinstance(v, bool):
                attrs[a] = round(v, 6) if isinstance(v, float) else v
        design = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in u.design_results.items()
                  if isinstance(v, (int, float, str))}
        items = getattr(type(u), "cost_items", {}) or {}
        cost_spec = "; ".join(f"{k}: basis {ci.basis} [{ci.units}], S={ci.S}, ub={ci.ub}, n={ci.n}, CE={ci.CE}"
                              for k, ci in items.items())
        func, cfg = _UNIT_INFO.get(u.ID, ("", ""))
        if not u.outs:   # facilities (HXN) have no streams
            continue
        out = u.outs[0]
        rows.append(dict(
            unit_ID=u.ID, BioSTEAM_class=type(u).__name__, function=func,
            inlet_streams=", ".join(s.ID for s in u.ins), outlet_streams=", ".join(s.ID for s in u.outs),
            outlet0_T_C=float(out.T) - 273.15, outlet0_P_kPa=float(out.P) / 1e3, key_settings=str(attrs),
            design_results=str(design), parallel_units=str(getattr(u, "parallel", {}) or ""),
            purchase_cost_USD=u.purchase_cost, installed_cost_USD=u.installed_cost,
            cost_correlation=cost_spec or ("BioSTEAM unit _cost" if u.purchase_cost > 0 else
                                           "no model cost (see TEA-only estimates)"),
            sizing_costing_source="native BioSTEAM" if u.purchase_cost > 0 else
            ("custom estimate (att.yaml inventory.cost_estimates)" if u.ID in ("C1", "EC1") else
             ("preliminary PSA estimate (att_tea.yaml)" if u.ID == "U3P" else "no equipment (junction)")),
            configuration=cfg, data_origin=ORIGIN_SYS))
    for r in estimates:
        rows.append(dict(unit_ID=r["unit"], BioSTEAM_class="TEA-only estimate", function=r["item"],
                         inlet_streams="", outlet_streams="", outlet0_T_C=float("nan"), outlet0_P_kPa=float("nan"),
                         key_settings=r["method"], design_results=r["size"], parallel_units="",
                         purchase_cost_USD=r["purchase_cost"], installed_cost_USD=r["installed_cost"],
                         cost_correlation=r["method"], sizing_costing_source="custom estimate",
                         configuration="att.yaml:att.inventory.cost_estimates", data_origin="att.inventory.get_att_cost_estimates"))
    for item, note in (("Pumps and conveyors", "Not modeled as units (not costed separately)"),
                       ("Steam boiler, cooling tower (utility facilities)", "Purchased utilities; no capital in baseline"),
                       ):
        rows.append(dict(unit_ID="-", BioSTEAM_class="not modeled", function=item, key_settings=note,
                         data_origin="documentation"))
    return rows


def _connectivity(sys):
    seen, rows = set(), []
    for u in sys.units:
        for s in (*u.ins, *u.outs):
            if s.ID in seen:
                continue
            seen.add(s.ID)
            rows.append(dict(stream=s.ID, from_unit=s.source.ID if s.source else "FEED (system input)",
                             to_unit=s.sink.ID if s.sink else "PRODUCT (system output)",
                             recycle="yes" if s.ID == "naoh_recycle" else ""))
    return rows


def _streams(sys):
    """Full internal and external stream inventory (long format)."""
    dry = inv._dry_feed_kgph(sys)
    hours = sys.operating_hours
    seen, rows = set(), []
    for u in sys.units:
        for s in (*u.ins, *u.outs):
            if s.ID in seen:
                continue
            seen.add(s.ID)
            F = float(s.F_mass)
            head = dict(stream=s.ID, from_unit=s.source.ID if s.source else "FEED",
                        to_unit=s.sink.ID if s.sink else "PRODUCT", T_C=float(s.T) - 273.15, P_kPa=float(s.P) / 1e3,
                        phase=s.phase)
            mass_sum = 0.0
            for ID, m, n in zip(s.chemicals.IDs, s.mass, s.mol):
                if m != 0.0:
                    mass_sum += float(m)
                    rows.append(dict(head, component=ID, kg_per_h=float(m), kmol_per_h=float(n),
                                     kg_per_kg_dry=float(m) / dry, t_per_yr=float(m) * hours / 1e3,
                                     mass_fraction=float(m) / F if F else float("nan")))
            rows.append(dict(head, component="TOTAL", kg_per_h=F, kmol_per_h=float(s.F_mol), kg_per_kg_dry=F / dry,
                             t_per_yr=F * hours / 1e3,
                             mass_fraction=mass_sum / F if F else float("nan")))
    return rows


def _streams_wide(long_rows):
    import pandas as pd
    df = pd.DataFrame([r for r in long_rows if r["component"] != "TOTAL"])
    wide = df.pivot_table(index="stream", columns="component", values="kg_per_kg_dry", aggfunc="sum").fillna(0.0)
    wide.insert(0, "TOTAL", wide.sum(axis=1))
    return wide.reset_index().to_dict("records")


def _naoh_extra(sys):
    s = inv._streams(sys)
    u = inv._units(sys)
    rows = []
    for ID in ("naoh_recycle", "liquor_to_concentrator", "naoh_carbonate_liquor",
               "carbonate_solution", "liquor_purge"):
        st = next((x for unit in sys.units for x in (*unit.ins, *unit.outs) if x.ID == ID), None)
        if st is None:
            continue
        naoh, w, c = float(st.imass["NaOH"]), float(st.imass["Water"]), float(st.imass["Na2CO3"])
        rows.append(dict(stream=ID, NaOH_over_NaOH_plus_H2O=naoh / (naoh + w) if naoh + w else float("nan"),
                         NaOH_over_total_mixture=naoh / float(st.F_mass) if st.F_mass else float("nan"),
                         Na2CO3_over_total_mixture=c / float(st.F_mass) if st.F_mass else float("nan"),
                         note="binary basis is the EC1 target (after the fresh NaOH makeup in M1)"))
    rows.append(dict(stream="SP1 purge fraction", NaOH_over_NaOH_plus_H2O=float("nan"), NaOH_over_total_mixture=float("nan"),
                     Na2CO3_over_total_mixture=float("nan"),
                     note=f"purge = {1 - Y('att.yaml', 'att.downstream.whole_liquor_recycle_fraction'):.2f} of liquor"))
    ec1 = u["EC1"]
    rows.append(dict(stream="EC1 operating pressure [Pa]", NaOH_over_NaOH_plus_H2O=ec1._operating_pressure_Pa,
                     NaOH_over_total_mixture=float("nan"), Na2CO3_over_total_mixture=float("nan"),
                     note="water vapor pressure at the condensation temperature"))
    return rows


def _crystallization_audit(sys):
    """
    Na2CO3 crystallization in EC1: inlet/outlet phases, the fixed dissolved
    fraction (att.yaml downstream.ec1_na2co3_dissolved_fraction), the unit
    mass balances and the Na2CO3 recycle fate. Values in kg/h at the
    reference scale and per 1 kg/h dry feed.
    """
    from biorefineries.sabre.units._att import _solid_na2co3_kgph

    u = inv._units(sys)
    s = inv._streams(sys)
    dry = inv._dry_feed_kgph(sys)
    EC1, U2 = u["EC1"], u["U2"]
    nan = float("nan")
    rows = []

    def add(section, item, ec1, unit, basis, per_kg_dry=True):
        scale = (lambda v: v / dry if isinstance(v, float) and v == v else nan) if per_kg_dry else (lambda v: nan)
        rows.append(dict(section=section, item=item, EC1=ec1, unit=unit,
                         EC1_per_kg_per_h_dry_feed=scale(ec1), basis=basis))

    def phases(stream):
        total = float(stream.imass["Na2CO3"])
        solid = _solid_na2co3_kgph(stream)
        return total, solid, total - solid

    # Inlet and outlet.
    ec1_in, ec1_out, ec1_cond = EC1.ins[0], EC1.outs[0], EC1.outs[1]
    e_tot, e_sol, e_dis = phases(ec1_in)
    eo_tot, eo_sol, eo_dis = phases(ec1_out)
    S = "1 Na2CO3 in and out"
    add(S, "Na2CO3 entering the unit (total)", e_tot, "kg/h", "inlet stream (SP1 liquor)")
    add(S, "  of which already solid in the inlet", e_sol, "kg/h", "inlet solid phase")
    add(S, "  of which dissolved in the inlet", e_dis, "kg/h", "inlet liquid phase")
    add(S, "Additional Na2CO3 precipitated in the unit", eo_sol - e_sol, "kg/h", "outlet solid - inlet solid")
    add(S, "Na2CO3 dissolved in the outlet", eo_dis, "kg/h", "outlet liquid phase")
    add(S, "Total solid Na2CO3 leaving the unit", eo_sol, "kg/h", "outlet solid phase")
    add(S, "Model attribute: crystals", EC1._na2co3_crystals_kgph, "kg/h", "EC1._na2co3_crystals_kgph")

    # Conditions.
    ec1_w, ec1_naoh = float(ec1_out.imass["l", "Water"]), float(ec1_out.imass["l", "NaOH"])
    S = "2 Conditions"
    add(S, "Outlet temperature", float(ec1_out.T) - 273.15, "C", "fixed boiling temperature", per_kg_dry=False)
    add(S, "Pressure", EC1._operating_pressure_Pa / 1e3, "kPa",
        "water vapor pressure at the boiling temperature minus the boiling-point elevation", per_kg_dry=False)
    add(S, "Water in the outlet liquor", ec1_w, "kg/h", "EC1 evaporates to the water limit")
    add(S, "Water evaporated", float(ec1_cond.F_mass), "kg/h", "EC1 condensate")
    add(S, "NaOH in the outlet liquor", ec1_naoh, "kg/h", "recovered NaOH; the fresh makeup is added in M1")
    add(S, "NaOH/(NaOH + H2O) in the outlet", ec1_naoh / (ec1_naoh + ec1_w), "-",
        "binary basis; the recycle target (0.50) applies after the fresh NaOH makeup in M1", per_kg_dry=False)
    add(S, "Dissolved fraction of the Na2CO3 fed", EC1.na2co3_dissolved_fraction, "-",
        "att.yaml downstream.ec1_na2co3_dissolved_fraction (assumption)", per_kg_dry=False)

    # Unit mass balances.
    S = "3 Mass balances"
    add(S, "Na2CO3: in - (dissolved out + solid out)", e_tot - eo_tot, "kg/h", "should be 0")
    add(S, "NaOH: in - out", float(ec1_in.imass["NaOH"]) - ec1_naoh, "kg/h", "should be 0")
    add(S, "Water: in - (out + evaporated)", float(ec1_in.imass["Water"]) - ec1_w - float(ec1_cond.F_mass), "kg/h",
        "should be 0")
    add(S, "Total mass: in - out", float(ec1_in.F_mass) - float(ec1_out.F_mass) - float(ec1_cond.F_mass), "kg/h",
        "should be 0")
    add(S, "Fresh solid NaOH added in M1", float(s["fresh_naoh_solid"].imass["NaOH"]), "kg/h", "M1 makeup")

    # Fate of the Na2CO3.
    S = "4 Na2CO3 recycle and losses"
    u2_in = float(U2.ins[0].imass["Na2CO3"])
    for item, v, basis in (
        ("Na2CO3 recycled to U2 with the liquor (EC1 -> M1 -> U2)", eo_tot, "all EC1 outlet Na2CO3, solid + dissolved"),
        ("  of which solid crystals", eo_sol, "crystals are not separated"),
        ("  of which dissolved", eo_dis, ""),
        ("Na2CO3 in the U2 feed", u2_in, "M1 outlet (M1 merges phases; Na2CO3 mass unchanged)"),
        ("Na2CO3 formed in U2 (NaOH + CO2)", float(U2.outs[1].imass["Na2CO3"]) - u2_in, "U2 residue - U2 feed"),
        ("Loss: Na2CO3 in ash/char cake (F1)", float(s["ash_residue_cake"].imass["Na2CO3"]), "entrained liquor"),
        ("Loss: Na2CO3 in CaCO3 cake (F2)", float(s["caco3_cake"].imass["Na2CO3"]), "entrained liquor"),
        ("Loss: Na2CO3 in liquor purge (SP1)", float(s["liquor_purge"].imass["Na2CO3"]),
         "purge is upstream of EC1: dissolved Na2CO3 only, no crystals"),
    ):
        add(S, item, v, "kg/h", basis)
    losses = sum(float(s[ID].imass["Na2CO3"]) for ID in ("ash_residue_cake", "caco3_cake", "liquor_purge"))
    add(S, "Recycled / (recycled + lost)", eo_tot / (eo_tot + losses), "-", "Na2CO3 basis", per_kg_dry=False)

    # Verification of the per-1-kg/h-dry values and the method.
    S = "5 Verification"
    from biorefineries.sabre.systems._att_system import create_att_system
    small = inv._simulate(create_att_system(dry_sargassum_kgph=1.0), 1.0)
    v = (eo_sol - e_sol) / dry
    v_small = inv._units(small)["EC1"]._na2co3_crystals_kgph
    same = abs(v - v_small) <= 1e-6 * max(abs(v), 1e-12)
    add(S, "EC1 precipitation [kg/h at 1 kg/h dry feed]", v, "kg/kg dry",
        f"converged model {v:.5f} (reference scale) = {v_small:.5f} (1 kg/h simulation): "
        f"{'PASS' if same else 'FAIL'}", per_kg_dry=False)
    expected_solid = e_tot * (1.0 - EC1.na2co3_dissolved_fraction)
    for item, a_, b_ in (("EC1 solid = Na2CO3 fed x (1 - dissolved fraction)", eo_sol, expected_solid),
                         ("Na2CO3 balance of EC1 closes", e_tot - eo_tot, 0.0)):
        add(S, item, a_, "kg/h", "PASS" if abs(a_ - b_) <= 1e-9 * max(1.0, abs(b_)) else "FAIL", per_kg_dry=False)
    add(S, "Method", nan, "",
        "ASSUMED, not calculated: a fixed fraction of the Na2CO3 fed stays dissolved and the rest crystallizes "
        "(att.yaml downstream.ec1_na2co3_dissolved_fraction, about 5 %, from the Wu et al. 2020 solubility "
        "near 50 wt% NaOH). Limitations: single source, solid identity (Na2CO3 vs Na2CO3.H2O) unresolved, "
        "crystals recycled to U2 (not separated).", per_kg_dry=False)
    return rows


def _products(sys):
    s = inv._streams(sys)
    dry = inv._dry_feed_kgph(sys)
    rows = []
    for ID in ("h2_product", "u3_tail_gas", "caco3_cake", "ash_residue_cake", "liquor_purge", "biostimulant_juice",
               "excess_condensate", "u3_dryer_removed_water", "dryer_exhaust"):
        if ID not in s:
            continue
        st = s[ID]
        F = float(st.F_mass)
        for comp, m in zip(st.chemicals.IDs, st.mass):
            if m > 0:
                rows.append(dict(stream=ID, fate=Y("att.yaml", f"att.inventory.stream_fates.{ID}")[1], component=comp,
                                 kg_per_kg_dry=float(m) / dry, mass_fraction=float(m) / F,
                                 basis="MODEL (specified gas yields)"))
    U2gas = inv._units(sys)["U2"].outs[0]
    rows.append(dict(stream="H2 before PSA (U2 gas)", fate="model", component="H2",
                     kg_per_kg_dry=float(U2gas.imass["H2"]) / dry, mass_fraction=float("nan"),
                     basis="MODEL (specified gas yields)"))
    return rows


def _energy_accounts(sys):
    u = inv._units(sys)
    dry = inv._dry_feed_kgph(sys)
    rows = []

    def put(unit, item, value, unit_label, note=""):
        rows.append(dict(account=unit, item=item, value=value, unit=unit_label, note=note))

    U2 = u["U2"]
    for k, v in U2.design_results.items():
        if isinstance(v, float) and any(w in k.lower() for w in ("duty", "enthalpy", "correction", "hhv")):
            put("U2", k, v / dry / 1e3, "MJ/kg dry", "ATTReactor.design_results (kJ/h normalized)")
    put("U2", "Process heat duty", U2._heat_duty_kJph / dry / 1e3, "MJ/kg dry", "Hnet(out) - Hnet(in) incl. corrections")
    put("U2", "Heat loss (5 %)", U2._heat_loss_kJph / dry / 1e3, "MJ/kg dry")
    put("U2", "Utility heat (NG furnace)", U2._utility_heat_duty_kJph / dry / 1e3, "MJ/kg dry")
    D0 = u["D0"]
    for k, v in D0.design_results.items():
        put("D0", k, v, D0._units.get(k, "") if hasattr(D0, "_units") else "", "DrumDryer.design_results (absolute)")
    for hu in D0.heat_utilities:
        put("D0", f"{hu.agent.ID} process duty", hu.unit_duty / dry / 1e3, "MJ/kg dry")
        put("D0", f"{hu.agent.ID} utility duty", hu.duty / dry / 1e3, "MJ/kg dry", "agent heat-transfer efficiency 0.95")
    evaporated = float(inv._streams(sys)["dryer_exhaust"].imass["Water"])
    put("D0", "Utility heat per kg water evaporated", sum(hu.duty for hu in D0.heat_utilities) / evaporated / 1e3,
        "MJ/kg water", "ideal heat balance; equipment 3.2-6.5 (att.yaml, not used)")
    C1 = u["C1"]
    for a, label in (("_heat_duty_kJph", "Process heat"), ("_heat_loss_kJph", "Heat loss"),
                     ("_utility_heat_duty_kJph", "Utility heat"), ("_sensible_phase_heat_kJph", "Sensible/phase term"),
                     ("_formation_reaction_heat_kJph", "Reaction (formation) term"),
                     ("_aqueous_reference_correction_kJph", "Aqueous-ion reference correction")):
        put("C1", label, getattr(C1, a) / dry / 1e3, "MJ/kg dry", "CausticizationReactor")
    EC1 = u["EC1"]
    for a, label, unit_label in (("_evaporated_water_kgph", "Evaporated water", "kg/kg dry"),
                                 ("_heat_duty_kJph", "Process heat", "MJ/kg dry"),
                                 ("_condenser_duty_kJph", "Condenser duty", "MJ/kg dry"),
                                 ("_utility_heat_duty_kJph", "Utility heat (steam)", "MJ/kg dry"),
                                 ("_heat_loss_kJph", "Heat loss", "MJ/kg dry")):
        v = getattr(EC1, a)
        put("EC1", label, v / dry if "kg/kg" in unit_label else v / dry / 1e3, unit_label, "NaOHEvaporator")
    put("EC1", "Specific heat per kg water", EC1._specific_heat_kJ_per_kg_water / 1e3, "MJ/kg water")
    put("EC1", "Operating pressure", EC1._operating_pressure_Pa / 1e3, "kPa")
    for ID in ("U3HX", "U3D", "U3K", "RC1"):
        x = u[ID]
        for hu in x.heat_utilities:
            put(ID, f"{hu.agent.ID} duty", hu.duty / dry / 1e3, "MJ/kg dry")
        put(ID, "Electricity", x.power_utility.rate / dry, "kWh/kg dry")
        for k, v in x.design_results.items():
            if isinstance(v, (int, float)):
                put(ID, k, v, x._units.get(k, "") if hasattr(x, "_units") else "", "design result (absolute)")
    return rows


def _energy_totals(sys, utilities):
    dry = inv._dry_feed_kgph(sys)
    hours = sys.operating_hours
    h2 = float(inv._streams(sys)["h2_product"].imass["H2"]) / dry
    u = {r["item"]: r["per_kg_dry"] for r in utilities}
    items = [("Natural gas, U2 fuel (LHV)", u["U2 natural gas: fuel input (LHV)"], "MJ"),
             ("Natural gas, steam boiler (LHV)", u["LP steam: boiler natural gas (LHV)"], "MJ"),
             ("Heat delivered by U2 furnace", u["U2 natural gas: heat delivered incl. 5 % reactor loss"], "MJ"),
             ("Heat delivered by LP steam", u["LP steam: utility heat incl. 5 % loss"], "MJ"),
             ("Cooling (heat removed)", u["Cooling water: heat removed"], "MJ"),
             ("Electricity (units + cooling tower + auxiliaries)", u["Electricity: total"], "kWh")]
    rows = []
    for name, v, unit in items:
        rows.append(dict(item=name, per_kg_dry=v, per_kg_H2=v / h2, per_hour_full_scale=v * dry,
                         per_year=v * dry * hours, unit=unit))
    ng = u["U2 natural gas: fuel input (LHV)"] + u["LP steam: boiler natural gas (LHV)"]
    rows.append(dict(item="Total natural gas (LHV)", per_kg_dry=ng, per_kg_H2=ng / h2, per_hour_full_scale=ng * dry,
                     per_year=ng * dry * hours, unit="MJ"))
    pe = ng + u["Electricity: total"] * 3.6
    rows.append(dict(item="Total purchased energy (NG LHV + electricity as 3.6 MJ/kWh)", per_kg_dry=pe,
                     per_kg_H2=pe / h2, per_hour_full_scale=pe * dry, per_year=pe * dry * hours, unit="MJ"))
    return rows


def _heat_integration(sys):
    """BioSTEAM HeatExchangerNetwork (HXN) summary; empty if the system has no HXN."""
    HXN = next((f for f in sys.facilities if type(f).__name__ == "HeatExchangerNetwork"), None)
    dry = inv._dry_feed_kgph(sys)
    if HXN is None:
        return [dict(section="status", item="no HeatExchangerNetwork in the system", value=float("nan"),
                     unit="", note="")]
    rows = [dict(section="status", item=f"HXN, minimum approach {HXN.T_min_app} K; U2 (fired) and RC1 (solids) excluded",
                 value=float("nan"), unit="", note="BioSTEAM HeatExchangerNetwork; process-process exchangers use BioSTEAM's default U")]
    for label, v in (("heating utility before", HXN.original_heat_util_load), ("heating utility after", HXN.actual_heat_util_load),
                     ("cooling utility before", HXN.original_cool_util_load), ("cooling utility after", HXN.actual_cool_util_load)):
        rows.append(dict(section="utility", item=label, value=v / dry / 1e3, unit="MJ/kg dry", note=""))
    for x in HXN.new_HXs:
        rows.append(dict(section="match", item=x.ID, value=x.Q / dry / 1e3, unit="MJ/kg dry",
                         note=f"installed {x.installed_cost / 1e6:.3f} MUSD at the 1 kg/h basis scale"))
    rows.append(dict(section="capital", item="HXN installed cost (net of the exchangers it replaces)",
                     value=HXN.installed_cost, unit="USD", note="BioSTEAM: max(0, new network - original exchangers)"))
    return rows


def _lca_register(contributions, applied):
    years = {"NaOH": "not stated (collaborators' table)", "Ca(OH)2": "not stated (collaborators' table)",
             "Natural gas U2: combustion": "IPCC 2006 default", "Natural gas boiler (LP steam): combustion": "IPCC 2006 default",
             "Natural gas U2: upstream supply": "2019 report (2016 data)",
             "Natural gas boiler (LP steam): upstream supply": "2019 report (2016 data)",
             "Electricity: process units": "GREET 2022", "Electricity: cooling tower and CW pumps": "Humbird 2011 x GREET 2022",
             "Electricity: outside unit models (agitators, EC1 vacuum)": "GREET 2022",
             "Process water (D1)": "Zib et al. 2021", "Wastewater treatment": "Zib et al. 2021",
             "Purge neutralization (H2SO4)": "GREET (version not stated in repository)",
             "Landfill: solid residues": "EPA WARM v15, 2019"}
    coverage = {"NaOH makeup": "BioSTEAM stream CF (fresh_naoh_solid)", "Ca(OH)2": "BioSTEAM stream CF (lime)",
                "Process water (D1)": "BioSTEAM stream CF (dissolution_water)",
                "Natural gas U2: combustion": "BioSTEAM utility-agent CF (natural_gas, kg basis)",
                "Natural gas U2: upstream supply": "BioSTEAM utility-agent CF (natural_gas, kg basis)",
                "Natural gas boiler (LP steam): combustion": "BioSTEAM utility-agent CF (low_pressure_steam, kJ)",
                "Natural gas boiler (LP steam): upstream supply": "BioSTEAM utility-agent CF (low_pressure_steam, kJ)",
                "Electricity: cooling tower and CW pumps": "BioSTEAM utility-agent CF (cooling_water, kg)",
                "Electricity: process units": "BioSTEAM PowerUtility CF"}
    rows = []
    for r in contributions:
        key = next((k for k in years if r["item"].startswith(k.split(":")[0]) and (":" not in k or r["item"] == k)), None)
        rows.append(dict(material_or_energy=r["item"], stage=r["stage"], activity_per_kg_dry=r["activity_per_kg_dry"],
                         activity_unit=r["activity_unit"], EF=r["EF"], EF_unit=r["EF_unit"],
                         GWP_kgCO2e_per_kg_dry=r["GWP_kgCO2e_per_kg_dry"], GWP_kgCO2e_per_kg_H2=r["GWP_kgCO2e_per_kg_H2"],
                         contribution_share=r["share"], source=r["source"],
                         source_year=years.get(r["item"], years.get(key, "")),
                         BioSTEAM_coverage=coverage.get(r["item"], "System.define_process_impact"
                                                         if not r["item"].startswith("TOTAL") else "System.get_net_impact"),
                         assumptions=""))
    return rows


def _opex_detail(sys, result):
    s = inv._streams(sys)
    dry = inv._dry_feed_kgph(sys)
    hours = sys.operating_hours
    h2_yr = float(s["h2_product"].imass["H2"]) * hours
    rows = []

    def add(name, cons_per_kg_dry, cons_unit, price, price_unit, annual_usd, source, year, purchased):
        rows.append(dict(item=name, consumption_per_kg_dry=cons_per_kg_dry, unit=cons_unit,
                         annual_consumption=cons_per_kg_dry * dry * hours, unit_price=price, price_unit=price_unit,
                         annual_cost_USD=annual_usd, USD_per_kg_H2=annual_usd / h2_yr, source=source, price_year=year,
                         accounting=purchased))

    P = tea_mod._T["prices"]
    for ID, name, key in (("fresh_naoh_solid", "NaOH (solid, 100 %)", "NaOH"), ("lime", "Ca(OH)2", "CaOH2"),
                          ("dissolution_water", "Process water", "process_water")):
        add(name, float(s[ID].F_mass) / dry, "kg", s[ID].price, "USD/kg", s[ID].cost * hours, P[key]["source"],
            P[key].get("year", "not stated"), "purchased")
    add("Sargassum (delivered)", float(s["att_sargassum_feed"].F_mass) / dry, "kg wet", s["att_sargassum_feed"].price,
        "USD/kg wet", s["att_sargassum_feed"].cost * hours, "tea.yaml price.sargassum.baseline", "-",
        "purchased (0 in baseline; see collection sensitivity)")
    gas = [hu for hu in sys.heat_utilities if hu.agent.ID == "natural_gas"]
    fuel = sum(hu.duty for hu in gas) / 1e3 / tea_mod._BURNER_EFFICIENCY
    ng_cost = sum(hu.cost for hu in gas) * hours + next(v for n, v in result["voc_items"] if n.startswith("Natural"))
    add("Natural gas, U2 (LHV)", fuel / dry, "MJ", tea_mod._ng_usd_per_MJ(), "USD/MJ", ng_cost,
        "BioSTEAM default natural_gas agent price, converted per MJ LHV", NV + " (BioSTEAM default)", "purchased")
    displaced = next((v for n, v in result["voc_items"] if n.startswith("Natural gas displaced")), 0.0)
    if displaced:
        add("Natural gas displaced by PSA tail gas", -inv.get_att_tail_gas_offset(sys)["offset_MJph"] / dry, "MJ",
            tea_mod._ng_usd_per_MJ(), "USD/MJ", displaced,
            "tail gas LHV burned in the U2 burner, priced at the natural gas price (att.yaml gas_treatment.tail_gas_combustion)",
            NV + " (BioSTEAM default)", "credit")
    for agent, label in (("low_pressure_steam", "LP steam"), ("cooling_water", "Cooling water (circulating)")):
        hus = [hu for hu in sys.heat_utilities if hu.agent.ID == agent]
        kg = sum(hu.flow * hu.agent.MW for hu in hus)
        a = bst.HeatUtility.get_agent(agent)
        add(label, kg / dry, "kg", a.regeneration_price / a.MW, "USD/kg", sum(hu.cost for hu in hus) * hours,
            f"BioSTEAM default {agent} price", NV + " (BioSTEAM default)",
            "purchased; includes generation (boiler fuel / tower power not priced again)")
    aux = next(v for n, v in result["voc_items"] if n.startswith("Electricity: agitators"))
    add("Electricity (units + auxiliaries)", (sys.power_utility.rate + aux / bst.PowerUtility.price / hours) / dry,
        "kWh", bst.PowerUtility.price, "USD/kWh", sys.power_utility.cost * hours + aux, "BioSTEAM default PowerUtility.price",
        NV + " (BioSTEAM default)", "purchased")
    h2so4 = lca._h2so4_kgph(sys)
    add("H2SO4 (purge neutralization)", h2so4 / dry, "kg", P["H2SO4"]["value"], "USD/kg",
        next(v for n, v in result["voc_items"] if n.startswith("Purge")), P["H2SO4"]["source"], "not stated", "purchased")
    for ID in (*tea_mod._T["prices"]["wastewater_streams"], *tea_mod._T["prices"]["solid_waste_streams"],
               "caco3_cake", "u3_tail_gas"):
        if ID not in s:      # no PSA, no off-gas
            continue
        add(f"Disposal: {ID}", float(s[ID].F_mass) / dry, "kg", -s[ID].price, "USD/kg (cost)",
            -s[ID].price * float(s[ID].F_mass) * hours, "tea.yaml disposal price" if ID != "caco3_cake"
            else "reference: 0; Case A: tea.yaml disposal_solid", "-", "service")
    tea = result["tea"]
    add("Fixed operating cost (labor, maintenance, overhead)", float("nan"), "-", tea_mod._FIN["foc_frac_of_fci"],
        "fraction of FCI/yr", tea.FOC, "tea.yaml tea.foc_frac_of_fci", "-",
        "fixed; labor and maintenance not itemized")
    return rows


def _capex_detail(sys, result):
    rows = []
    for u in sys.units:
        items = getattr(type(u), "cost_items", {}) or {}
        for name, purchase in u.baseline_purchase_costs.items():
            ci = items.get(name)
            rows.append(dict(item=f"{u.ID}: {name}", class_=type(u).__name__,
                             sizing_basis=str({k: round(v, 3) for k, v in u.design_results.items()
                                               if isinstance(v, float)})[:300],
                             parallel_units=str(getattr(u, "parallel", {}) or ""),
                             purchase_cost_USD=u.purchase_costs.get(name, purchase),
                             installed_cost_USD=u.installed_costs.get(name, float("nan")),
                             F_BM=u.F_BM.get(name, float("nan")), F_M=u.F_M.get(name, 1.0) if hasattr(u, "F_M") else 1.0,
                             correlation=(f"basis {ci.basis} [{ci.units}], S={ci.S}, ub={ci.ub}, n={ci.n}, CE={ci.CE}"
                                          if ci else "BioSTEAM unit _cost method"),
                             cost_year=f"CEPCI {bst.CE} (BioSTEAM)", source="native BioSTEAM"))
    for name, value, source in result["capital_items"]:
        purchase = float("nan")
        est = next((r for r in result["estimates"] if name.startswith(r["item"])), None)
        if est:
            purchase = est["purchase_cost"]
        rows.append(dict(item=name, class_="TEA-only estimate", sizing_basis=est["size"] if est else "",
                         parallel_units="", purchase_cost_USD=purchase, installed_cost_USD=value, F_BM=float("nan"),
                         F_M=float("nan"), correlation=source, cost_year=f"CEPCI {bst.CE}" if "PSA" not in name
                         else "not verified (anchor)", source="custom estimate"))
    tea = result["tea"]
    purchase_total = sum(u.purchase_cost for u in sys.units) + sum(
        r["purchase_cost_USD"] for r in rows[-len(result["capital_items"]):] if r["purchase_cost_USD"] == r["purchase_cost_USD"])
    for item, v in (("Total purchased equipment (PSA purchase not available)", purchase_total),
                    ("Total installed = DPI = TDC = FCI", tea.FCI), ("Working capital", tea.working_capital),
                    ("Total capital investment", tea.TCI)):
        rows.append(dict(item=item, class_="TOTAL", purchase_cost_USD=v if "purchased" in item else float("nan"),
                         installed_cost_USD=v if "purchased" not in item else float("nan"), source="SaBReTEA"))
    return rows


def _financial(result):
    tea = result["tea"]
    rows = [dict(parameter=k, value=str(v), source=f"tea.yaml:tea.{k}") for k, v in tea_mod._FIN.items()]
    rows += [
        dict(parameter="operating_days", value=tea.operating_days, source="tea.yaml:operating_days"),
        dict(parameter="operating_hours", value=tea.operating_days * 24, source="derived"),
        dict(parameter="lang_factor", value="None (installed costs from bare-module factors)", source="att.tea.evaluate_att_tea"),
        dict(parameter="FCI definition", value="FCI = DPI = TDC = installed equipment (no indirect capital)",
             source="SaBReTEA (bst.TEA defaults _DPI/_TDC/_FCI)"),
        dict(parameter="FOC", value=f"{tea_mod._FIN['foc_frac_of_fci']} x FCI per year (labor, maintenance, overhead)",
             source="biorefineries/sabre/_tea.py SaBReTEA._FOC"),
        dict(parameter="CEPCI", value=bst.CE, source="BioSTEAM default bst.CE"),
        dict(parameter="TEA class", value="ATTTEA(SaBReTEA): + extra installed capital, + extra VOC",
             source="biorefineries/sabre/analyses/att/tea.py"),
        dict(parameter="MSP solver", value="bst.TEA.solve_price (DCF, NPV = 0 at IRR)", source="BioSTEAM"),
    ]
    return rows


def _caco3_detail(sys, caco3):
    s = inv._streams(sys)
    hours = sys.operating_hours
    cake_t = float(s["caco3_cake"].F_mass) * hours / 1e3
    caco3_t = float(s["caco3_cake"].imass["CaCO3"]) * hours / 1e3
    disposal = -float(tea_mod._PRICE["disposal_solid"]["baseline"]) * 1e3
    rows = []
    for r in caco3:
        f = r["marketable_fraction"] if r["marketable_fraction"] == r["marketable_fraction"] else 0.0
        reference = r["case"].startswith("Reference")
        price = r["CaCO3_price_usd_per_t"] if r["CaCO3_price_usd_per_t"] == r["CaCO3_price_usd_per_t"] else 0.0
        handling = r["handling_usd_per_t"] if r["handling_usd_per_t"] == r["handling_usd_per_t"] else 0.0
        rows.append(dict(lime_price=r["lime_price"], case=r["case"], CaCO3_equivalent_t_per_yr=caco3_t,
                         wet_cake_t_per_yr=cake_t, marketable_fraction=f, CaCO3_price_USD_per_t=price,
                         handling_USD_per_t=handling, CaCO3_sold_t_per_yr=f * caco3_t,
                         revenue_MUSD_per_yr=f * caco3_t * price / 1e6,
                         handling_cost_MUSD_per_yr=f * caco3_t * handling / 1e6,
                         cake_disposal_cost_MUSD_per_yr=0.0 if reference else (1 - f) * cake_t * disposal / 1e6,
                         MSP_USD_per_kg_H2=r["MSP_USD_per_kg_H2"], delta_vs_case_A=r["delta_vs_case_A"],
                         price_status="ILLUSTRATIVE (not a demonstrated selling price)" if price else "-"))
    return rows


def _gaps_and_inconsistencies(lca_gaps):
    rows = [dict(type="Data gap (LCA)", item=r["item"], status=r["status"], magnitude=r["indicative_kgCO2e_per_kg_dry"],
                 note=r["note"], importance=r["importance"]) for r in lca_gaps]
    rows += [dict(type="TEA limitation", item=x, status="documented", magnitude=float("nan"), note="", importance="")
             for x in Y("att_tea.yaml", "tea.limitations")]
    inconsistencies = [
        ("att.yaml energy_sources.marine_fuel.emission_factor_kgCO2e_per_L = 3.2", "key says per litre; workbook and "
         "att_lca.yaml state 3.2 kg CO2/kg fuel. Key is not used by any calculation."),
        ("tea.yaml price.sargassum.scenario mid_cost_collect = high_cost_collect = 0.05", "range reaches 0.10; "
         "likely a typo in existing SaBRe data (not changed)."),
        ("tea.yaml price.naoh.baseline = 0.35", "note 'fermentation medium', source 'no literature source cited in "
         "legacy scripts'."),
        ("att.yaml reactor.legacy_heat_duty_kJ_per_kg_dry_sargassum = 10423.77", "not used by any code (legacy)."),
        ("att.yaml heat_recovery.minimum_approach_temperature_K = 5", "used only by legacy diagnostics "
         "(att.mass_energy); the HXN uses a 10 K minimum approach temperature."),
        ("att.yaml heat_recovery future_tail_gas_fuel_species / gas_energy_diagnostic_species list CH4, CO",
         "legacy diagnostic keys used only by att.mass_energy diagnostics."),
        ("att_inventory preliminary LCI (sheets 08/09)", "omits natural-gas upstream and waste treatment "
         "(46.7 kg CO2e/kg H2); superseded by att_lca (55.0)."),
        ("TEA Case A vs LCA baseline", "Case A disposes the CaCO3 cake; LCA baseline treats it as a burden-free "
         "coproduct; Case-A-consistent LCA = baseline + 0.76 kg CO2e/kg H2."),
        ("P1 power basis", "Municipal press 5 kWh/t dry adopted; BioSTEAM ScrewPress (37.2 kWh/t total wet feed) reported as the alternative."),
        ("feedstock.yaml dry_composition", "no citation in the file."),
    ]
    rows += [dict(type="Inconsistency / traceability", item=a, status="documented, not changed", magnitude=float("nan"),
                  note=b, importance="") for a, b in inconsistencies]
    return rows


def _yaml_register():
    def flat(d, p=""):
        if isinstance(d, dict):
            for k, v in d.items():
                yield from flat(v, f"{p}.{k}" if p else str(k))
        else:
            yield p, d
    rows = []
    for f in FILES:
        for k, v in flat(load_assumptions(f)):
            rows.append(dict(file=FILES[f], key=k, value=str(v)))
    return rows


def _overview(sys, result, gwp_total):
    scale = inv.get_att_reference_scale(tea_mod._configuration(sys))
    s = inv._streams(sys)
    dry = inv._dry_feed_kgph(sys)
    return [
        dict(item="Purpose", value="Research-stage ATT (alkaline thermal treatment) H2 process: mass/energy, GWP100, TEA",
             note="Documentation package; no model changes"),
        dict(item="Model", value=f"{tea_mod._configuration(sys)} case, U2 with specified gas yields "
                                 "(experimental team Excel); checks on NaOH capacity, electrons, mass, energy",
             note="biorefineries/sabre/systems/_att_system.py, units/_att.py"),
        dict(item="Simulation scale", value=scale["dry_feed_kgph"], note="kg/h dry (NLR scale: 3 million wet t/yr of fresh Sargassum)"),
        dict(item="Operating hours", value=sys.operating_hours, note="330 d x 24 h (tea.yaml)"),
        dict(item="Normalization", value="per kg dry Sargassum; per kg H2 (PSA product)", note=""),
        dict(item="H2 product", value=float(s["h2_product"].imass["H2"]) / dry, note="kg/kg dry"),
        dict(item="MSP reference / Case A", value=f"{result['msp']:.3f} / see MSP sheet", note="USD/kg H2"),
        dict(item="GWP100 (partial boundary)", value=gwp_total, note="kg CO2e/kg H2; collection/transport excluded"),
        dict(item="Modules", value="att.inventory -> att.lca, att.tea -> att.reporting (consolidated results, then documentation)",
             note="biorefineries/sabre/analyses"),
        dict(item="Data origin labels", value="frozen BioSTEAM system | analysis function | configuration input",
             note="see data_origin / source columns"),
    ]


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build_att_documentation():
    sys = tea_mod.create_att_tea_system()
    fingerprint = [float(x) for st in (*sys.feeds, *sys.products) for x in st.mass]
    estimates = inv.get_att_cost_estimates(sys)
    utilities = inv.get_att_purchased_utilities(sys, estimates)
    small_checks = inv.check_att_inventory(sys, None, utilities)

    # TEA (existing functions; each restores the reference prices).
    caco3 = tea_mod.get_att_caco3_cases(sys, estimates)
    lime = tea_mod.get_att_lime_price_cases(sys, estimates)
    sens_tea = tea_mod.get_att_tea_sensitivity(sys, estimates)
    p1 = tea_mod.get_att_p1_power_cases(sys, estimates)
    offgas = tea_mod.get_att_offgas_cases(sys, estimates)
    case_a = tea_mod.evaluate_att_tea(sys, estimates, caco3=dict(fraction=0.0))
    opex_a = _opex_detail(sys, case_a)
    result = tea_mod.evaluate_att_tea(sys, estimates)
    opex = _opex_detail(sys, result)
    capex = _capex_detail(sys, result)
    tea_checks = tea_mod._checks(sys, result, fingerprint)

    # LCA (existing module on the same system).
    applied = lca.apply_att_gwp(sys, estimates=estimates)
    contributions = lca.get_att_gwp_contributions(sys, applied)
    lca_checks = lca.check_att_lca(sys, applied, contributions, utilities)
    stage = lca.get_att_gwp_by_stage(contributions)
    by_unit = lca.get_att_gwp_by_unit(sys, applied)
    summary_lca = lca.get_att_gwp_summary(sys, applied)
    gaps = lca.get_att_lca_data_gaps(sys, applied)
    sens_lca = lca.get_att_gwp_sensitivity(sys, estimates)
    applied = lca.apply_att_gwp(sys, estimates=estimates)
    total = contributions[-1]
    dry = inv._dry_feed_kgph(sys)
    h2 = float(inv._streams(sys)["h2_product"].imass["H2"]) / dry
    cake_landfill = float(inv._streams(sys)["caco3_cake"].F_mass) / dry * float(lca._EF["inert_landfill"]["value"])
    ct = _collection_transport(sys, estimates, total["GWP_kgCO2e_per_kg_dry"])
    consistency = _existing_outputs_check(_consistency(sys, estimates, result, contributions, utilities),
                                              result["msp"], total["GWP_kgCO2e_per_kg_H2"])

    lca_scen = [dict(scenario=r["scenario"], parameter=r["parameter"], value=r["value"],
                     GWP_kgCO2e_per_kg_dry=r["GWP_kgCO2e_per_kg_dry"], GWP_kgCO2e_per_kg_H2=r["GWP_kgCO2e_per_kg_H2"],
                     delta_per_kg_H2=r["delta_per_kg_H2"], note="") for r in sens_lca]
    lca_scen.append(dict(scenario="Case-A-consistent (CaCO3 cake landfilled, WARM inert proxy)", parameter="cake fate",
                         value=float("nan"), GWP_kgCO2e_per_kg_dry=total["GWP_kgCO2e_per_kg_dry"] + cake_landfill,
                         GWP_kgCO2e_per_kg_H2=(total["GWP_kgCO2e_per_kg_dry"] + cake_landfill) / h2,
                         delta_per_kg_H2=cake_landfill / h2, note="consistent with TEA Case A"))
    lca_scen += [dict(scenario=f"Collection/transport: {r['parameter']}", parameter=r["unit"], value=r["value"],
                      GWP_kgCO2e_per_kg_dry=float("nan"), GWP_kgCO2e_per_kg_H2=r["result"], delta_per_kg_H2=float("nan"),
                      note=r["note"]) for r in ct if r["analysis"] == "LCA"]
    lca_scen += [dict(scenario=f"Carbon/biogenic: {r['item']}", parameter=r["unit"], value=r["value"],
                      GWP_kgCO2e_per_kg_dry=float("nan"), GWP_kgCO2e_per_kg_H2=float("nan"), delta_per_kg_H2=float("nan"),
                      note=r["note"]) for r in summary_lca]

    tea_sens = ([dict(group="One-at-a-time", case=r["case"], MSP_USD_per_kg_H2=r["MSP_USD_per_kg_H2"], delta=r["delta"],
                      note="") for r in sens_tea]
                + [dict(group="Lime price", case=f"{r['lime_price']} | {r['case']}", MSP_USD_per_kg_H2=r["MSP_USD_per_kg_H2"],
                        delta=r["delta_vs_0.24"], note=r["basis"]) for r in lime]
                + [dict(group="P1 press", case=r["case"], MSP_USD_per_kg_H2=r["MSP_USD_per_kg_H2"], delta=r["delta_MSP"],
                        note=f"P1 {r['P1_GWh_per_yr']:.1f} GWh/yr; {r['P1_installed_MUSD']:.1f} MUSD; "
                             f"dGWP {r['delta_GWP_kgCO2e_per_kg_H2']:.2f} kg CO2e/kg H2") for r in p1]
                + [dict(group="Collection/transport", case=f"{r['case']} | {r['parameter']} {r['value']} {r['unit']}",
                        MSP_USD_per_kg_H2=r["result"], delta=float("nan"), note=r["note"])
                   for r in ct if r["analysis"] == "TEA"]
                + [dict(group="Off-gas handling", case=r["item"], MSP_USD_per_kg_H2=r["MSP_USD_per_kg_H2"],
                        delta=float("nan"), note=f"{r['value']} {r['unit']}") for r in offgas])

    qc = ([dict(source="inventory", check=k, value=str(v), status="") for k, v in small_checks.items()]
          + [dict(source="TEA", check=r["check"], value=str(r["value"]), status=r["status"]) for r in tea_checks]
          + [dict(source="LCA", check=r["check"], value=str(r["value"]), status=r["status"]) for r in lca_checks]
          + [dict(source="TEA-LCA", check=r["check"], value=str(r["TEA_or_model"]), status=r["status"]) for r in consistency]
          + [dict(source="inventory", check=r["check"], value=str(r["value"]), status=r["status"])
             for r in inv.get_att_utility_consistency_check(sys)])

    register = _register_rows()
    process_sections = ("Feedstock", "Scale", "Preparation", "ATT reaction", "Gas treatment", "Downstream", "Energy")
    process = [dict(Parameter=r["parameter"], Value=r["value"], Unit=r["unit"], Process_unit=r["process_unit"],
                    Description=r["description"], Source_category=r["source_category"],
                    Exact_source_file_key=f"{r['exact_source']} | {r['file_key']}",
                    Assumption_status=r["assumption_status"], Notes=r["notes"])
               for r in register if r["section"] in process_sections]
    master = [dict(Category=r["section"], Parameter=r["parameter"], Value=r["value"], Unit=r["unit"],
                   Model_location=r["process_unit"], Source_category=r["source_category"],
                   Exact_source=r["exact_source"], File_and_key=r["file_key"], Rationale=r["description"],
                   Affects=r["affects"], Baseline_or_sensitivity=r["baseline_or_sensitivity"],
                   Uncertainty=r["uncertainty_or_limitation"],
                   Collaborator_confirmation=r["collaborator_confirmation_needed"]) for r in register]

    tables = {
        "00_Overview": _overview(sys, result, total["GWP_kgCO2e_per_kg_H2"]),
        "01_Process_Assumptions": process,
        "02_Feedstock_Composition": _feedstock(sys),
        "03_Equipment_Operating": _units_table(sys, estimates),
        "04_Connectivity": _connectivity(sys),
        "05_Stream_Inventory_Long": _streams(sys),
        "06_Mass_Element_Balance": _mass_balance(sys),
        "07_NaOH_Carbonate": ([dict(item=r["item"], value=r["value"], unit=r["unit"])
                               for r in inv.get_att_sodium_calcium_ledger(sys)] + [
            dict(item=f"{r['stream']}: NaOH/(NaOH+H2O) | NaOH/total | Na2CO3/total",
                 value=f"{r['NaOH_over_NaOH_plus_H2O']:.4g} | {r['NaOH_over_total_mixture']:.4g} | "
                       f"{r['Na2CO3_over_total_mixture']:.4g}", unit=r["note"]) for r in _naoh_extra(sys)]),
        "07b_Na2CO3_Crystallization": _crystallization_audit(sys),
        "08_Water_Balance": inv.get_att_water_balance(sys),
        "09_Products_Residues": _products(sys),
        "10_Unit_Energy_Balance": inv.get_att_unit_energy_balance(sys),
        "11_Energy_Accounts": _energy_accounts(sys),
        "12_Utilities_Energy_Totals": utilities + _energy_totals(sys, utilities),
        "13_Heat_Exchanger_Network": _heat_integration(sys),
        "14_LCA_EF_Register": lca.get_att_lca_factor_register(),
        "15_LCA_Contributions": _lca_register(contributions, applied),
        "16_LCA_by_Unit_and_Stage": ([dict(view="unit", item=r["unit"], GWP_kgCO2e_per_kg_dry=r["GWP_kgCO2e_per_kg_dry"],
                                           GWP_kgCO2e_per_kg_H2=r["GWP_kgCO2e_per_kg_H2"], share=r["share"]) for r in by_unit]
                                     + [dict(view="stage", item=r["stage"], GWP_kgCO2e_per_kg_dry=r["GWP_kgCO2e_per_kg_dry"],
                                             GWP_kgCO2e_per_kg_H2=r["GWP_kgCO2e_per_kg_H2"], share=r["share"]) for r in stage]),
        "17_LCA_Scenarios": lca_scen,
        "18_TEA_CAPEX": capex,
        "19_TEA_OPEX_Reference": opex,
        "19b_TEA_OPEX_Case_A": opex_a,
        "20_Financial_Assumptions": _financial(result),
        "21_MSP_and_CaCO3_Cases": ([dict(case="Reference (commit 1473af06)", MSP_USD_per_kg_H2=result["msp"]),
                                    dict(case="Case A (no CaCO3 sales; cake disposed)", MSP_USD_per_kg_H2=case_a["msp"])]),
        "21b_CaCO3_Case_Detail": _caco3_detail(sys, caco3),
        "21c_MSP_Breakdown": tea_mod._opex_table(sys, result),
        "22_TEA_Sensitivities": tea_sens,
        "23_Master_Assumptions": master,
        "24_Limitations_Gaps": _gaps_and_inconsistencies(gaps),
        "25_YAML_Config_Register": _yaml_register(),
        "26_QC_Checks": qc,
    }
    tables["05b_Stream_Matrix_kg_per_kg_dry"] = _streams_wide(tables["05_Stream_Inventory_Long"])
    # Cost-year comparison re-simulates (flows reconverge); run last.
    tables["22b_Cost_Year"] = tea_mod.get_att_cost_year_comparison(sys)
    tables["26_QC_Checks"].append(dict(source="documentation", check="Frozen flows unchanged (rel. 1e-8)",
                                       value=str(tea_mod._same_flows(sys, fingerprint)),
                                       status="PASS" if tea_mod._same_flows(sys, fingerprint) else "FAIL"))
    tables["26_QC_Checks"] += [dict(source="process", check=r["check"], value=str(r["value"]), status=r["status"])
                               for r in inv.get_att_process_checks(sys)]
    r = inv.get_att_recycle_convergence(sys)   # re-simulates: keep last
    tables["26_QC_Checks"].append(dict(source="process", check=r["check"], value=str(r["value"]), status=r["status"]))
    order = ["00_Overview", "01_Process_Assumptions", "02_Feedstock_Composition", "03_Equipment_Operating",
             "04_Connectivity", "05_Stream_Inventory_Long", "05b_Stream_Matrix_kg_per_kg_dry",
             "06_Mass_Element_Balance", "07_NaOH_Carbonate", "07b_Na2CO3_Crystallization",
             "08_Water_Balance", "09_Products_Residues",
             "10_Unit_Energy_Balance", "11_Energy_Accounts", "12_Utilities_Energy_Totals",
             "13_Heat_Exchanger_Network", "14_LCA_EF_Register", "15_LCA_Contributions", "16_LCA_by_Unit_and_Stage",
             "17_LCA_Scenarios", "18_TEA_CAPEX", "19_TEA_OPEX_Reference", "19b_TEA_OPEX_Case_A",
             "20_Financial_Assumptions", "21_MSP_and_CaCO3_Cases", "21b_CaCO3_Case_Detail", "21c_MSP_Breakdown",
             "22_TEA_Sensitivities", "22b_Cost_Year", "23_Master_Assumptions", "24_Limitations_Gaps",
             "25_YAML_Config_Register", "26_QC_Checks"]
    return {k: tables[k] for k in order}


def _feedstock(sys):
    U2 = inv._units(sys)["U2"]
    feed = U2.ins[0]
    daf = float(U2._daf_sargassum_kgph)
    dry = float(U2._dry_sargassum_kgph)
    AW = {"C": 12.011, "H": 1.008, "O": 15.999, "N": 14.007, "S": 32.06}
    rows, tot = [], {e: 0.0 for e in AW}
    for c in feed.chemicals:
        m = float(feed.imass[c.ID])
        if m <= 0 or c.ID in ("Water", "NaOH", "Na2CO3"):
            continue
        n = float(feed.imol[c.ID])
        if c.ID != "Ash":
            for e in AW:
                tot[e] += n * c.atoms.get(e, 0) * AW[e]
        rows.append(dict(item=f"Pseudo-component {c.ID}", wt_frac_dry=m / dry,
                         wt_frac_daf=m / daf if c.ID != "Ash" else float("nan"),
                         formula=str(dict(c.atoms)) if c.atoms else "inert", MW=c.MW,
                         source="feedstock.yaml:dry_composition (" + NV + "); formula: biorefineries/sabre/_chemicals.py"))
    for e, v in tot.items():
        rows.append(dict(item=f"Ultimate analysis {e} (calculated)", wt_frac_dry=v / dry, wt_frac_daf=v / daf,
                         formula="", MW=float("nan"), source=CALC + " from pseudo-component formulas"))
    rows += [
        dict(item="daf / dry", wt_frac_dry=daf / dry, wt_frac_daf=float("nan"), formula="", MW=float("nan"),
             source=CALC + " (1 - ash)"),
        dict(item="Moisture as harvested (wet basis)", wt_frac_dry=Y("feedstock.yaml", "feedstock_type.pelagic.moisture_frac"),
             wt_frac_daf=float("nan"), formula="", MW=float("nan"), source="feedstock.yaml (milledge2020)"),
        dict(item="Wet feed per kg dry", wt_frac_dry=1 / (1 - Y("feedstock.yaml", "feedstock_type.pelagic.moisture_frac")),
             wt_frac_daf=float("nan"), formula="", MW=float("nan"), source=CALC),
        dict(item="Available electrons (mmol e-/g daf)", wt_frac_dry=float("nan"),
             wt_frac_daf=U2._redox_balance_kmol_e_per_h["feed_organics"] / daf * 1e3, formula="4C+H-2O-3N",
             MW=float("nan"), source=CALC + " (ATTReactor redox bookkeeping)"),
        dict(item="Proximate: volatile solids / total solids", wt_frac_dry=Y("feedstock.yaml", "feedstock_type.pelagic.vs_ts"),
             wt_frac_daf=float("nan"), formula="", MW=float("nan"), source="feedstock.yaml (milledge2020); not used"),
        dict(item="Proximate: fixed carbon", wt_frac_dry=float("nan"), wt_frac_daf=float("nan"), formula="", MW=float("nan"),
             source="Not available in the repository"),
    ]
    return rows


def _mass_balance(sys):
    rows = []
    flows = inv.get_att_external_flows(sys)
    for r in flows:
        if r["component"] == "TOTAL":
            rows.append(dict(table="external flow", item=r["stream"], direction=r["direction"], value=r["kg_per_kg_dry"],
                             unit="kg/kg dry", note=r["category"]))
    check = inv.check_att_inventory(sys, flows)
    rows.append(dict(table="overall", item="mass residual (out-in)/in", direction="", value=check["mass_relative_error"],
                     unit="-", note=""))
    for e, v in check["element_relative_error"].items():
        rows.append(dict(table="overall element", item=e, direction="", value=v, unit="relative error", note=""))
    for r in inv.get_att_unit_balances(sys):
        rows.append(dict(table="unit balance", item=r["unit"], direction=r["type"], value=r["mass_relative_error"],
                         unit="relative mass error",
                         note=", ".join(f"{e} {r[f'{e}_relative_error']:.1e}" for e in ("C", "H", "O", "N", "Na", "Ca"))))
    for r in inv.get_att_carbon_fate(sys):
        rows.append(dict(table="carbon fate", item=r["stream"], direction=r["direction"], value=r["kg_C_per_kg_dry"],
                         unit="kg C/kg dry", note=r["category"]))
    return rows


_README = """# ATT model documentation package

Generated by `python -m biorefineries.sabre.test.run_att_documentation`
(`biorefineries/sabre/analyses/att/reporting.py`). Data extraction and
traceability only: no model, LCA or TEA parameter is changed.

## Modeling framework

- **Process model (frozen):** `biorefineries/sabre/systems/_att_system.py` builds the
  BioSTEAM flowsheet P1-D0-M1-U2-U3HX-U3C-U3D-U3K (no PSA in the baseline; att.yaml gas_treatment.psa_enabled) / RC1-W3-SW-D1-F1-C1-F2-SP1-EC1
  with custom units in `biorefineries/sabre/units/_att.py`. U2 takes the specified gas yields of the experimental team (H2, CH4, CO, CO2), forms Na2CO3 from NaOH and
  closes oxygen with water; balance checks cover NaOH capacity for CO2, electrons, mass and energy. Sources of the data: `data_sources` in `biorefineries/sabre/data/att.yaml`.
- **Configuration:** `biorefineries/sabre/data/att.yaml` (process),
  `feedstock.yaml`, `tea.yaml` (SaBRe common), `att_lca.yaml` (GWP100 factors),
  `att_tea.yaml` (ATT prices and capital items).
- **Inventory:** `analyses/att/inventory.py` (mass, element, water, Na/Ca,
  energy, utilities, equipment estimates) -> `att_outputs/full_scale/mass_energy/`.
- **LCA:** `analyses/att/lca.py` (BioSTEAM characterization factors and
  process impacts, `System.get_net_impact`) -> `att_outputs/full_scale/lca/`.
- **TEA:** `analyses/att/tea.py` (`ATTTEA` = SaBReTEA + extra capital/VOC,
  `solve_price`) -> `att_outputs/full_scale/tea/`.
- **Consolidation:** `analyses/att/reporting.py` -> `att_outputs/full_scale/summary/`.
- **This package:** `analyses/att/reporting.py` -> `att_outputs/documentation/`.

All analyses run on the frozen system at the NLR preprint scale (3 million wet
t/yr; about 1,300 dry t/d; 7,920 h/yr). Electricity and equipment costs are taken
at this scale; per-kg-dry material and heat flows are scale-invariant.

## Authoritative sources

1. Code and configuration files above (git-tracked).
2. The exported workbooks are generated outputs; regenerate rather than edit.
3. Within this workbook, each table states its origin: frozen BioSTEAM system,
   an existing analysis function, or a configuration key (`file:key`).

## Reproduce

```
python -m biorefineries.sabre.test.run_att_all          # every ATT result, in dependency order
python -m biorefineries.sabre.test.run_att_documentation  # this package only
python -m unittest discover -s biorefineries/sabre/test -t . -p "test_att*.py"
```

## Main uncertainties

See sheet `24_Limitations_Gaps` and `23_Master_Assumptions` (column
`Collaborator_confirmation`): NaOH capacity for CO2 (36 % captured), Sargassum collection/transport data, CaCO3 cake purity and outlet,
delivered Ca(OH)2 price and source, P1 press basis, PSA
capital (preliminary), plant-location electricity factor, indirect capital,
feedstock composition (no CHNS-O of the UCLA sample).

## Sheets

{sheets}
"""


def export_att_documentation(out_dir=None):
    import pandas as pd
    from biorefineries.sabre.analyses.att.paths import output_dir

    out_dir = os.fspath(out_dir or output_dir("documentation"))
    tables = build_att_documentation()
    os.makedirs(out_dir, exist_ok=True)
    with pd.ExcelWriter(os.path.join(out_dir, WORKBOOK), engine="openpyxl") as writer:
        for name, rows in tables.items():
            df = pd.DataFrame(rows)
            df.to_csv(os.path.join(out_dir, f"{name}.csv"), index=False)
            df.to_excel(writer, sheet_name=name[:31], index=False)
    sheets = "\n".join(f"- `{name}` ({len(rows)} rows)" for name, rows in tables.items())
    with open(os.path.join(out_dir, "README.md"), "w", encoding="utf-8") as f:
        f.write(_README.replace("{sheets}", sheets))
    return tables


# ==========================================================================
# Consolidated research-stage results (process, TEA, GWP100)
# ==========================================================================

_TEA_PRICE = load_assumptions("tea.yaml")["price"]
COLLECTION_COST_USD_PER_WET_T = (0.0, 5.0, 10.0, 20.0, 50.0)
ILLUSTRATIVE_FUEL_KG_PER_WET_T = (1.0, 5.0, 10.0)   # parametric only; no data


def _row(table, section, item, value, unit, basis=""):
    table.append(dict(section=section, item=item, value=value, unit=unit, basis=basis))


def _process_and_materials(sys, utilities):
    s = inv._streams(sys)
    dry = inv._dry_feed_kgph(sys)
    hours = sys.operating_hours
    U2 = inv._units(sys)["U2"]
    u = {r["item"]: r["per_kg_dry"] for r in utilities}
    h2 = float(s["h2_product"].imass["H2"]) / dry
    rows = []
    P, M = "Process and energy", "Materials and products"
    _row(rows, P, "Wet Sargassum feed", float(s["att_sargassum_feed"].F_mass) * 24 / 1e3, "t/d", "SaBRe scale")
    _row(rows, P, "Dry Sargassum feed", dry * 24 / 1e3, "t/d", "NLR preprint composition")
    _row(rows, P, "Operating time", hours, "h/yr", "tea.yaml 330 d/yr")
    specified = U2.reported_gas_yield_mmol_per_g_daf
    for gas in ("H2", "CH4", "CO", "CO2"):
        _row(rows, P, f"{gas} yield, specified", float(specified.get(gas, 0.0)), "mmol/g daf",
             "Experimental team Excel (CO2 topped up by the carbon balance)")
        _row(rows, P, f"{gas} yield, model", U2._model_gas_yield_mmol_per_g_daf[gas], "mmol/g daf",
             "specified yields")
    _row(rows, P, "H2 at U2 outlet", float(U2.outs[0].imass["H2"]) / dry, "kg/kg dry", "model yield x daf")
    _row(rows, P, "H2 product (PSA 90 %)", h2, "kg/kg dry", "PSA recovery: engineering assumption")
    _row(rows, P, "H2 product", h2 * dry * hours / 1e3, "t/yr", "")
    for item, unit in (("U2 natural gas: fuel input (LHV)", "MJ/kg dry"),
                       ("LP steam: utility heat incl. 5 % loss", "MJ/kg dry"),
                       ("LP steam: boiler natural gas (LHV)", "MJ/kg dry"),
                       ("Cooling water: heat removed", "MJ/kg dry"),
                       ("Electricity: total", "kWh/kg dry")):
        _row(rows, P, item, u[item], unit, "frozen model, reference scale")
    _row(rows, P, "Total natural gas (U2 + steam boiler)", u["U2 natural gas: fuel input (LHV)"]
         + u["LP steam: boiler natural gas (LHV)"], "MJ/kg dry", "")
    _row(rows, P, "Total natural gas per kg H2", (u["U2 natural gas: fuel input (LHV)"]
                                                 + u["LP steam: boiler natural gas (LHV)"]) / h2, "MJ/kg H2", "")
    ledger = {r["item"]: r["value"] for r in inv.get_att_sodium_calcium_ledger(sys)}
    _row(rows, P, "Effective NaOH recovery", ledger["Effective NaOH recovery = 1 - makeup / gross"], "-",
         "95 % whole-liquor recycle")
    for label, ID, comp in (("NaOH makeup", "fresh_naoh_solid", "NaOH"), ("Ca(OH)2", "lime", "CaOH2"),
                            ("Process water (D1)", "dissolution_water", "Water")):
        v = float(s[ID].imass[comp]) / dry
        _row(rows, M, label, v, "kg/kg dry", "")
        _row(rows, M, f"{label} per kg H2", v / h2, "kg/kg H2", "")
    cake = s["caco3_cake"]
    _row(rows, M, "CaCO3 equivalent in cake", float(cake.imass["CaCO3"]) / dry, "kg/kg dry", "model (C1 85 %)")
    _row(rows, M, "CaCO3 wet filter cake (impure)", float(cake.F_mass) / dry, "kg/kg dry",
         "incl. Ca(OH)2, NaOH, Na2CO3, 25 % water")
    _row(rows, M, "Ash/char cake to disposal", float(s["ash_residue_cake"].F_mass) / dry, "kg/kg dry", "")
    ww = sum(float(s[ID].F_mass) for ID in lca._LCA["waste_management"]["wastewater_streams"]) / dry
    _row(rows, M, "Wastewater incl. alkaline purge", ww, "kg/kg dry", "")
    tail = inv._tail_gas(sys)
    _row(rows, M, "PSA off-gas (total)", float(tail.F_mass) / dry, "kg/kg dry",
         "explicit collected stream; final fate unresolved; direct CH4 emission not in baseline GWP; "
         "treatment equipment and cost not in baseline TEA")
    for gas in ("CH4", "H2", "CO", "CO2"):
        _row(rows, M, f"  {gas} in PSA off-gas", float(tail.imass[gas]) / dry, "kg/kg dry", "model")
    return rows


def _collection_transport(sys, estimates, gwp_per_kg_dry):
    s = inv._streams(sys)
    dry = inv._dry_feed_kgph(sys)
    h2 = float(s["h2_product"].imass["H2"]) / dry
    wet_t_per_kg_dry = float(s["att_sargassum_feed"].F_mass) / 1e3 / dry
    rows = []
    for case, kw in (("Reference", {}), ("Case A", dict(caco3=dict(fraction=0.0)))):
        for cost in COLLECTION_COST_USD_PER_WET_T:
            msp = tea_mod.evaluate_att_tea(sys, estimates, feedstock_usd_per_wet_t=cost, **kw)["msp"]
            rows.append(dict(analysis="TEA", case=case, parameter="collection + transport cost",
                             value=cost, unit="USD/wet t", result=msp, result_unit="MSP USD/kg H2",
                             note="sensitivity; no SaBRe/ATT location-specific data"))
    sc = _TEA_PRICE["sargassum"]
    for name, v in sc["scenario"].items():
        msp = tea_mod.evaluate_att_tea(sys, estimates, feedstock_usd_per_wet_t=v * 1e3,
                                       caco3=dict(fraction=0.0))["msp"]
        rows.append(dict(analysis="TEA", case="Case A", parameter=f"tea.yaml sargassum.{name}", value=v * 1e3,
                         unit="USD/wet t", result=msp, result_unit="MSP USD/kg H2", note=sc["source"]))
    tea_mod.evaluate_att_tea(sys, estimates)
    ef = float(lca._EF["marine_fuel"]["value"])
    coeff = wet_t_per_kg_dry * ef
    rows.append(dict(analysis="LCA", case="Baseline", parameter="GWP coefficient per kg fuel per wet t",
                     value=1.0, unit="kg fuel/wet t", result=coeff / h2, result_unit="kg CO2e/kg H2",
                     note=f"marine fuel combustion {ef} kg CO2/kg (collaborators); fuel upstream not included; "
                          f"{coeff:.4f} kg CO2e/kg dry"))
    for fuel in ILLUSTRATIVE_FUEL_KG_PER_WET_T:
        rows.append(dict(analysis="LCA", case="Baseline", parameter="illustrative fuel intensity (NOT data)",
                         value=fuel, unit="kg fuel/wet t", result=(gwp_per_kg_dry + fuel * coeff) / h2,
                         result_unit="kg CO2e/kg H2", note="parametric; no collection fuel-use data available"))
    return rows


def _consistency(sys, estimates, tea_result, contributions, utilities):
    """TEA and LCA use the same activity data (same system, same streams)."""
    s = inv._streams(sys)
    hours = sys.operating_hours
    dry = inv._dry_feed_kgph(sys)
    c = {r["item"]: r for r in contributions}
    u = {r["item"]: r["per_kg_dry"] for r in utilities}
    tea = tea_result["tea"]
    gas = [hu for hu in sys.heat_utilities if hu.agent.ID == "natural_gas"]
    ng_tea_MJ = (sum(hu.cost for hu in gas) * hours
                 + next(v for n, v in tea_result["voc_items"] if n.startswith("Natural"))) / tea_mod._ng_usd_per_MJ()
    aux = next(v for n, v in tea_result["voc_items"] if n.startswith("Electricity: agitators"))
    elec_tea_kWh = (sys.power_utility.rate * hours + aux / tea_mod.bst.PowerUtility.price)
    checks = [
        ("Operating hours (TEA = LCA)", tea.operating_days * 24, sys.operating_hours),
        ("H2 product for MSP = LCA functional-unit basis [kg/yr]", float(s["h2_product"].imass["H2"]) * hours,
         c["TOTAL (System.get_net_impact)"]["GWP_kgCO2e_per_kg_dry"] / c["TOTAL (System.get_net_impact)"][
             "GWP_kgCO2e_per_kg_H2"] * dry * hours),
        ("NaOH: TEA purchase = LCA activity [kg/kg dry]", float(s["fresh_naoh_solid"].F_mass) / dry,
         c["NaOH makeup"]["activity_per_kg_dry"]),
        ("Ca(OH)2: TEA purchase = LCA activity [kg/kg dry]", float(s["lime"].F_mass) / dry,
         c["Ca(OH)2"]["activity_per_kg_dry"]),
        ("U2 natural gas: TEA priced fuel = LCA fuel [MJ/kg dry]", ng_tea_MJ / hours / dry,
         c["Natural gas U2: combustion"]["activity_per_kg_dry"]),
        ("U2 natural gas = inventory fuel [MJ/kg dry]", ng_tea_MJ / hours / dry, u["U2 natural gas: fuel input (LHV)"]),
        ("Electricity priced in TEA = LCA unit + auxiliary [kWh/kg dry]", elec_tea_kWh / hours / dry,
         c["Electricity: process units"]["activity_per_kg_dry"]
         + c["Electricity: outside unit models (agitators, EC1 vacuum)"]["activity_per_kg_dry"]),
        ("Wastewater: TEA disposal volume = LCA treatment volume [m3/kg dry]",
         sum(float(s[ID].F_mass) for ID in tea_mod._T["prices"]["wastewater_streams"]) / 1e3 / dry,
         c["Wastewater treatment"]["activity_per_kg_dry"]),
        ("Ash/char cake: TEA disposal = LCA landfill [kg/kg dry]",
         sum(float(s[ID].F_mass) for ID in (*tea_mod._T["prices"]["solid_waste_streams"], "caco3_cake")
             if ID in s and s[ID] in sys.products) / dry,      # the CaCO3 cake leaves only without the lime recycle
         c["Landfill: solid residues"]["activity_per_kg_dry"]),
    ]
    rows = [dict(check=a, TEA_or_model=b, LCA_or_reference=d,
                 status="PASS" if abs(b - d) <= 1e-6 * max(1.0, abs(d)) else "FAIL") for a, b, d in checks]
    rows += [
        dict(check="Steam: TEA prices steam (agent price covers generation); LCA counts boiler natural gas",
             TEA_or_model=float("nan"), LCA_or_reference=float("nan"), status="BY DESIGN (no double count)"),
        dict(check="Cooling: TEA cooling-water price; LCA cooling-tower electricity",
             TEA_or_model=float("nan"), LCA_or_reference=float("nan"), status="BY DESIGN (no double count)"),
        dict(check="CaCO3: TEA Case B revenue does not imply an LCA credit; LCA baseline has no CaCO3 credit",
             TEA_or_model=float("nan"), LCA_or_reference=float("nan"), status="BY DESIGN"),
        dict(check="CaCO3 cake: TEA Case A disposes the cake; LCA baseline treats it as a coproduct without "
                   "burden. Case-A-consistent LCA adds cake landfill (see GWP sheet)",
             TEA_or_model=float("nan"), LCA_or_reference=float("nan"), status="FLAGGED, quantified"),
        dict(check="tea.yaml sargassum scenarios mid_cost_collect = high_cost_collect = 0.05 USD/kg while the "
                   "range reaches 0.10 (existing SaBRe data; not changed)",
             TEA_or_model=float("nan"), LCA_or_reference=float("nan"), status="FLAGGED"),
    ]
    return rows


def _process_check_rows(sys):
    """Process-level checks (U2 balances, HXN, dryer humidity, D1 solubility, UCLA reference values)."""
    return [dict(check=r["check"], TEA_or_model=r["value"], LCA_or_reference=r["expected"], status=r["status"])
            for r in inv.get_att_process_checks(sys)]


def _existing_outputs_check(rows, msp_reference, gwp_per_kg_H2):
    """Compare with the exported TEA and LCA results; a missing file is reported as NOT CHECKED."""
    import pandas as pd
    from biorefineries.sabre.analyses.att.paths import SUBDIRS, output_dir

    for key, name, item, value in (("tea", "00_summary.csv", "H2 MSP", msp_reference),
                                   ("lca", "01_summary.csv", "GWP100 per kg H2", gwp_per_kg_H2)):
        path = output_dir(key) / name
        label = f"Matches existing {SUBDIRS[key]}/{name}: {item}"
        if path.exists():
            df = pd.read_csv(path)
            ref = float(df.loc[df["item"] == item, "value"].iloc[0])
            rows.append(dict(check=label, TEA_or_model=value, LCA_or_reference=ref,
                             status="PASS" if abs(value - ref) <= 1e-6 * max(1.0, abs(ref)) else "FAIL"))
        else:
            rows.append(dict(check=label, TEA_or_model=value, LCA_or_reference=float("nan"),
                             status="NOT CHECKED (reference output missing; run run_att_tea/run_att_lca first)"))
    return rows


def _findings(msp, caco3, gwp, stage, slag, sens_tea, sens_lca, ct, case_a_lca, h2, lime_share=float("nan"),
              s_factor=float("nan"), cap_share=float("nan")):
    """Preliminary conclusions with a robustness label for presentation."""
    def m(case, price=250.0, handling=0.0, f=None, lime="0.24 (original)"):
        for r in caco3:
            if (r["lime_price"] == lime and r["case"].startswith(case)
                    and (f is None or (r["marketable_fraction"] == f and r["CaCO3_price_usd_per_t"] == price
                                       and r["handling_usd_per_t"] == handling))):
                return r["MSP_USD_per_kg_H2"]
    st = {r["stage"]: r for r in stage}
    ng = (st["Onsite fuel combustion"]["share"] + st["Natural gas supply chain"]["share"]
          + st.get("Natural gas displaced by tail gas", {"share": 0.0})["share"])  # net of the tail-gas offset
    ct10 = [r["result"] for r in ct if r["analysis"] == "TEA" and r["case"] == "Case A"
            and r["parameter"] == "collection + transport cost"]
    rows = [
        ("Cost drivers", f"Ca(OH)2 is the largest cost ({lime_share:.0%} of the reference MSP {msp:.2f} USD/kg); steam, NaOH "
         f"and filter-cake disposal follow; capital recovery is {cap_share:.0%}. The process is operating-cost dominated.",
         "ROBUST (ranking); main text"),
        ("Conservative MSP", f"Case A (no CaCO3 sales, cake disposed at an assumed 0.04 USD/kg) "
         f"{m('Case A'):.2f} USD/kg H2; reference without cake cost {msp:.2f}.", "ROBUST as a bound; main text"),
        ("Lime price", f"0.28 instead of 0.24 USD/kg (USGS 2025e, f.o.b.) raises MSP by "
         f"{m('Case A', lime='0.28 (USGS MCS 2026, 2025e)') - m('Case A'):.2f} USD/kg; delivery not included.",
         "SENSITIVITY; main text"),
        ("CaCO3 marketability", f"At 250 USD/t (optimistic commodity reference) Case A falls to "
         f"{m('Case B', f=0.5):.2f} (50 % marketable) and {m('Case B', f=1.0):.2f} USD/kg (100 %); at 50 USD/t "
         f"and 100 % only to {m('Case B', price=50.0, f=1.0):.2f}. Feasibility hinges on cake quality and market.",
         "SENSITIVITY; main text figure, not a result"),
        ("Collection/transport cost", f"Each 10 USD/wet t adds ~{(ct10[2] - ct10[0]):.2f} USD/kg H2 "
         f"(~{1 / h2 * 7.536 / 1e3 * 1e3:.0f} t wet Sargassum per t H2); 50 USD/t -> "
         f"{ct10[4]:.2f}.", "SENSITIVITY; main text (data pending)"),
        ("GWP100", f"{gwp:.1f} kg CO2e/kg H2 (partial boundary, no collection/transport); natural gas "
         f"(combustion + upstream) {ng:.0%}, chemical supply {st['Chemical supply']['share']:.0%}.",
         "ROBUST (ranking); value partial-boundary"),
        ("Lime sourcing (LCA)", f"Steel-slag Ca(OH)2 lowers GWP to {slag:.1f} kg CO2e/kg H2 "
         f"({slag / gwp - 1:.0%}); limestone range 0.59-1.00 gives "
         f"{min(r['GWP_kgCO2e_per_kg_H2'] for r in sens_lca if 'CaOH2_limestone' in r['scenario']):.1f}-"
         f"{max(r['GWP_kgCO2e_per_kg_H2'] for r in sens_lca if 'CaOH2_limestone' in r['scenario']):.1f}.",
         "SENSITIVITY; main text"),
        ("Case-A-consistent GWP", f"Landfilling the CaCO3 cake (WARM proxy) adds {case_a_lca:.2f} kg CO2e/kg H2.",
         "SENSITIVITY; SI"),
        ("Gas-yield basis", "Specified yields of the experimental team (H2 70.52, CH4 0.70, CO 0.31, CO2 22.68 mmol/g daf; "
         "NaOH 1 g/g daf); they close the electron balance (identified products hold less reducing power than the feed).",
         "ROBUST as method; value depends on feed composition"),
        ("Open items before submission", "Collection/transport activity data; CaCO3 purity and outlet; delivered "
         "lime price and source; P1 press basis; PSA capital; plant-location grid factor; "
         "indirect capital; collaborator confirmation of gas analysis.", "TO RESOLVE"),
    ]
    return [dict(topic=a, finding=b, robustness_and_placement=c) for a, b, c in rows]


def build_att_consolidated_results():
    sys = tea_mod.create_att_tea_system()
    estimates = inv.get_att_cost_estimates(sys)
    # TEA (reference case leaves the reference prices applied).
    caco3 = tea_mod.get_att_caco3_cases(sys, estimates)
    lime = tea_mod.get_att_lime_price_cases(sys, estimates)
    sens_tea = tea_mod.get_att_tea_sensitivity(sys, estimates)
    p1 = tea_mod.get_att_p1_power_cases(sys, estimates)
    result = tea_mod.evaluate_att_tea(sys, estimates)
    capex = tea_mod._capex_table(sys, result)
    opex = tea_mod._opex_table(sys, result)
    case_a = tea_mod.evaluate_att_tea(sys, estimates, caco3=dict(fraction=0.0))
    opex_a = tea_mod._opex_table(sys, case_a)
    result = tea_mod.evaluate_att_tea(sys, estimates)
    # LCA on the same system.
    applied = lca.apply_att_gwp(sys, estimates=estimates)
    contributions = lca.get_att_gwp_contributions(sys, applied)
    stage = lca.get_att_gwp_by_stage(contributions)
    sens_lca = lca.get_att_gwp_sensitivity(sys, estimates)
    total = contributions[-1]
    gwp_dry, gwp_h2 = total["GWP_kgCO2e_per_kg_dry"], total["GWP_kgCO2e_per_kg_H2"]
    slag = next(r["GWP_kgCO2e_per_kg_H2"] for r in sens_lca if r["scenario"].startswith("S1"))
    s = inv._streams(sys)
    dry = inv._dry_feed_kgph(sys)
    h2 = float(s["h2_product"].imass["H2"]) / dry
    cake_landfill = float(s["caco3_cake"].F_mass) / dry * float(lca._EF["inert_landfill"]["value"])
    utilities = inv.get_att_purchased_utilities(sys, estimates)
    ct = _collection_transport(sys, estimates, gwp_dry)
    gwp_rows = [dict(view="by stage", item=r["stage"], GWP_kgCO2e_per_kg_dry=r["GWP_kgCO2e_per_kg_dry"],
                     GWP_kgCO2e_per_kg_H2=r["GWP_kgCO2e_per_kg_H2"], share=r["share"]) for r in stage]
    gwp_rows += [dict(view="by input", item=r["item"], GWP_kgCO2e_per_kg_dry=r["GWP_kgCO2e_per_kg_dry"],
                      GWP_kgCO2e_per_kg_H2=r["GWP_kgCO2e_per_kg_H2"], share=r["share"]) for r in contributions]
    gwp_rows += [
        dict(view="lime sourcing", item="Limestone Ca(OH)2 (baseline)", GWP_kgCO2e_per_kg_dry=gwp_dry,
             GWP_kgCO2e_per_kg_H2=gwp_h2, share=float("nan")),
        dict(view="lime sourcing", item="Steel-slag Ca(OH)2 (S1)", GWP_kgCO2e_per_kg_dry=slag * h2,
             GWP_kgCO2e_per_kg_H2=slag, share=float("nan")),
        dict(view="Case-A-consistent", item="Baseline + CaCO3 cake landfill (WARM inert proxy)",
             GWP_kgCO2e_per_kg_dry=gwp_dry + cake_landfill, GWP_kgCO2e_per_kg_H2=(gwp_dry + cake_landfill) / h2,
             share=float("nan")),
    ]
    msp_rows = [dict(case="Reference (no CaCO3 revenue, cake not costed)", lime_USD_per_kg=0.24,
                     MSP_USD_per_kg_H2=result["msp"])]
    msp_rows += [dict(case=r["case"] if r["case"].startswith("Case A") else
                      f"{r['case']} | {r['CaCO3_price_usd_per_t']} USD/t, handling "
                      f"{r['handling_usd_per_t']} USD/t, marketable {r['marketable_fraction']}",
                      lime_USD_per_kg=r["lime_price"], MSP_USD_per_kg_H2=r["MSP_USD_per_kg_H2"])
                 for r in caco3 if not r["case"].startswith("Reference")]
    consistency = _consistency(sys, estimates, result, contributions, utilities)
    consistency = _existing_outputs_check(consistency, result["msp"], gwp_h2) + _process_check_rows(sys)
    sens = ([dict(analysis="TEA (MSP USD/kg H2)", case=r["case"], value=r["MSP_USD_per_kg_H2"], delta=r["delta"])
             for r in sens_tea]
            + [dict(analysis="TEA lime price (Case A)", case=r["lime_price"], value=r["MSP_USD_per_kg_H2"],
                    delta=r["delta_vs_0.24"]) for r in lime if r["case"].startswith("Case A")]
            + [dict(analysis="TEA/LCA P1 power (pending decision)", case=r["case"], value=r["MSP_USD_per_kg_H2"],
                    delta=r["delta_GWP_kgCO2e_per_kg_H2"]) for r in p1]
            + [dict(analysis="LCA (kg CO2e/kg H2)", case=r["scenario"], value=r["GWP_kgCO2e_per_kg_H2"],
                    delta=r["delta_per_kg_H2"]) for r in sens_lca])
    assumptions = _assumptions_table()
    lime_share = next(r["USD_per_kg_H2"] for r in opex if r["item"] == "Ca(OH)2") / result["msp"]
    findings = _findings(result["msp"], caco3, gwp_h2, stage, slag, sens_tea, sens_lca, ct, cake_landfill / h2, h2,
                         lime_share, 1.0,
                         next(r["USD_per_kg_H2"] for r in opex if r["category"] == "capital") / result["msp"])
    return {
        "00_key_findings": findings,
        "01_process_materials": _process_and_materials(sys, utilities),
        "02_tea_capex": capex,
        "03_tea_opex_reference": opex,
        "03b_tea_opex_case_A": opex_a,
        "04_msp_cases": msp_rows,
        "05_gwp100": gwp_rows,
        "06_sensitivities": sens,
        "07_collection_transport": ct,
        "08_consistency_checks": consistency,
        "09_assumptions_sources": assumptions,
    }


def _assumptions_table():
    rows = [
        ("EXPERIMENTAL", "Gas yields", "H2 70.52, CH4 0.70, CO 0.31, CO2 22.68 mmol/g daf",
         "Experimental team Excel (energy and exergy calculation)"),
        ("EXPERIMENTAL", "NaOH : daf", "1 : 1", "Experimental team Excel"),
        ("LITERATURE", "Feedstock", "NLR preprint fresh (14.3 % solids) and pressed Sargassum", "feedstock.yaml (Wiatrowski et al.)"),
        ("LITERATURE", "Ca(OH)2 price", "0.24 (ref.) / 0.28 USD/kg, f.o.b.", "USGS MCS 2025 / 2026"),
        ("LITERATURE", "Emission factors", "NaOH 1.12, Ca(OH)2 0.91/0, NG 0.056 + 0.0199, grid 0.449",
         "collaborators; NETL 2019; GREET 2022 (att_lca.yaml)"),
        ("LITERATURE", "Collection cost scenarios", "-20 to 100 USD/wet t", "tea.yaml, Rodriguez-Martinez 2023"),
        ("ENGINEERING", "PSA recovery / capital", "90 % / 38.6 MUSD (+/-50 %)", "assumption / review anchor"),
        ("ENGINEERING", "Filter cakes, recycle, C1", "F1 30 %, F2 25 % moisture; 95 % recycle; C1 85 %, lime 1.1x",
         "att.yaml"),
        ("ENGINEERING", "Heat supply", "U2 burner 0.90; steam boiler 0.80; 5 % heat loss", "workbook / BioSTEAM"),
        ("ENGINEERING", "Cake disposal (Case A)", "0.04 USD/kg wet", "tea.yaml disposal_solid (assumed)"),
        ("ILLUSTRATIVE", "CaCO3 price", "250 USD/t (optimistic) / 50 USD/t (low)", "not a demonstrated price"),
        ("FINANCIAL", "SaBReTEA", "IRR 10 %, 20 yr, MACRS7, 21 % tax, FOC 4 % FCI, FCI = installed cost",
         "tea.yaml"),
        ("COST YEAR", "Equipment / prices", "CEPCI 567.5 (2017) / 2024-2025 prices", "see att_tea 10_cost_year"),
        ("BOUNDARY", "LCA", "cradle-to-gate, collection/transport EXCLUDED, no allocation or CaCO3 credit",
         "att_lca.yaml"),
    ]
    rows = [dict(type=a, item=b, value=c, source=d) for a, b, c, d in rows]
    rows += [dict(type="LIMITATION", item="TEA", value=x, source="att_tea.yaml") for x in
             load_assumptions("att_tea.yaml")["tea"]["limitations"]]
    return rows


def export_att_consolidated_results(out_dir=None):
    import pandas as pd
    from biorefineries.sabre.analyses.att.paths import output_dir

    out_dir = os.fspath(out_dir or output_dir("summary"))
    tables = build_att_consolidated_results()
    os.makedirs(out_dir, exist_ok=True)
    with pd.ExcelWriter(os.path.join(out_dir, "att_consolidated_results.xlsx"), engine="openpyxl") as writer:
        for name, rows in tables.items():
            df = pd.DataFrame(rows)
            df.to_csv(os.path.join(out_dir, f"{name}.csv"), index=False)
            df.to_excel(writer, sheet_name=name[:31], index=False)
    return tables
