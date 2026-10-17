# Bioindustrial-Park: BioSTEAM's Premier Biorefinery Models and Results
# Copyright (C) 2026-, Yu Zhou,
#                      Yalin Li <mailto.yalin.li@gmail.com>
#
# This module is under the UIUC open-source license. See
# github.com/BioSTEAMDevelopmentGroup/biosteam/blob/master/LICENSE.txt
# for license details.

"""
The ATT scenarios. s1-s4 (``SCENARIOS``, used by every analysis and figure) start from the presscake of a
biostimulant plant (configuration ``presscake``: no press P1, dry presscake fed to the dryer D0). s5 starts from fresh
Sargassum (configuration ``fresh_sargassum``: press P1, its liquid is a biostimulant coproduct); it is kept in
``OPTIONAL_SCENARIOS`` so that it can be analyzed on request (``build_att_breakdown("s5")``, ``create(ALL_SCENARIOS["s5"])``)
but is not part of the standard analyses and figures.

    s1  BASELINE   presscake feed, NaOH 1 g/g daf (the team's lab dose), PSA, fresh Ca(OH)2 (cake disposed), NLR scale
    s2  ALTERNATIVE  as s1 with recycled lime (kiln + slaker)
    s3  ALTERNATIVE  as s1 with waste lime, at the scale of the waste supply
    s4  ALTERNATIVE  NaOH for full CO2 capture (2.995 g/g, gas CO2 = 0), no PSA, waste lime, same scale as s3
    s5  OPTIONAL     as s1 but starting from fresh Sargassum (press P1, juice coproduct), NLR scale (not analyzed by default)

Waste lime: a Ca(OH)2 source that needs no recalcination (carbide lime from acetylene generation), assumed pure, free
of cost and of emissions, delivered at no charge. It replaces all the lime (no kiln; the CaCO3 cake is disposed as in
the fresh-lime case, TEA Case A). Its supply is one reference-size carbide plant: 80 kt/yr CaC2 (Intratec reference
electrothermic plant) x 74.09/64.10 = 92.5 kt/yr Ca(OH)2, taken as fully captured. The scale of s3 and s4 is the one
at which s4 (the larger lime user) uses that whole supply.

The NaOH dose and the gas CO2 yield of a scenario are applied with ``dose(spec)`` (a context manager, att.yaml is not
changed); build and analyze the system inside it.
"""
from contextlib import contextmanager

from biorefineries.sabre.analyses.att import inventory as inv
from biorefineries.sabre.systems import _att_system
from biorefineries.sabre.units import _att
from biorefineries.sabre.utils import OPERATING_DAYS_PER_YEAR

__all__ = ("SCENARIOS", "OPTIONAL_SCENARIOS", "ALL_SCENARIOS", "CASES", "CASE_LABELS", "SHORT_LABELS", "WASTE_LIME_KG_PER_YR", "dose", "dry_feed_kgph",
           "create", "waste_scale_dry_kgph")

LAB_DOSE, LAB_GAS_CO2 = 1.0, 22.68                 # the team's lab dose and gas CO2 (mmol/g daf)
FULL_DOSE, FULL_GAS_CO2 = 2.995, 0.0               # 2 NaOH per CO2 generated
CARBIDE_KT_PER_YR = 80.0                           # Intratec reference carbide plant
WASTE_LIME_KG_PER_YR = CARBIDE_KT_PER_YR * 1e6 * 74.09268 / 64.0993

