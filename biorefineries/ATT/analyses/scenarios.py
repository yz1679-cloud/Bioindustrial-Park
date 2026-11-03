# Bioindustrial-Park: BioSTEAM's Premier Biorefinery Models and Results
# Copyright (C) 2026-, Yu Zhou,
#                      Yalin Li <mailto.yalin.li@gmail.com>
#
# This module is under the UIUC open-source license. See
# github.com/BioSTEAMDevelopmentGroup/biosteam/blob/master/LICENSE.txt
# for license details.

"""
The ATT scenarios. One baseline, ATT Scenario 1 (key ``"att_s1"``), defined in data/att.yaml (``att.scenarios``):

    att_s1  presscake feed (no press P1, dryer D0 to 50 wt % moisture), gross NaOH 1 kg/kg DRY Sargassum,
            measured Ni-CatATT 1:1 gas yields (H2 54.15, CH4 0.60, CO 0, CO2 0.77 mmol/g daf), C1 conversion 0.88,
            waste-lime CO2 scrubber, no PSA, waste Ca(OH)2 (free, burden-free; CaCO3 cake disposed),
            capacity fixed at the SaBRe Scenario 5 waste-lime scale (5029.17 kg dry/h).

It was derived from SaBRe Scenario 5 (biorefineries/sabre). Unlike SaBRe, the NaOH dose and the gas yields are not
patched at run time (SaBRe's ``dose()`` context manager, which rewrote the CO2 yield to 22.68 mmol/g daf, is gone):
the reactor case of att.yaml is the only source, and the capacity is a fixed parameter instead of a run of
SaBRe Scenario 4.

This module is the single source of the scenario assumptions used by every standard export: the flowsheet and
capacity (``create``, ``scale``), the TEA lime and CaCO3-sales keywords (``tea_config``) and the LCA lime burden
(``lca_overrides``).
"""
from biorefineries.ATT.analyses import inventory as inv
from biorefineries.ATT import system as att_system
from biorefineries.ATT.utils import load_assumptions

__all__ = ("ATT_S1", "ATT_S2", "SCENARIOS", "OPTIONAL_SCENARIOS", "ALL_SCENARIOS", "CASES", "CASE_LABELS", "SHORT_LABELS",
           "WASTE_LIME_KG_PER_YR", "dry_feed_kgph", "create", "scale", "tea_config", "lca_overrides")

_ATT = load_assumptions("att.yaml")["att"]
_CASE = _ATT["reactor"]["cases"][_ATT["reactor"]["baseline_case"]]


def _spec(key):
    s = _ATT["scenarios"][key]
    return dict(key=key, label=s["label"], short=s["short"], configuration=s["configuration"],
                psa=bool(s["psa"]), scrubber=bool(s["co2_scrubber"]), lime=s["lime"],
                dry_feed_kgph=float(s["dry_feed_kgph"]), marine=bool(s.get("marine", False)),
                naoh_kg_per_kg_dry=float(_CASE["naoh_kg_per_kg_dry"]),
                gas_yield_mmol_per_g_daf=dict(_CASE["gas_yield_mmol_per_g_daf"]))


ATT_S1 = _spec("att_s1")
# ATT S2: same process as S1 on a ship; its WHR and floating TEA are in marine_whr.py / marine_tea.py. Kept out of
# SCENARIOS (baseline analyses); build_att_breakdown refuses it without the marine TEA hooks.
ATT_S2 = _spec("att_s2")
WASTE_LIME_KG_PER_YR = float(_ATT["scenarios"]["att_s1"]["waste_lime_supply_kg_per_yr"])

SCENARIOS = {"att_s1": ATT_S1}
OPTIONAL_SCENARIOS = {"att_s2": ATT_S2}
ALL_SCENARIOS = {**SCENARIOS, **OPTIONAL_SCENARIOS}
CASES = SCENARIOS                      # the scenarios of the standard analyses
CASE_LABELS = {k: v["label"] for k, v in ALL_SCENARIOS.items()}
SHORT_LABELS = {k: v["short"] for k, v in ALL_SCENARIOS.items()}


