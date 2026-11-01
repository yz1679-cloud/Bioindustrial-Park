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
"""
from biorefineries.ATT.analyses.att import inventory as inv
from biorefineries.ATT.systems import _att_system
from biorefineries.ATT.utils import load_assumptions

__all__ = ("ATT_S1", "ATT_S2", "SCENARIOS", "OPTIONAL_SCENARIOS", "ALL_SCENARIOS", "CASES", "CASE_LABELS", "SHORT_LABELS",
           "WASTE_LIME_KG_PER_YR", "dry_feed_kgph", "create")

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
# SCENARIOS (the land-based standard analyses); build_att_breakdown refuses it without the marine TEA hooks.
ATT_S2 = _spec("att_s2")
WASTE_LIME_KG_PER_YR = float(_ATT["scenarios"]["att_s1"]["waste_lime_supply_kg_per_yr"])

SCENARIOS = {"att_s1": ATT_S1}
OPTIONAL_SCENARIOS = {"att_s2": ATT_S2}
ALL_SCENARIOS = {**SCENARIOS, **OPTIONAL_SCENARIOS}
CASES = SCENARIOS                      # the scenarios of the standard analyses
CASE_LABELS = {k: v["label"] for k, v in ALL_SCENARIOS.items()}
SHORT_LABELS = {k: v["short"] for k, v in ALL_SCENARIOS.items()}


def create(spec=ATT_S1, dry_kgph=None, hxn=True):
    """Simulated system of a scenario; operating hours are set. ``dry_kgph`` defaults to the scenario capacity."""
    configuration = spec["configuration"]
    ref = inv.get_att_reference_scale(configuration)
    dry_kgph = dry_feed_kgph(spec) if dry_kgph is None else dry_kgph
    system = inv._simulate(_att_system.create_att_system(
        dry_sargassum_kgph=dry_kgph, configuration=configuration, heat_exchanger_network=hxn,
        lime_recycle=spec["lime"] == "recycled", psa=spec["psa"], co2_scrubber=spec["scrubber"]), dry_kgph)
    system.operating_hours = ref["operating_hours_per_year"]
    return system


def dry_feed_kgph(spec=ATT_S1):
    """Plant capacity of a scenario [kg dry Sargassum/h] (att.yaml att.scenarios.<key>.dry_feed_kgph)."""
    return spec["dry_feed_kgph"]
