# Bioindustrial-Park: BioSTEAM's Premier Biorefinery Models and Results
# Copyright (C) 2026-, Yu Zhou,
#                      Yalin Li <mailto.yalin.li@gmail.com>
#
# This module is under the UIUC open-source license. See
# github.com/BioSTEAMDevelopmentGroup/biosteam/blob/master/LICENSE.txt
# for license details.

"""
The four ATT scenarios used by every analysis (ATT-only configuration: raw Sargassum, press P1, dryer D0; the press
liquid is a biostimulant coproduct):

    s1  BASELINE   NaOH 1 g/g daf (the team's lab dose), PSA, fresh Ca(OH)2 (cake disposed), NLR scale
    s2  ALTERNATIVE  as s1 with recycled lime (kiln + slaker)
    s3  ALTERNATIVE  as s1 with waste lime, at the scale of the waste supply
    s4  ALTERNATIVE  NaOH for full CO2 capture (2.995 g/g, gas CO2 = 0), no PSA, waste lime, same scale as s3

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

__all__ = ("SCENARIOS", "CASES", "CASE_LABELS", "SHORT_LABELS", "CONFIGURATION", "WASTE_LIME_KG_PER_YR", "dose",
           "dry_feed_kgph", "create", "waste_scale_dry_kgph")

CONFIGURATION = "att_only"
LAB_DOSE, LAB_GAS_CO2 = 1.0, 22.68                 # the team's lab dose and gas CO2 (mmol/g daf)
FULL_DOSE, FULL_GAS_CO2 = 2.995, 0.0               # 2 NaOH per CO2 generated
CARBIDE_KT_PER_YR = 80.0                           # Intratec reference carbide plant
WASTE_LIME_KG_PER_YR = CARBIDE_KT_PER_YR * 1e6 * 74.09268 / 64.0993

SCENARIOS = {
    "s1": dict(label="1 Baseline: fresh lime, PSA, NaOH 1 g/g, NLR scale", short="1 baseline",
               dose=LAB_DOSE, co2=LAB_GAS_CO2, psa=True, lime="fresh", scale="NLR"),
    "s2": dict(label="2 Recycled lime, PSA, NaOH 1 g/g, NLR scale", short="2 recycled lime",
               dose=LAB_DOSE, co2=LAB_GAS_CO2, psa=True, lime="recycled", scale="NLR"),
    "s3": dict(label="3 Waste lime, PSA, NaOH 1 g/g, waste scale", short="3 waste lime",
               dose=LAB_DOSE, co2=LAB_GAS_CO2, psa=True, lime="waste", scale="waste"),
    "s4": dict(label="4 Waste lime, no PSA, full CO2 capture, waste scale", short="4 waste lime, full capture",
               dose=FULL_DOSE, co2=FULL_GAS_CO2, psa=False, lime="waste", scale="waste"),
}
CASES = SCENARIOS
CASE_LABELS = {k: v["label"] for k, v in SCENARIOS.items()}
SHORT_LABELS = {k: v["short"] for k, v in SCENARIOS.items()}


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
    ref = inv.get_att_reference_scale(CONFIGURATION)
    dry_kgph = dry_feed_kgph(spec) if dry_kgph is None else dry_kgph
    system = inv._simulate(_att_system.create_att_system(
        dry_sargassum_kgph=dry_kgph, configuration=CONFIGURATION, heat_exchanger_network=hxn,
        lime_recycle=spec["lime"] == "recycled", psa=spec["psa"]), dry_kgph)
    system.operating_hours = ref["operating_hours_per_year"]
    return system


def waste_scale_dry_kgph():
    """Dry feed (kg/h) at which s4 consumes the whole waste-lime supply."""
    spec = SCENARIOS["s4"]
    with dose(spec):
        small = create(spec, dry_kgph=1000.0)
    lime_per_dry = float(inv._streams(small)["lime"].imass["CaOH2"]) / 1000.0
    return WASTE_LIME_KG_PER_YR / (OPERATING_DAYS_PER_YEAR * 24.0) / lime_per_dry


_WASTE_SCALE = []


def dry_feed_kgph(spec):
    if spec["scale"] == "NLR":
        return inv.get_att_reference_scale(CONFIGURATION)["dry_feed_kgph"]
    if not _WASTE_SCALE:
        _WASTE_SCALE.append(waste_scale_dry_kgph())
    return _WASTE_SCALE[0]