SCENARIOS = {
    "s1": dict(label="1 Baseline (presscake feed): fresh lime, PSA, NaOH 1 g/g, NLR scale", short="1 baseline",
               configuration="presscake", dose=LAB_DOSE, co2=LAB_GAS_CO2, psa=True, lime="fresh", scale="NLR"),
    "s2": dict(label="2 Presscake, recycled lime, PSA, NaOH 1 g/g, NLR scale", short="2 recycled lime",
               configuration="presscake", dose=LAB_DOSE, co2=LAB_GAS_CO2, psa=True, lime="recycled", scale="NLR"),
    "s3": dict(label="3 Presscake, waste lime, PSA, NaOH 1 g/g, waste scale", short="3 waste lime",
               configuration="presscake", dose=LAB_DOSE, co2=LAB_GAS_CO2, psa=True, lime="waste", scale="waste"),
    "s4": dict(label="4 Presscake, waste lime, no PSA, full CO2 capture, waste scale", short="4 waste lime, full capture",
               configuration="presscake", dose=FULL_DOSE, co2=FULL_GAS_CO2, psa=False, lime="waste", scale="waste"),
}
OPTIONAL_SCENARIOS = {
    "s5": dict(label="5 Fresh Sargassum feed (press P1): fresh lime, PSA, NaOH 1 g/g, NLR scale", short="5 fresh Sargassum",
               configuration="fresh_sargassum", dose=LAB_DOSE, co2=LAB_GAS_CO2, psa=True, lime="fresh", scale="NLR"),
}
ALL_SCENARIOS = {**SCENARIOS, **OPTIONAL_SCENARIOS}
CASES = SCENARIOS                      # the scenarios of the standard analyses
CASE_LABELS = {k: v["label"] for k, v in ALL_SCENARIOS.items()}
SHORT_LABELS = {k: v["short"] for k, v in ALL_SCENARIOS.items()}


@contextmanager
def dose(spec):
    """Apply the scenario's NaOH dose and gas CO2 yield to the reactor data (this process only)."""
    cases = [m._ATT["cases"]["Ni-CatATT"] for m in (_att_system, _att)]
    old = [(c["naoh_kg_per_kg_daf"], c["gas_yield_mmol_per_g_daf"]["CO2"]) for c in cases]
    for c in cases:
        c["naoh_kg_per_kg_daf"], c["gas_yield_mmol_per_g_daf"]["CO2"] = spec["dose"], spec["co2"]
    try:
        yield
    finally:
        for c, (d, g) in zip(cases, old):
            c["naoh_kg_per_kg_daf"], c["gas_yield_mmol_per_g_daf"]["CO2"] = d, g


def create(spec, dry_kgph=None, hxn=True):
    """Simulated system of a scenario (call inside ``dose(spec)``); operating hours are set."""
    configuration = spec["configuration"]
    ref = inv.get_att_reference_scale(configuration)
    dry_kgph = dry_feed_kgph(spec) if dry_kgph is None else dry_kgph
    system = inv._simulate(_att_system.create_att_system(
        dry_sargassum_kgph=dry_kgph, configuration=configuration, heat_exchanger_network=hxn,
        lime_recycle=spec["lime"] == "recycled", psa=spec["psa"]), dry_kgph)
    system.operating_hours = ref["operating_hours_per_year"]
    return system


def waste_scale_dry_kgph(configuration="presscake"):
    """Dry feed (kg/h) at which s4 consumes the whole waste-lime supply."""
    spec = dict(SCENARIOS["s4"], configuration=configuration)
    with dose(spec):
        small = create(spec, dry_kgph=1000.0)
    lime_per_dry = float(inv._streams(small)["lime"].imass["CaOH2"]) / 1000.0
    return WASTE_LIME_KG_PER_YR / (OPERATING_DAYS_PER_YEAR * 24.0) / lime_per_dry


_WASTE_SCALE = {}


def dry_feed_kgph(spec):
    """Dry feed of a scenario (kg/h): the NLR reference scale, or the scale of the waste-lime supply."""
    configuration = spec["configuration"]
    if spec["scale"] == "NLR":
        return inv.get_att_reference_scale(configuration)["dry_feed_kgph"]
    if configuration not in _WASTE_SCALE:
        _WASTE_SCALE[configuration] = waste_scale_dry_kgph(configuration)
    return _WASTE_SCALE[configuration]
