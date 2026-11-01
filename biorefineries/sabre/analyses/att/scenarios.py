# Bioindustrial-Park: BioSTEAM's Premier Biorefinery Models and Results
# Copyright (C) 2026-, Yu Zhou,
#                      Yalin Li <mailto.yalin.li@gmail.com>
#
# This module is under the UIUC open-source license. See
# github.com/BioSTEAMDevelopmentGroup/biosteam/blob/master/LICENSE.txt
# for license details.

"""
The ATT scenario used by every analysis: the BASELINE (key ``"baseline"``, formerly SaBRe Scenario 5), defined in
data/att.yaml (``att.scenarios.baseline``) and reconciled with ATT Scenario 1 of the ATT branch:

    presscake feed (no press P1, dryer D0 to 50 wt % moisture), gross NaOH 1 kg/kg DRY Sargassum, measured
    Ni-CatATT 1:1 gas yields (H2 54.15, CH4 0.60, CO 0, CO2 0.77 mmol/g daf), the remaining carbon in the lumped
    residue (ATT char), C1 conversion 0.88, F2 cake washing, waste-lime CO2 scrubber, no PSA, waste Ca(OH)2 (free,
    burden-free; CaCO3 cake disposed at the solid-waste price, no CaCO3 revenue), capacity fixed at 5029.17 kg dry/h
    (the SaBRe waste-lime scale: one 80 kt/yr carbide plant).

``OPTIONAL_SCENARIOS`` keeps the fresh-Sargassum feed (press P1, juice coproduct; same chemistry and lime as the
baseline, NLR scale) for analysis on request (``build_att_breakdown("fresh_sargassum")``); it is not part of the
standard analyses and figures. The earlier SaBRe scenarios 1-4 (fresh/recycled lime, PSA, full CO2 capture) are not
kept; the flowsheet options (``lime_recycle``, ``psa``) remain in ``create_att_system``.

The NaOH dose and the gas yields come from the reactor case of att.yaml only (nothing is patched at run time).
"""
from biorefineries.sabre.analyses.att import inventory as inv
from biorefineries.sabre.systems import _att_system
from biorefineries.sabre.utils import load_assumptions

__all__ = ("SCENARIOS", "OPTIONAL_SCENARIOS", "ALL_SCENARIOS", "CASES", "CASE_LABELS", "SHORT_LABELS",
           "WASTE_LIME_KG_PER_YR", "dry_feed_kgph", "create", "scale", "tea_config", "lca_overrides")

_ATT = load_assumptions("att.yaml")["att"]
_CASE = _ATT["reactor"]["cases"][_ATT["reactor"]["baseline_case"]]
_BASE = _ATT["scenarios"]["baseline"]

WASTE_LIME_KG_PER_YR = float(_BASE["waste_lime_supply_kg_per_yr"])

BASELINE = dict(
    key="baseline", label=_BASE["label"], short=_BASE["short"], configuration=_BASE["configuration"],
    psa=bool(_BASE["psa"]), scrubber=bool(_BASE["co2_scrubber"]), lime=_BASE["lime"],
    dry_feed_kgph=float(_BASE["dry_feed_kgph"]), naoh_kg_per_kg_dry=float(_CASE["naoh_kg_per_kg_dry"]),
    gas_yield_mmol_per_g_daf=dict(_CASE["gas_yield_mmol_per_g_daf"]))

FRESH_SARGASSUM = dict(BASELINE, key="fresh_sargassum", configuration="fresh_sargassum", dry_feed_kgph=None,
                       label="Fresh Sargassum feed (press P1), otherwise the baseline", short="fresh Sargassum")

SCENARIOS = {"baseline": BASELINE}
OPTIONAL_SCENARIOS = {"fresh_sargassum": FRESH_SARGASSUM}
ALL_SCENARIOS = {**SCENARIOS, **OPTIONAL_SCENARIOS}
CASES = SCENARIOS                      # the scenarios of the standard analyses
CASE_LABELS = {k: v["label"] for k, v in ALL_SCENARIOS.items()}
SHORT_LABELS = {k: v["short"] for k, v in ALL_SCENARIOS.items()}


def dry_feed_kgph(spec=BASELINE):
    """Plant capacity of a scenario [kg dry feed/h]: fixed (att.yaml) or the NLR reference scale."""
    if spec["dry_feed_kgph"] is not None:
        return spec["dry_feed_kgph"]
    return inv.get_att_reference_scale(spec["configuration"])["dry_feed_kgph"]


def create(spec=BASELINE, dry_kgph=None, hxn=True, washing=None, wash_ratio=None):
    """Simulated system of a scenario; operating hours are set. ``dry_kgph`` defaults to the scenario capacity."""
    if washing not in (None, "washing_on", "washing_off"):
        raise ValueError("washing must be washing_on, washing_off or None (configured default)")
    configuration = spec["configuration"]
    ref = inv.get_att_reference_scale(configuration)
    dry_kgph = dry_feed_kgph(spec) if dry_kgph is None else dry_kgph
    system = inv._simulate(_att_system.create_att_system(
        dry_sargassum_kgph=dry_kgph, configuration=configuration, heat_exchanger_network=hxn,
        lime_recycle=spec["lime"] == "recycled", psa=spec["psa"], co2_scrubber=spec["scrubber"],
        f2_wash_enabled=None if washing is None else washing == "washing_on", f2_wash_ratio=wash_ratio), dry_kgph)
    system.operating_hours = ref["operating_hours_per_year"]
    return system


def scale(spec=BASELINE):
    """Annual basis of a scenario: the keys of inventory.get_att_reference_scale at the scenario capacity."""
    ref = inv.get_att_reference_scale(spec["configuration"])
    dry = dry_feed_kgph(spec)
    wet = dry / (1.0 - ref["moisture_frac"])
    return dict(ref, scenario=spec["key"], wet_feed_kgph=wet, wet_feed_t_per_day=wet * 24.0 / 1e3, dry_feed_kgph=dry,
                dry_feed_t_per_day=dry * 24.0 / 1e3, dry_feed_t_per_year=dry * ref["operating_hours_per_year"] / 1e3,
                basis=f"{spec['short']} capacity (att.yaml att.scenarios.baseline.dry_feed_kgph)")


def tea_config(spec=BASELINE):
    """evaluate_att_tea keywords for the lime and CaCO3 assumptions: waste lime at 0 USD/kg; the cakes are disposed."""
    recycled = spec["lime"] == "recycled"
    return dict(price_overrides={"CaOH2": 0.0} if spec["lime"] == "waste" else None,
                caco3=None if recycled else dict(fraction=0.0))


def lca_overrides(spec=BASELINE):
    """apply_att_gwp factor overrides of a scenario: waste lime is burden-free."""
    return {"CaOH2_limestone": 0.0} if spec["lime"] == "waste" else None