def create(spec=ATT_S1, dry_kgph=None, hxn=True, washing=None, wash_ratio=None, wash_recycle=None,
           wash_condensate=None, f1_wash=None, f1_wash_ratio=None,
           f1_wash_condensate=None, caco3_dry=None):
    """Simulated system of a scenario; operating hours are set. ``dry_kgph`` defaults to the scenario capacity."""
    if washing not in (None, "washing_on", "washing_off"):
        raise ValueError("washing must be washing_on, washing_off or None (configured default)")
    configuration = spec["configuration"]
    ref = inv.get_att_reference_scale(configuration)
    dry_kgph = dry_feed_kgph(spec) if dry_kgph is None else dry_kgph
    system = inv._simulate(att_system.create_att_system(
        dry_sargassum_kgph=dry_kgph, configuration=configuration, heat_exchanger_network=hxn,
        lime_recycle=spec["lime"] == "recycled", psa=spec["psa"], co2_scrubber=spec["scrubber"],
        f2_wash_enabled=None if washing is None else washing == "washing_on", f2_wash_ratio=wash_ratio,
        f2_wash_recycle=wash_recycle, f2_wash_condensate=wash_condensate,
        f1_wash=f1_wash, f1_wash_ratio=f1_wash_ratio,
        f1_wash_condensate=f1_wash_condensate, caco3_drying=caco3_dry), dry_kgph)
    system.operating_hours = ref["operating_hours_per_year"]
    return system


def dry_feed_kgph(spec=ATT_S1):
    """Plant capacity of a scenario [kg dry Sargassum/h] (att.yaml att.scenarios.<key>.dry_feed_kgph)."""
    return spec["dry_feed_kgph"]


def scale(spec=ATT_S1):
    """Annual basis of a scenario: the keys of inventory.get_att_reference_scale at the scenario capacity."""
    ref = inv.get_att_reference_scale(spec["configuration"])
    dry = dry_feed_kgph(spec)
    wet = dry / (1.0 - ref["moisture_frac"])
    return dict(ref, scenario=spec["key"], wet_feed_kgph=wet, wet_feed_t_per_day=wet * 24.0 / 1e3, dry_feed_kgph=dry,
                dry_feed_t_per_day=dry * 24.0 / 1e3, dry_feed_t_per_year=dry * ref["operating_hours_per_year"] / 1e3,
                basis=f"{spec['short']} capacity (att.yaml att.scenarios.{spec['key']}.dry_feed_kgph)",
                status=_ATT["scenarios"][spec["key"]].get("dry_feed_basis", ""))


def tea_config(spec=ATT_S1, caco3_price=None, f2_sales=True):
    """
    evaluate_att_tea keywords for the lime and CaCO3 assumptions of a scenario. Waste lime: Ca(OH)2 at 0 USD/kg.
    Without the lime recycle the cakes are products: with att_tea.yaml caco3_sales enabled their CaCO3 is sold and
    the rest disposed (counted once, on the cake stream prices), otherwise the whole cake is disposed (Case A).
    ``caco3_price`` [USD/t] overrides the configured price for this call only.
    """
    from biorefineries.ATT.analyses import tea as tea_mod     # tea imports this module
    recycled = spec["lime"] == "recycled"
    sales = dict(tea_mod._T["caco3_sales"])
    if caco3_price is not None:
        sales["price_usd_per_metric_ton"] = float(caco3_price)
    if not f2_sales:
        sales["saleable_fraction_by_stream"] = {"caco3_cake": 0.0}
    sell = bool(sales.pop("enabled")) and not recycled
    return dict(price_overrides={"CaOH2": 0.0} if spec["lime"] == "waste" else None,
                caco3=None if recycled else dict(fraction=0.0),
                caco3_sales=sales if sell else None)


def lca_overrides(spec=ATT_S1):
    """apply_att_gwp factor overrides of a scenario: waste lime is burden-free."""
    return {"CaOH2_limestone": 0.0} if spec["lime"] == "waste" else None
