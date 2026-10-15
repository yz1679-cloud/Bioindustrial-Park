
"""
ATT heat-integration analysis utilities.

Purpose
-------
This module sits on top of the validated ATT process model and does NOT modify
the process flowsheet. It is intended to:

1. Identify hot process streams / cooling duties.
2. Identify cold process streams / heating duties.
3. Summarize heating, cooling, and power requirements.
4. Check whether a hot stream is thermally capable of serving a cold stream
   using a minimum approach temperature criterion.
5. Audit all modeled heating and cooling utilities separately, without
   automatically treating cooling as recoverable heat.
6. Provide a clean foundation for later heat matching / HEN work.

Current scope
-------------
- Physical heat only.
- No combustion credit from PSA tail gas.
- No U2 reaction enthalpy credit.
- No TEA/LCA logic.
- No sensitivity analysis.
- No automatic heat exchanger network optimization yet.

Notes
-----
The current ATT model includes custom and native units. For heat-integration
screening, the most important information is taken from actual simulated stream
temperatures and BioSTEAM heat utilities wherever possible.

The initial baseline focuses on:
    Hot-side candidates:
        U3HX : cooling / condensation of U2 hot gas/steam
        RC1  : cooling of hot ATT residue

    Cold-side candidates:
        D0   : drying duty
        U2   : ATT reactor duty (fired; not heat-integrated)
        C1   : causticization heating duty
        EC1  : recycle-liquor evaporation duty
        U3D  : molecular-sieve heating duty, if positive

This module is deliberately conservative: a duty is not counted as recovered
heat simply because it exists. Temperature feasibility must first be checked.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Optional

# Shared with the energy accounting (same definitions as before the merge).
from biorefineries.sabre.analyses.att.mass_energy import _positive_heat_utility_kJph, _units_of

__all__ = (
    "HeatStream",
    "get_hot_streams",
    "get_cold_streams",
    "get_heat_duty_summary",
    "get_heat_utility_audit",
    "format_heat_utility_audit",
    "HeatInterval",
    "calculate_temperature_cascade",
    "get_att_temperature_audit",
    "get_att_heat_recovery_assessment",
    "format_att_heat_recovery_assessment",
    "get_att_process_heat_intervals",
    "get_att_pinch_targets",
    "design_att_heat_exchanger_network",
    "format_att_heat_exchanger_network",
    "check_temperature_feasibility",
    "build_temperature_feasibility_matrix",
)


# ---------------------------------------------------------------------
# Data container
# ---------------------------------------------------------------------

@dataclass
class HeatStream:
    """
    Container for a heat-integration candidate.

    Parameters
    ----------
    name :
        Short descriptive name.
    unit_id :
        BioSTEAM unit ID associated with this heat stream.
    kind :
        "hot" or "cold".
    duty_kJph :
        Positive magnitude of heat available or required [kJ/h].
    T_in_K :
        Process-stream inlet temperature [K].
    T_out_K :
        Process-stream outlet/target temperature [K].
    description :
        Human-readable explanation.
    basis :
        How the duty was obtained, e.g. BioSTEAM heat utility or process
        enthalpy drop.
    include_in_matching :
        Whether this stream should currently be considered for heat matching.
    """

    name: str
    unit_id: str
    kind: str
    duty_kJph: float
    T_in_K: Optional[float]
    T_out_K: Optional[float]
    description: str = ""
    basis: str = ""
    include_in_matching: bool = True

    @property
    def duty_kW(self) -> float:
        return self.duty_kJph / 3600.0


# ---------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------

def _negative_heat_utility_magnitude_kJph(unit) -> float:
    """Return magnitude of total negative BioSTEAM heat-utility duty [kJ/h]."""
    return sum(
        max(-float(hu.duty), 0.0)
        for hu in unit.heat_utilities
    )


def _process_enthalpy_drop_kJph(unit) -> float:
    """
    Return process-stream enthalpy drop across a 1-in / 1-out unit [kJ/h].

    Positive result means the process stream released heat.

    This is useful for units such as U3HX and RC1, where the stream itself
    carries the thermal energy that may later be recovered.
    """
    if len(unit.ins) != 1 or len(unit.outs) != 1:
        raise ValueError(
            f"{unit.ID} must have exactly one inlet and one outlet "
            "for direct process-enthalpy-drop calculation."
        )

    H_in = float(unit.ins[0].H)
    H_out = float(unit.outs[0].H)

    return max(H_in - H_out, 0.0)


def _stream_temperature(stream) -> Optional[float]:
    try:
        return float(stream.T)
    except Exception:
        return None


def _unit_inlet_temperature(unit) -> Optional[float]:
    """
    Representative inlet temperature for screening.

    For one-inlet units, this is exact.
    For mixers / multi-inlet units, this is intentionally not guessed;
    return None unless a later unit-specific treatment is added.
    """
    if len(unit.ins) == 1:
        return _stream_temperature(unit.ins[0])
    return None


def _unit_outlet_temperature(unit) -> Optional[float]:
    """
    Representative outlet temperature for screening.

    For one-outlet units, this is exact.
    Otherwise, return None unless explicitly handled.
    """
    if len(unit.outs) == 1:
        return _stream_temperature(unit.outs[0])
    return None


# ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------

def get_hot_streams(sys) -> list[HeatStream]:
    """
    Return current hot-stream candidates for physical heat recovery.

    Important
    ---------
    This does NOT mean the heat is actually recoverable. It only identifies
    streams that release heat and could potentially serve cold streams.

    Current baseline
    ----------------
    U3HX
        Cooling / partial condensation of U2 hot gas/steam.

    RC1
        Cooling of hot U2 residue from ATT temperature to downstream
        dissolution temperature.

    Additional hot streams can be added later if the process model develops
    new cooling duties.
    """
    u = _units_of(sys)

    hot_streams: list[HeatStream] = []

    # --------------------------------------------------------------
    # U3HX: U2 hot gas/steam cooling + partial condensation
    # --------------------------------------------------------------
    q_u3hx = _process_enthalpy_drop_kJph(u.U3HX)

    hot_streams.append(
        HeatStream(
            name="U2 hot gas/steam cooling",
            unit_id="U3HX",
            kind="hot",
            duty_kJph=q_u3hx,
            T_in_K=_stream_temperature(u.U3HX.ins[0]),
            T_out_K=_stream_temperature(u.U3HX.outs[0]),
            description=(
                "Physical heat released while cooling / partially condensing "
                "the U2 hot gas/steam stream before U3 separation."
            ),
            basis="Process-stream enthalpy drop",
        )
    )

    # --------------------------------------------------------------
    # RC1: hot ATT residue cooling
    # --------------------------------------------------------------
    q_rc1 = _process_enthalpy_drop_kJph(u.RC1)

    hot_streams.append(
        HeatStream(
            name="ATT residue cooling",
            unit_id="RC1",
            kind="hot",
            duty_kJph=q_rc1,
            T_in_K=_stream_temperature(u.RC1.ins[0]),
            T_out_K=_stream_temperature(u.RC1.outs[0]),
            description=(
                "Sensible heat released while cooling the hot U2 residue "
                "before downstream dissolution."
            ),
            basis="Process-stream enthalpy drop",
        )
    )

    return hot_streams


def get_cold_streams(sys) -> list[HeatStream]:
    """
    Return current cold-stream / heating-duty candidates.

    Current baseline
    ----------------
    D0
        Native dryer heating duty.

    U2
        ATT feed heating duty only. Reaction enthalpy is intentionally
        excluded because the U2 empirical chemistry is not atom-balanced.

    C1
        Causticization heating duty.

    EC1
        Native evaporator heating duty.

    U3D
        Molecular-sieve heating duty, if positive.

    Notes
    -----
    This function uses BioSTEAM heat utilities wherever possible.
    """
    u = _units_of(sys)

    cold_streams: list[HeatStream] = []

    # --------------------------------------------------------------
    # D0 dryer
    # --------------------------------------------------------------
    q_d0 = _positive_heat_utility_kJph(u.D0)

    cold_streams.append(
        HeatStream(
            name="D0 drying",
            unit_id="D0",
            kind="cold",
            duty_kJph=q_d0,
            T_in_K=_unit_inlet_temperature(u.D0),
            T_out_K=_unit_outlet_temperature(u.D0),
            description=(
                "Heating / evaporation demand associated with drying "
                "the pressed Sargassum cake."
            ),
            basis="BioSTEAM positive heat utility",
        )
    )

    # --------------------------------------------------------------
    # U2 ATT heating
    # --------------------------------------------------------------
    q_u2 = _positive_heat_utility_kJph(u.U2)

    cold_streams.append(
        HeatStream(
            name="U2 ATT feed heating",
            unit_id="U2",
            kind="cold",
            duty_kJph=q_u2,
            T_in_K=_unit_inlet_temperature(u.U2),
            T_out_K=_unit_outlet_temperature(u.U2),
            description=(
                "Thermal duty assigned by the current U2 model for heating "
                "the ATT feed. Reaction enthalpy is not separately credited."
            ),
            basis="BioSTEAM positive heat utility",
        )
    )

    # --------------------------------------------------------------
    # C1 causticization
    # --------------------------------------------------------------
    q_c1 = _positive_heat_utility_kJph(u.C1)

    cold_streams.append(
        HeatStream(
            name="C1 causticization heating",
            unit_id="C1",
            kind="cold",
            duty_kJph=q_c1,
            T_in_K=_unit_inlet_temperature(u.C1),
            T_out_K=_unit_outlet_temperature(u.C1),
            description=(
                "Heating demand for causticization to the current 90 degC "
                "operating condition."
            ),
            basis="BioSTEAM positive heat utility",
        )
    )

    # --------------------------------------------------------------
    # EC1 native evaporator
    # --------------------------------------------------------------
    q_ec1 = _positive_heat_utility_kJph(u.EC1)

    cold_streams.append(
        HeatStream(
            name="EC1 recycle-liquor concentration",
            unit_id="EC1",
            kind="cold",
            duty_kJph=q_ec1,
            T_in_K=_unit_inlet_temperature(u.EC1),
            T_out_K=_unit_outlet_temperature(u.EC1),
            description=(
                "Evaporation duty for concentrating the recycle alkali liquor "
                "to the current 50 wt% NaOH total-liquor basis."
            ),
            basis="BioSTEAM positive heat utility",
        )
    )

    # --------------------------------------------------------------
    # U3D molecular sieve
    # --------------------------------------------------------------
    q_u3d = _positive_heat_utility_kJph(u.U3D)

    cold_streams.append(
        HeatStream(
            name="U3D molecular-sieve heating",
            unit_id="U3D",
            kind="cold",
            duty_kJph=q_u3d,
            T_in_K=_unit_inlet_temperature(u.U3D),
            T_out_K=_unit_outlet_temperature(u.U3D),
            description=(
                "Native MolecularSieve heating duty. This remains provisional "
                "for ATT gas service because the built-in correlation is not "
                "ATT-specific."
            ),
            basis="BioSTEAM positive heat utility",
            include_in_matching=(q_u3d > 0.0),
        )
    )

    return cold_streams


def get_heat_duty_summary(sys) -> dict:
    """
    Summarize gross heating and cooling duties before heat integration.

    Returns
    -------
    dict
        Includes:
        - hot_streams
        - cold_streams
        - gross_hot_available_kJph
        - gross_cold_demand_kJph
        - gross_hot_available_kW
        - gross_cold_demand_kW

    Important
    ---------
    ``gross_hot_available`` is only thermodynamic availability at the
    process-stream level. It is NOT yet recovered heat.
    """
    hot_streams = get_hot_streams(sys)
    cold_streams = get_cold_streams(sys)

    gross_hot = sum(
        stream.duty_kJph
        for stream in hot_streams
        if stream.include_in_matching
    )

    gross_cold = sum(
        stream.duty_kJph
        for stream in cold_streams
        if stream.include_in_matching
    )

    return {
        "hot_streams": hot_streams,
        "cold_streams": cold_streams,
        "gross_hot_available_kJph": gross_hot,
        "gross_cold_demand_kJph": gross_cold,
        "gross_hot_available_kW": gross_hot / 3600.0,
        "gross_cold_demand_kW": gross_cold / 3600.0,
    }


def check_temperature_feasibility(
    hot_stream: HeatStream,
    cold_stream: HeatStream,
    delta_T_min_K: float = 10.0,
) -> dict:
    """
    Screen whether a hot stream can thermally serve a cold stream.

    This is a FIRST-PASS feasibility check only.

    Criterion
    ---------
    A match is considered temperature-feasible when:

        hot inlet temperature >= cold target temperature + delta_T_min

    and

        hot outlet temperature >= cold inlet temperature + delta_T_min

    whenever all four temperatures are available.

    If some temperatures are unavailable, the function returns
    ``status='INSUFFICIENT_TEMPERATURE_DATA'`` rather than guessing.

    Parameters
    ----------
    hot_stream :
        HeatStream with kind="hot".
    cold_stream :
        HeatStream with kind="cold".
    delta_T_min_K :
        Minimum approach temperature [K]. Default = 10 K.

    Returns
    -------
    dict
    """
    if hot_stream.kind != "hot":
        raise ValueError(
            f"{hot_stream.name} is not marked as a hot stream."
        )

    if cold_stream.kind != "cold":
        raise ValueError(
            f"{cold_stream.name} is not marked as a cold stream."
        )

    temps = (
        hot_stream.T_in_K,
        hot_stream.T_out_K,
        cold_stream.T_in_K,
        cold_stream.T_out_K,
    )

    if any(T is None for T in temps):
        return {
            "hot_stream": hot_stream.name,
            "cold_stream": cold_stream.name,
            "delta_T_min_K": delta_T_min_K,
            "feasible": None,
            "status": "INSUFFICIENT_TEMPERATURE_DATA",
        }

    hot_in = float(hot_stream.T_in_K)
    hot_out = float(hot_stream.T_out_K)
    cold_in = float(cold_stream.T_in_K)
    cold_out = float(cold_stream.T_out_K)

    hot_end_ok = (
        hot_in
        >= cold_out + delta_T_min_K
    )

    cold_end_ok = (
        hot_out
        >= cold_in + delta_T_min_K
    )

    feasible = hot_end_ok and cold_end_ok

    return {
        "hot_stream": hot_stream.name,
        "cold_stream": cold_stream.name,
        "hot_T_in_K": hot_in,
        "hot_T_out_K": hot_out,
        "cold_T_in_K": cold_in,
        "cold_T_out_K": cold_out,
        "delta_T_min_K": delta_T_min_K,
        "hot_end_approach_K": hot_in - cold_out,
        "cold_end_approach_K": hot_out - cold_in,
        "feasible": feasible,
        "status": "FEASIBLE" if feasible else "NOT_FEASIBLE",
    }


def build_temperature_feasibility_matrix(
    sys,
    delta_T_min_K: float = 10.0,
) -> list[dict]:
    """
    Check every current hot-stream / cold-stream pairing.

    Returns
    -------
    list[dict]
        One record per hot-cold pair.

    Notes
    -----
    This does not allocate heat duty. It only screens temperature
    compatibility. Actual duty matching comes later.
    """
    hot_streams = get_hot_streams(sys)
    cold_streams = get_cold_streams(sys)

    results = []

    for hot in hot_streams:
        if not hot.include_in_matching:
            continue

        for cold in cold_streams:
            if not cold.include_in_matching:
                continue

            results.append(
                check_temperature_feasibility(
                    hot_stream=hot,
                    cold_stream=cold,
                    delta_T_min_K=delta_T_min_K,
                )
            )

    return results


# ---------------------------------------------------------------------
# Step 7.8A: full heat-UTILITY audit (not an HEN heat-recovery model)
# ---------------------------------------------------------------------

# A positive heat utility is a heating requirement; a negative utility is a
# cooling requirement. Both signs can legitimately occur on one unit, most
# notably EC1. They must NEVER be netted to estimate recoverable process heat.
#
# Only U3HX and RC1 are currently represented by actual physical hot streams
# with process-inlet/outlet temperatures and an enthalpy-drop calculation.
# Their utility duties appear below for ACCOUNTING, not as extra hot streams.
_KNOWN_HOT_STREAM_UNITS = frozenset({"U3HX", "RC1"})
_KNOWN_COLD_DUTY_UNITS = frozenset({"D0", "U2", "C1", "EC1"})
_PROVISIONAL_UNIT_IDS = frozenset({"U3D"})


def _audit_units(sys):
    """Find top-level system units, avoiding repeated *unit objects*.

    ``sys.units`` is the usual BioSTEAM interface. A minimal test stand-in
    with ``sys.flowsheet.unit`` is also accepted for deterministic testing.
    This inventory does not intentionally descend into ``auxiliary_units``:
    parent units may already aggregate their auxiliaries' heat utilities.
    """
    units = getattr(sys, "units", None)
    if units is None:
        container = sys.flowsheet.unit
        if isinstance(container, dict):
            units = container.values()
        else:
            units = vars(container).values()

    visited = set()
    for unit in units:
        if not hasattr(unit, "ID") or not hasattr(unit, "heat_utilities"):
            continue
        identity = id(unit)
        if identity not in visited:
            visited.add(identity)
            yield unit


def _utility_audit_classification(unit_id: str, direction: str) -> str:
    """Classify for follow-up, *not* as proof of recoverability."""
    if direction == "zero":
        return "ZERO_DUTY"
    if unit_id in _PROVISIONAL_UNIT_IDS:
        return "PROVISIONAL_NATIVE_MODEL"
    if direction == "cooling":
        if unit_id in _KNOWN_HOT_STREAM_UNITS:
            return "EXPLICIT_HOT_STREAM_CANDIDATE"
        if unit_id == "EC1":
            return "CONDENSER_REVIEW_REQUIRED"
        return "UNASSESSED_COOLING"
    if unit_id in _KNOWN_COLD_DUTY_UNITS:
        return "EXPLICIT_COLD_DUTY"
    return "UNASSESSED_HEATING"


def get_heat_utility_audit(sys) -> dict:
    """Inventory all recorded heat utilities of the modeled system [kJ/h].

    Run ``sys.simulate()`` with BioSTEAM equipment design enabled first.
    Merely calling ``sys.simulate(design_and_cost=False)`` may omit native
    equipment utilities, causing artificially zero duty totals.

    Returns
    -------
    dict
        ``units``: one row per top-level unit, including those with no duties.
        ``utilities``: one row per heat utility; positive = heating,
        negative = cooling. ``summary``: independent heating and cooling
        magnitudes, along with conservative hot-side accounting.
        ``warnings``: duplicate references (if any) and scope notes.

    Accounting rules
    ----------------
    * EC1 may have BOTH heating and cooling utilities; do not net them.
    * Utility agent temperatures (if accessible) are NOT process-stream
      temperature profiles and are not used for temperature matching.
    * Only U3HX and RC1 currently contribute to explicit process-stream
      hot candidates. Other cooling loads, especially EC1 and U3D, require
      separate duty/temperature/phase assessment before matching.
    * A shared HeatUtility object appearing under multiple unit references
      is included only once; a warning is recorded. Auxiliary equipment is
      not recursed into to avoid summing parent and auxiliary accounting.
    * This is a utility inventory. It is not a whole-process first-law
      balance and does not include thermal content of all uncooled streams,
      equipment power, heat losses, or reaction enthalpy not modeled.
    """
    utility_rows = []
    unit_rows = []
    warnings = []
    seen_utility_objects = {}  # id(HeatUtility) -> first unit ID

    for unit in _audit_units(sys):
        ID = str(unit.ID)
        heating = 0.0
        cooling = 0.0
        duplicate_count = 0
        utility_count = 0

        for index, hu in enumerate(unit.heat_utilities):
            # Avoid counting the same HeatUtility object twice if the library
            # presents it through both a parent and a nested unit.
            hu_identity = id(hu)
            if hu_identity in seen_utility_objects:
                duplicate_count += 1
                warnings.append(
                    f"Repeated HeatUtility object on {ID}[{index}], "
                    f"already counted on {seen_utility_objects[hu_identity]}; "
                    "excluded from totals."
                )
                continue
            seen_utility_objects[hu_identity] = ID

            duty = float(hu.duty)
            if not math.isfinite(duty):
                raise ValueError(f"Non-finite heat utility duty on {ID}[{index}]: {duty}")
            direction = "heating" if duty > 0 else "cooling" if duty < 0 else "zero"
            magnitude = abs(duty)
            if duty > 0:
                heating += duty
            elif duty < 0:
                cooling -= duty
            utility_count += 1

            agent = getattr(hu, "agent", None)
            agent_ID = getattr(agent, "ID", None)
            if agent_ID is None and agent is not None:
                agent_ID = str(agent)
            utility_rows.append({
                "unit_id": ID,
                "utility_index": index,
                "duty_kJph": duty,
                "magnitude_kJph": magnitude,
                "direction": direction,
                "agent_id": agent_ID,
                "classification": _utility_audit_classification(ID, direction),
            })

        unit_rows.append({
            "unit_id": ID,
            "unit_type": type(unit).__name__,
            "heating_kJph": heating,
            "cooling_kJph": cooling,
            "net_utility_kJph": heating - cooling,
            "heat_utility_count": utility_count,
            "duplicate_utility_count": duplicate_count,
        })

    mixed_duty_unit_ids = [
        row["unit_id"] for row in unit_rows
        if row["heating_kJph"] > 0 and row["cooling_kJph"] > 0
    ]
    total_heating = sum(row["heating_kJph"] for row in unit_rows)
    total_cooling = sum(row["cooling_kJph"] for row in unit_rows)
    hot_candidate_cooling = sum(
        row["cooling_kJph"] for row in unit_rows
        if row["unit_id"] in _KNOWN_HOT_STREAM_UNITS
    )
    other_cooling = total_cooling - hot_candidate_cooling
    selected_cold_heating = sum(
        row["heating_kJph"] for row in unit_rows
        if row["unit_id"] in (_KNOWN_COLD_DUTY_UNITS | _PROVISIONAL_UNIT_IDS)
    )

    return {
        "units": unit_rows,
        "utilities": utility_rows,
        "summary": {
            "total_heating_kJph": total_heating,
            "total_cooling_kJph": total_cooling,
            "net_utility_kJph": total_heating - total_cooling,
            "explicit_hot_candidate_cooling_kJph": hot_candidate_cooling,
            "additional_cooling_requires_review_kJph": other_cooling,
            "selected_cold_heating_kJph": selected_cold_heating,
            "additional_heating_requires_review_kJph": total_heating - selected_cold_heating,
            "total_heating_kW": total_heating / 3600.0,
            "total_cooling_kW": total_cooling / 3600.0,
            "mixed_duty_unit_ids": mixed_duty_unit_ids,
        },
        "warnings": warnings,
    }


def format_heat_utility_audit(audit: dict) -> str:
    """Create a compact, plain-text human-readable Step 7.8A audit report."""
    lines = [
        "=== STEP 7.8A | FULL ATT HEAT UTILITY AUDIT ===",
        "NOTE: utilities are separate heating/cooling obligations, NOT recovered heat.",
        f"{'Unit':<10}{'Equipment':<27}{'Heating kJ/h':>17}"
        f"{'Cooling kJ/h':>17}{'HU count':>11}",
        "-" * 82,
    ]
    for row in audit["units"]:
        lines.append(
            f"{row['unit_id']:<10}{row['unit_type'][:26]:<27}"
            f"{row['heating_kJph']:>17,.3f}{row['cooling_kJph']:>17,.3f}"
            f"{row['heat_utility_count']:>11d}"
        )
    summary = audit["summary"]
    lines.extend([
        "-" * 82,
        f"TOTAL external heating utilities (kJ/h): {summary['total_heating_kJph']:,.3f}",
        f"TOTAL external cooling utilities (kJ/h): {summary['total_cooling_kJph']:,.3f}",
        f"Explicit hot candidate unit cooling (U3HX + RC1; kJ/h): "
        f"{summary['explicit_hot_candidate_cooling_kJph']:,.3f}",
        f"OTHER cooling requires review (kJ/h): "
        f"{summary['additional_cooling_requires_review_kJph']:,.3f}",
        "NOTE: EC1 condenser and U3D utility cooling are NOT automatically "
        "recoverable.",
        "Units with BOTH heating and cooling duties: "
        + (", ".join(summary["mixed_duty_unit_ids"]) or "none"),
        "=== HEAT UTILITY DETAILS (including simultaneous heating/cooling) ===",
        f"{'Unit':<9}{'HU':>4}  {'Direction':<9} {'Duty kJ/h':>16}  "
        f"{'Agent':<18} Classification",
    ])
    for row in audit["utilities"]:
        lines.append(
            f"{row['unit_id']:<9}{row['utility_index']:>4}  "
            f"{row['direction']:<9} {row['duty_kJph']:>16,.3f}  "
            f"{str(row['agent_id'] or 'N/A')[:18]:<18} {row['classification']}"
        )
    if audit["warnings"]:
        lines.append("WARNINGS:")
        lines.extend("- " + note for note in audit["warnings"])
    return "\n".join(lines)


# ---------------------------------------------------------------------
# Steps 7.8B-7.8C: explicit temperature evidence and NON-CREDITABLE
# heat-recovery screening.  This section does not modify the flowsheet.
# ---------------------------------------------------------------------

@dataclass(frozen=True)
class HeatInterval:
    """A user-supported piece of a T-Q profile (kJ/h, K).

    Sensible: hot high->low, cold low->high.  Isothermal/latent:
    T_start_K == T_end_K.  Such a pulse enters the shifted temperature
    cascade at exactly that point; latent heat is NOT spread over a
    fictitious temperature span.

    A valid heat interval is a process-side enthalpy interval, not a
    utility-agent temperature profile or an arbitrary split of total duty.
    """
    unit_id: str
    kind: str
    T_start_K: float
    T_end_K: float
    duty_kJph: float
    description: str = ""
    provenance: str = "user_verified"


def _checked_heat_interval(seg: HeatInterval) -> None:
    if not isinstance(seg, HeatInterval):
        raise TypeError("All intervals must be HeatInterval instances.")
    if seg.kind not in ("hot", "cold"):
        raise ValueError(f"{seg.unit_id}: kind must be 'hot' or 'cold'.")
    if not str(seg.unit_id).strip():
        raise ValueError("Heat intervals require an identifying unit_id.")
    for v in (seg.T_start_K, seg.T_end_K, seg.duty_kJph):
        if not math.isfinite(float(v)):
            raise ValueError(f"{seg.unit_id}: temperature and duty must be finite.")
    if min(seg.T_start_K, seg.T_end_K) <= 0.0 or seg.duty_kJph < 0.0:
        raise ValueError(f"{seg.unit_id}: physical temperatures and duty required.")
    if seg.kind == "hot" and seg.T_start_K < seg.T_end_K:
        raise ValueError(f"{seg.unit_id}: hot sensible interval must cool.")
    if seg.kind == "cold" and seg.T_start_K > seg.T_end_K:
        raise ValueError(f"{seg.unit_id}: cold sensible interval must heat.")


def calculate_temperature_cascade(intervals: Iterable[HeatInterval],
                                  delta_T_min_K: float = 10.0) -> dict:
    """Pinch heat cascade for *specified* piecewise constant-Cp/isothermal T-Q.

    This is an ideal thermodynamic target for the INCLUDED pieces, not
    exchanger-network design, equipment saving, or a process model credit.
    It permits partial heat recovery and handles isothermal latent pulses.
    Hot temperatures shift DOWN by delta_T_min/2; cold temperatures UP by
    delta_T_min/2. Integrating from high to low yields minimum hot utility.
    See standard problem-table cascade methodology; no UA/pressure checks.
    """
    delta = float(delta_T_min_K)
    if not math.isfinite(delta) or delta < 0:
        raise ValueError("delta_T_min_K must be finite and nonnegative.")
    segments = tuple(intervals)
    for s in segments:
        _checked_heat_interval(s)
    total_hot = sum(s.duty_kJph for s in segments if s.kind == "hot")
    total_cold = sum(s.duty_kJph for s in segments if s.kind == "cold")
    if not segments:
        return dict(delta_T_min_K=delta, hot_kJph=0., cold_kJph=0.,
                    ideal_recovery_kJph=0., minimum_hot_utility_kJph=0.,
                    minimum_cold_utility_kJph=0., temperature_nodes=[],
                    energy_closure_kJph=0.)

    shifted = []
    levels = set()
    for s in segments:
        offset = -delta / 2 if s.kind == "hot" else delta / 2
        high = max(s.T_start_K, s.T_end_K) + offset
        low = min(s.T_start_K, s.T_end_K) + offset
        if high <= 0 or low <= 0:
            raise ValueError("Shifted temperature must be >0 K.")
        shifted.append((s, high, low))
        levels.update((high, low))
    levels = sorted(levels, reverse=True)

    cumulative = 0.0
    minimum_cumulative = 0.0
    nodes = []
    for i, high in enumerate(levels):
        # Fixed-temperature enthalpy release/requirement is a node pulse.
        pulse = sum((1.0 if s.kind == "hot" else -1.0) * s.duty_kJph
                    for s, top, bottom in shifted
                    if top == bottom == high)
        cumulative += pulse
        minimum_cumulative = min(minimum_cumulative, cumulative)
        row = dict(shifted_temperature_K=high, pulse_net_kJph=pulse,
                   interval_net_kJph=0.0, cascade_net_kJph=cumulative)
        if i + 1 < len(levels):
            low = levels[i+1]
            net = 0.0
            for s, top, bottom in shifted:
                if top > bottom and top >= high and bottom <= low:
                    frac = (high - low) / (top - bottom)
                    net += (1.0 if s.kind == "hot" else -1.0) * s.duty_kJph * frac
            cumulative += net
            minimum_cumulative = min(minimum_cumulative, cumulative)
            row["interval_net_kJph"] = net
            row["cascade_net_kJph"] = cumulative
        nodes.append(row)

    minimum_hot = max(-minimum_cumulative, 0.0)
    recovered = max(0.0, min(total_hot, total_cold, total_cold - minimum_hot))
    minimum_cold = max(total_hot - recovered, 0.0)
    closure = abs((total_hot - total_cold) - cumulative)
    if closure > 1e-6 * max(total_hot, total_cold, 1.):
        raise RuntimeError(f"Temperature cascade fails energy closure: {closure} kJ/h")
    return dict(delta_T_min_K=delta, hot_kJph=total_hot, cold_kJph=total_cold,
                ideal_recovery_kJph=recovered,
                minimum_hot_utility_kJph=total_cold - recovered,
                minimum_cold_utility_kJph=minimum_cold,
                temperature_nodes=nodes, energy_closure_kJph=closure)


def get_att_temperature_audit(sys) -> list[dict]:
    """Unit-specific operating conditions vs. *validated* process T-Q curves.

    Unit target temperatures are useful but do not establish energy-vs-T.
    Boiler duty, phase equilibrium and equipment constraints must be
    addressed independently before treating any whole-unit duty as a curve.
    """
    u = _units_of(sys)

    def temperature(obj):
        if obj is None:
            return None
        try:
            value = float(obj)
        except (TypeError, ValueError):
            return None
        return value if math.isfinite(value) and value > 0 else None

    def temperatures(streams):
        return [temperature(getattr(s, "T", None)) for s in streams]

    definitions = [
        ("U3HX", "VLE_TQ_AVAILABLE", "gas/steam condensation; see get_att_pinch_targets"),
        ("RC1", "SENSIBLE_PROFILE_APPROXIMATE", "hot residue; constant Cp may screen only"),
        ("D0", "DRYING_PROFILE_MISSING", "multi-stream dryer with evaporation and exhaust"),
        ("U2", "FIRED_REACTOR_NOT_INTEGRATED", "caustic slurry feed; duty includes reaction enthalpy"),
        ("C1", "NO_POSITIVE_UTILITY", "reaction plus mixing; check reaction heat treatment"),
        ("EC1", "ISOTHERMAL_BOILING_ELECTROLYTE_MODEL", "single-effect evaporator with condenser"),
        ("U3D", "PROVISIONAL_NATIVE_GAS_DRYER", "ethanol-service correlation; do not extrapolate"),
        ("U3K", "COMPRESSOR_COOLING_NOT_APPROVED", "compressor intercooling is not a process hot stream"),
    ]
    results = []
    for ID, status, explanation in definitions:
        equipment = getattr(u, ID, None)
        if equipment is None:
            continue
        tin = temperatures(getattr(equipment, "ins", ()))
        tout = temperatures(getattr(equipment, "outs", ()))
        target = temperature(getattr(equipment, "target_temperature_K", None))
        if target is None:
            target = temperature(getattr(equipment, "T", None))
        if ID == "EC1":
            # Actual simulated concentrate temperature, NOT heating-utility-agent T.
            target = tout[0] if tout else None
        if ID == "C1":
            q = _positive_heat_utility_kJph(equipment)
            status = "RECORDED_HEATING_NEEDS_TQ" if q > 0 else "NO_RECORDED_HEATING_UTILITY"
        results.append(dict(unit_id=ID, process_inlet_temperatures_K=tin,
                            process_outlet_temperatures_K=tout,
                            configured_target_K=target,
                            status=status, caveat=explanation))
    return results


def get_att_heat_recovery_assessment(sys, delta_T_min_K: float = 10.0,
                                     *, assume_isothermal_d0_ec1: bool = False,
                                     additional_segments: Iterable[HeatInterval] = ()) -> dict:
    """Generate conservative inventory and OPTIONAL hypothetical HEN target.

    In all cases the credited recovery is ZERO because no HEN units are
    installed in the process flowsheet.  The user may explicitly choose
    a screening scenario:
    - RC1 residue cooling is treated as constant Cp between its actual T's.
    - D0 dryer / EC1 evaporator demands are treated as isothermal at their
      simulated target temperatures. This is a modeling assumption, not a
      rigorous evaporator/dryer duty profile.
    - U3HX condensing stream is excluded unless phase-resolved user-verified
      HeatInterval segments are supplied. U2 and U3D similarly excluded by
      default; user supplied segments can be screened with coverage checks.
    """
    audit = get_heat_utility_audit(sys)
    total = audit["summary"]
    unit_rows = {r["unit_id"]: r for r in audit["units"]}
    temperature_evidence = get_att_temperature_audit(sys)
    intervals = []
    caveats = [
        "No exchanger network has been installed or re-simulated; credited heat recovery is zero.",
        "Phase-resolved U3HX/RC1/EC1 T-Q targets: see get_att_pinch_targets.",
        "EC1 negative utility is a condenser obligation, not an additional free hot stream.",
        "U3D native molecular sieve and U3K compressor cooling remain provisional/excluded.",
        "U2 (fired reactor with a caustic slurry feed; duty includes reaction enthalpy) is not heat-integrated.",
    ]
    u = _units_of(sys)
    # Audited heat utilities may be incomplete for custom units.  The
    # CausticizationReactor implementation computes an energy requirement in
    # _design(), but may not register a corresponding HeatUtility object.
    # Detect it; NEVER silently turn it into a modeled external-utility load.
    unregistered = []
    c1 = getattr(u, "C1", None)
    if c1 is not None:
        custom_q = getattr(c1, "_utility_heat_duty_kJph", None)
        if custom_q is not None:
            custom_q = float(custom_q)
            if not math.isfinite(custom_q):
                raise ValueError("Non-finite calculated C1 custom-unit heat duty")
            accounted_q = (unit_rows.get("C1", {}).get("heating_kJph", 0.0)
                           - unit_rows.get("C1", {}).get("cooling_kJph", 0.0))
            missing_q = custom_q - accounted_q
            if abs(missing_q) > max(1e-5, 1e-6 * abs(custom_q)):
                unregistered.append(dict(unit_id="C1",
                                         calculated_net_kJph=custom_q,
                                         recorded_net_kJph=accounted_q,
                                         difference_kJph=missing_q))
                caveats.append("C1 CUSTOM REACTOR INCOMPLETE: it calculates "
                               f"{custom_q:.6g} kJ/h but audit records "
                               f"{accounted_q:.6g} kJ/h; resolve before final utility totals.")
    rc1 = getattr(u, "RC1", None)
    if rc1 is not None and len(rc1.ins) == len(rc1.outs) == 1:
        t_hot = _stream_temperature(rc1.ins[0])
        t_cold = _stream_temperature(rc1.outs[0])
        q = _process_enthalpy_drop_kJph(rc1)
        if t_hot is not None and t_cold is not None and t_hot > t_cold and q > 0:
            intervals.append(HeatInterval("RC1", "hot", t_hot, t_cold, q,
                "constant-Cp residue cooling approximation", "model_Q_assumed_Cp"))
            caveats.append("RC1 duty is model-derived; constant-Cp temperature distribution is approximate.")

    if assume_isothermal_d0_ec1:
        for ID in ("D0", "EC1"):
            eq = getattr(u, ID, None)
            if eq is None:
                continue
            if ID == "D0":
                t = getattr(eq, "T", None)
            else:
                t = eq.outs[0].T if getattr(eq, "outs", ()) else None
            try:
                t = float(t)
            except (TypeError, ValueError):
                t = None
            q = unit_rows.get(ID, {}).get("heating_kJph", 0.)
            if t is not None and math.isfinite(t) and t > 0 and q > 0:
                intervals.append(HeatInterval(ID, "cold", t, t, q,
                    "assumed isothermal duty (NOT phase-resolved)",
                    "explicit_scenario_assumption"))
            else:
                caveats.append(f"{ID}: missing actual target T or heating duty; skipped.")
        caveats.append("D0 and EC1 heating lumps at model target T are an explicit screening approximation.")

    extras = tuple(additional_segments)
    intervals.extend(extras)
    # An interval may split one real process duty, but may never create heat
    # from outside the equipment's *recorded* aggregate heat utilities.
    grouped = {}
    for s in intervals:
        _checked_heat_interval(s)
        grouped[(s.unit_id, s.kind)] = grouped.get((s.unit_id, s.kind), 0.) + s.duty_kJph
    for (ID, kind), q in grouped.items():
        row = unit_rows.get(ID)
        if row is None:
            raise ValueError(f"{ID}: not a top-level system unit in the heat audit.")
        cap = row["cooling_kJph" if kind == "hot" else "heating_kJph"]
        tolerance = max(1e-5, 1e-6 * cap)
        if q > cap + tolerance:
            raise ValueError(f"{ID}: T-Q interval sum {q} exceeds audited {kind} duty {cap}.")
    target = calculate_temperature_cascade(intervals, delta_T_min_K)
    q_max = min(total["total_heating_kJph"], total["total_cooling_kJph"])
    gross_explicit = total["explicit_hot_candidate_cooling_kJph"]
    return dict(
        dry_feed_basis="1 kg dry Sargassum/h if create_att_system(dry_sargassum_kgph=1.0)",
        model_heating_kJph=total["total_heating_kJph"],
        model_cooling_kJph=total["total_cooling_kJph"],
        previously_screened_hot_candidate_kJph=gross_explicit,
        arithmetic_hot_cold_upper_bound_kJph=min(q_max, gross_explicit),
        selected_segments=list(intervals),
        selected_temperature_cascade=target,
        conditional_ideal_recovery_kJph=target["ideal_recovery_kJph"],
        credited_recovery_kJph=0.0,
        credited_external_heating_kJph=total["total_heating_kJph"],
        credited_external_cooling_kJph=total["total_cooling_kJph"],
        status="SCREENING_ONLY_NO_HEN_IMPLEMENTED",
        isothermal_screening_enabled=bool(assume_isothermal_d0_ec1),
        temperature_audit=temperature_evidence, caveats=caveats,
        unregistered_custom_thermal_duties=unregistered,
        recorded_heating_may_be_incomplete=any(x["difference_kJph"] > 0 for x in unregistered),
        recorded_cooling_may_be_incomplete=any(x["difference_kJph"] < 0 for x in unregistered),
    )


def _tq_intervals(unit_id, kind, stream, T_from, T_to, n, *, vle, provenance):
    """Split a stream's heating/cooling between two temperatures into n
    intervals from actual ThermoSTEAM enthalpies (with VLE if requested)."""
    s = stream.copy()
    temperatures = [T_from + (T_to - T_from) * i / n for i in range(n + 1)]
    enthalpies = []
    for T in temperatures:
        if vle:
            s.vle(T=T, P=s.P)
        else:
            s.T = T
        enthalpies.append(float(s.H))
    intervals = []
    for i in range(n):
        q = abs(enthalpies[i + 1] - enthalpies[i])
        if q > 0.0:
            intervals.append(HeatInterval(
                unit_id, kind, temperatures[i], temperatures[i + 1], q,
                f"{unit_id} {temperatures[i]:.1f}->{temperatures[i+1]:.1f} K",
                provenance))
    return intervals


def _c1_liquor_heating_kJph(u) -> float:
    """Sensible heating of the C1 carbonate liquor (F1 filtrate) from its
    inlet to the reactor temperature: the only C1 duty that an external
    preheater can supply. Capped at the C1 process duty."""
    liquor = u.C1.ins[0].copy()
    H_in = float(liquor.H)
    liquor.T = float(u.C1.target_temperature_K)
    return max(0.0, min(float(liquor.H) - H_in, float(u.C1._heat_duty_kJph)))


def _process_side_duties(u) -> dict:
    """
    Heat [kJ/h] that the process streams of the integrable units can absorb
    (cold) or release (hot), read from process-side results rather than
    heat utilities, which the optional heat-recovery scenario rescales.
    Heat losses are NOT included: a recovered stream can only replace
    process heat, never a unit's heat-loss allowance.
    """
    return {
        ("EC1", "cold"): max(float(u.EC1._heat_duty_kJph), 0.0),
        ("EC1", "hot"): max(-float(u.EC1._condenser_duty_kJph), 0.0),
        ("D0", "cold"): _positive_heat_utility_kJph(u.D0),
        ("C1", "cold"): _c1_liquor_heating_kJph(u),
        ("U3HX", "hot"): max(float(u.U3HX.ins[0].H - u.U3HX.outs[0].H), 0.0),
        ("RC1", "hot"): max(float(u.RC1.ins[0].H - u.RC1.outs[0].H), 0.0),
    }


def _baseline_heating_utilities(u) -> dict:
    """Unintegrated heating utility [kJ/h] = process duty + heat loss."""
    return {
        "EC1": max(float(u.EC1._utility_heat_duty_kJph), 0.0),
        "C1": max(float(u.C1._utility_heat_duty_kJph), 0.0),
        "D0": _positive_heat_utility_kJph(u.D0),
    }


def _dryer_option(dryer):
    if dryer is None:
        return None
    options = _hen_settings()["dryer_heat_acceptance"]
    if dryer not in options:
        raise ValueError(f"Unknown dryer option {dryer!r}; choose None or one of {tuple(options)}.")
    return options[dryer]


def get_att_process_heat_intervals(sys, n_intervals: int = 90,
                                   dryer: Optional[str] = None) -> list[HeatInterval]:
    """
    Phase-resolved process T-Q intervals of the simulated ATT flowsheet.

    Hot:  U3HX product gas cooling with steam condensation (ThermoSTEAM VLE),
          RC1 residue cooling (temperature-dependent Cp),
          EC1 vapor desuperheating and condensation (electrolyte model).
    Cold: EC1 boiling (isothermal at the evaporator temperature, electrolyte
          model), C1 heating (assumed linear from feed to reactor temperature)
          and, only for a ``dryer`` option from att.yaml, D0 drying. With
          ``dryer=None`` (baseline DrumDryer) D0 is not integrated, because
          its heat-acceptance temperature is not defined by the model.
    Cold duties include the units' heat-loss factors.

    Excluded: U2 (fired 500 C reactor fed with a caustic biomass slurry),
    U3D and U3K (provisional native correlations, small duties).
    """
    u = _units_of(sys)
    duties = _process_side_duties(u)
    d0 = _dryer_option(dryer)
    intervals = []
    # Use the U3HX set point, not outs[0].T: U3C (Flash) design re-equilibrates
    # that shared stream at constant H and can leave a non-physical T/phase
    # split (same enthalpy, so the U3HX duty is unaffected).
    gas_in = u.U3HX.ins[0]
    intervals += _tq_intervals("U3HX", "hot", gas_in, float(gas_in.T), float(u.U3HX.T),
                               n_intervals, vle=True, provenance="thermosteam_vle")
    res_in, res_out = u.RC1.ins[0], u.RC1.outs[0]
    intervals += _tq_intervals("RC1", "hot", res_in, float(res_in.T), float(res_out.T),
                               max(n_intervals // 3, 1), vle=False,
                               provenance="thermosteam_sensible")

    EC1 = u.EC1
    q_ec1 = duties[("EC1", "cold")]
    if q_ec1 > 0.0:
        intervals.append(HeatInterval("EC1", "cold", EC1.T, EC1.T, q_ec1,
            "single-effect boiling at the evaporator temperature",
            "electrolyte_model"))
    condenser = duties[("EC1", "hot")]
    if condenser > 0.0:
        T_c = float(EC1._condensation_temperature_K)
        Water = EC1.ins[0].chemicals["Water"]
        kmol = float(EC1.outs[1].imol["Water"])
        superheat = kmol * (Water.H("g", EC1.T) - Water.H("g", T_c))
        intervals.append(HeatInterval("EC1", "hot", EC1.T, T_c, superheat,
            "vapor desuperheating", "electrolyte_model"))
        intervals.append(HeatInterval("EC1", "hot", T_c, T_c, condenser - superheat,
            "vapor condensation", "electrolyte_model"))

    q_d0 = duties[("D0", "cold")]
    if d0 is not None and q_d0 > 0.0:
        intervals.append(HeatInterval("D0", "cold", d0["T_in_K"], d0["T_out_K"], q_d0,
            f"drying air heating ({dryer}); model thermal duty",
            "unverified_dryer_assumption"))
    q_c1 = duties[("C1", "cold")]
    if q_c1 > 0.0:
        # Actual liquor T-Q (ThermoSTEAM), truncated at the C1 process duty.
        liquor = u.C1.ins[0]
        cumulative = 0.0
        for s in _tq_intervals("C1", "cold", liquor, float(liquor.T),
                               float(u.C1.target_temperature_K), max(n_intervals // 3, 1),
                               vle=False, provenance="thermosteam_sensible"):
            q = min(s.duty_kJph, q_c1 - cumulative)
            if q <= 0.0:
                break
            T_end = s.T_start_K + (s.T_end_K - s.T_start_K) * q / s.duty_kJph
            intervals.append(HeatInterval("C1", "cold", s.T_start_K, T_end, q,
                "carbonate liquor preheating", s.provenance))
            cumulative += q
    return intervals


def get_att_pinch_targets(sys, delta_T_min_K: float = 10.0, n_intervals: int = 90,
                          dryer: Optional[str] = None) -> dict:
    """
    Minimum utility targets (problem table) for the phase-resolved process
    intervals of ``get_att_process_heat_intervals``. A target, not an
    installed exchanger network: no heat recovery is credited in the model.
    """
    intervals = get_att_process_heat_intervals(sys, n_intervals, dryer)
    cascade = calculate_temperature_cascade(intervals, delta_T_min_K)
    nodes = cascade["temperature_nodes"]
    pinch = min(nodes, key=lambda row: row["cascade_net_kJph"]) if nodes else None
    cold_units = sorted({s.unit_id for s in intervals if s.kind == "cold"})
    return dict(
        delta_T_min_K=float(delta_T_min_K),
        intervals=intervals,
        integrated_cold_units=cold_units,
        integrated_heating_now_kJph=cascade["cold_kJph"],
        integrated_hot_available_kJph=cascade["hot_kJph"],
        recoverable_kJph=cascade["ideal_recovery_kJph"],
        minimum_hot_utility_kJph=cascade["minimum_hot_utility_kJph"],
        minimum_cold_utility_kJph=cascade["minimum_cold_utility_kJph"],
        pinch_shifted_temperature_K=(
            pinch["shifted_temperature_K"]
            if pinch is not None and cascade["minimum_hot_utility_kJph"] > 0.0
            and cascade["ideal_recovery_kJph"] > 0.0 else None
        ),
        cascade=cascade,
    )


# ---------------------------------------------------------------------
# Heat-exchanger-network design (optimization scenarios; nothing credited)
# ---------------------------------------------------------------------
@dataclass
class _Curve:
    """Monotonic process T-Q curve. Hot: T falls as Q is released from the
    supply end. Cold: T rises as Q is absorbed from the inlet end."""
    name: str
    unit_id: str
    kind: str
    T: list
    Q: list

    @property
    def duty(self):
        return self.Q[-1]

    def T_at(self, q):
        q = min(max(q, 0.0), self.Q[-1])
        for i in range(1, len(self.Q)):
            if q <= self.Q[i] or i == len(self.Q) - 1:
                dq = self.Q[i] - self.Q[i - 1]
                f = 0.0 if dq <= 0.0 else (q - self.Q[i - 1]) / dq
                return self.T[i - 1] + f * (self.T[i] - self.T[i - 1])
        return self.T[-1]


def _curve_from_intervals(name, unit_id, kind, intervals):
    T, Q = [intervals[0].T_start_K], [0.0]
    for s in intervals:
        T.append(s.T_end_K)
        Q.append(Q[-1] + s.duty_kJph)
    return _Curve(name, unit_id, kind, T, Q)


def _hen_settings():
    from biorefineries.sabre.utils import load_assumptions
    return load_assumptions("att.yaml")["att"]["heat_recovery"]["heat_exchanger_network"]


def _max_countercurrent_duty(hot, q0, cold, c_top, approach, n=200):
    """Largest Q such that the hot curve from released q0 (its current
    top) and the cold curve below absorbed c_top (its current top) keep
    T_hot - T_cold >= approach everywhere in counter-current flow."""
    def feasible(Q):
        for i in range(n + 1):
            x = Q * i / n
            if hot.T_at(q0 + x) - cold.T_at(c_top - x) < approach - 1e-9:
                return False
        return True
    upper = min(hot.duty - q0, c_top)
    if upper <= 0.0 or not feasible(0.0):
        return 0.0
    if feasible(upper):
        return upper
    lo, hi = 0.0, upper
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if feasible(mid) else (lo, mid)
    return lo


def _max_preheat_duty(hot, q0, cold, c_bot, approach, n=200):
    """Largest Q for preheating a sensible cold curve from absorbed c_bot
    upward with the hot curve from released q0, counter-current."""
    def feasible(Q):
        for i in range(n + 1):
            x = Q * i / n
            if hot.T_at(q0 + x) - cold.T_at(c_bot + Q - x) < approach - 1e-9:
                return False
        return True
    upper = min(hot.duty - q0, cold.duty - c_bot)
    if upper <= 0.0 or not feasible(0.0):
        return 0.0
    if feasible(upper):
        return upper
    lo, hi = 0.0, upper
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if feasible(mid) else (lo, mid)
    return lo


def _area_m2(hot, q0, cold_T, Q, U_W_per_m2_K, n=200):
    """Exchanger area by integrating dQ/(U dT) along the match; cold_T(x)."""
    if Q <= 0.0:
        return 0.0
    area = 0.0
    for i in range(n):
        x = Q * (i + 0.5) / n
        dT = hot.T_at(q0 + x) - cold_T(x)
        area += (Q / n) * 1000.0 / 3600.0 / (U_W_per_m2_K * max(dT, 1e-6))
    return area


def design_att_heat_exchanger_network(sys, dryer: Optional[str] = None,
                                      delta_T_min_K: Optional[float] = None) -> dict:
    """
    Design and verify a heat-exchanger network for the simulated flowsheet.

    Hot sources: U2 product gas (U3HX, ThermoSTEAM VLE T-Q), ATT residue
    (RC1) and EC1 vapor (desuperheating + condensation). Cold sinks: EC1
    boiling, C1 liquor heating and, only for a ``dryer`` option from
    att.yaml, D0 drying (``None`` = baseline DrumDryer, not integrated).
    Isothermal sinks take the hottest remaining source; sensible sinks are
    preheated from the inlet with the coldest usable source. Every match is
    checked point by point in counter-current flow. Hot gas or solids
    feeding the evaporator, and hot solids feeding any sink, pass through an
    intermediate steam loop (one more approach temperature).

    Returns the verified matches and, per unit, the baseline duty, the
    recovered heat and the remaining external duty. The flowsheet and its
    heat utilities are not modified.
    """
    settings = _hen_settings()
    dT = float(settings["delta_T_min_K"] if delta_T_min_K is None else delta_T_min_K)
    loop_dT = float(settings["intermediate_loop_extra_approach_K"])
    U = settings["overall_U_W_per_m2_K"]
    d0 = _dryer_option(dryer)
    u = _units_of(sys)
    duties = _process_side_duties(u)
    intervals = get_att_process_heat_intervals(sys, dryer=dryer)

    def hot_curve(unit_id, name):
        segs = [s for s in intervals if s.unit_id == unit_id and s.kind == "hot"]
        return _curve_from_intervals(name, unit_id, "hot", segs)

    hots = [hot_curve("U3HX", "U2 product gas"), hot_curve("RC1", "ATT residue"),
            hot_curve("EC1", "EC1 vapor")]

    EC1 = u.EC1
    colds = [_Curve("EC1 boiling", "EC1", "cold", [EC1.T, EC1.T], [0.0, duties[("EC1", "cold")]])]
    c1_segments = [s for s in intervals if s.unit_id == "C1" and s.kind == "cold"]
    if c1_segments:
        colds.append(_curve_from_intervals("C1 liquor", "C1", "cold", c1_segments))
    if d0 is not None:
        colds.append(_Curve("D0 dryer", "D0", "cold", [d0["T_in_K"], d0["T_out_K"]],
                            [0.0, duties[("D0", "cold")]]))
    colds.sort(key=lambda c: c.T[-1], reverse=True)

    def needs_loop(hot, cold):
        return hot.unit_id == "RC1" or cold.unit_id == "EC1"

    def U_for(hot, cold, loop):
        if loop:
            return U["hot_solids"] if hot.unit_id == "RC1" else U["gas_sensible"]
        if hot.unit_id == "EC1":
            return U["condensing_vapor_to_air"] if cold.unit_id == "D0" else U["condensing_vapor_to_liquid"]
        return U["gas_condensing"] if hot.T_at(0) < 373.15 else U["gas_sensible"]

    # Isothermal sinks take the hottest remaining source. Sensible sinks are
    # preheated from their inlet with the coldest usable source first; the
    # unrecovered top of the sink is left to the external utility.
    released = {h.name: 0.0 for h in hots}
    absorbed = {c.name: 0.0 for c in colds}
    matches = []
    n = 200
    for cold in colds:
        sensible = cold.T[-1] > cold.T[0]
        order = sorted(hots, key=lambda h: h.T_at(released[h.name]), reverse=not sensible)
        for hot in order:
            if hot.unit_id == cold.unit_id:
                continue
            q0, c0 = released[hot.name], absorbed[cold.name]
            remaining = cold.duty - c0
            if remaining <= 1e-9 or hot.duty - q0 <= 1e-9:
                continue
            loop = needs_loop(hot, cold)
            if loop:
                # Medium raised isothermally loop_dT above the sink's outlet
                # temperature; the hot stream must stay dT above the medium.
                T_medium = cold.T[-1] + loop_dT
                medium = _Curve("loop", "loop", "cold", [T_medium, T_medium], [0.0, remaining])
                Q = _max_countercurrent_duty(hot, q0, medium, remaining, dT)
            elif sensible:
                Q = _max_preheat_duty(hot, q0, cold, c0, dT)
            else:
                Q = _max_countercurrent_duty(hot, q0, cold, cold.duty, dT)
                Q = min(Q, remaining)
            if Q <= 1e-6:
                continue
            if loop:
                approaches = [hot.T_at(q0 + Q * i / n) - T_medium for i in range(n + 1)]
                area = (_area_m2(hot, q0, lambda x: T_medium, Q, U_for(hot, cold, True))
                        + Q * 1000.0 / 3600.0 / (U["steam_to_boiling_liquor"] * loop_dT))
            else:
                cold_T = lambda x, c0=c0, Q=Q: cold.T_at(c0 + Q - x)
                approaches = [hot.T_at(q0 + Q * i / n) - cold_T(Q * i / n) for i in range(n + 1)]
                area = _area_m2(hot, q0, cold_T, Q, U_for(hot, cold, False))
            matches.append(dict(
                hot=hot.name, hot_unit=hot.unit_id, cold=cold.name, cold_unit=cold.unit_id,
                duty_kJph=Q,
                hot_T_in_K=hot.T_at(q0), hot_T_out_K=hot.T_at(q0 + Q),
                cold_T_in_K=cold.T_at(c0), cold_T_out_K=cold.T_at(c0 + Q),
                intermediate_loop=loop,
                loop_medium_T_K=T_medium if loop else None,
                # For loop matches: hot stream vs loop medium (the medium is a
                # further loop_dT above the sink).
                minimum_approach_K=min(approaches),
                required_approach_K=dT,
                area_m2_UNVERIFIED_U=area,
            ))
            released[hot.name] = q0 + Q
            absorbed[cold.name] = c0 + Q

    for m in matches:
        if m["minimum_approach_K"] < dT - 1e-6:
            raise RuntimeError(f"HEN match {m['hot']} -> {m['cold']} violates the approach temperature.")
        # Matches into D0 rest on an assumed dryer heat-acceptance profile.
        m["basis"] = ("unverified_dryer_assumption" if m["cold_unit"] == "D0"
                      else "temperature_verified")

    utilities = _baseline_heating_utilities(u)

    def unit_rows(units, kind):
        # Heating: baseline = unintegrated utility (process duty + heat loss);
        # recovery is bounded by the process-stream duty, so the heat-loss
        # allowance always stays with the external utility.
        rows = {}
        for ID in units:
            heating = kind == "heating"
            process = duties[(ID, "cold" if heating else "hot")]
            baseline = utilities[ID] if heating else process
            key = "cold_unit" if heating else "hot_unit"
            recovered = sum(m["duty_kJph"] for m in matches if m[key] == ID)
            if recovered > process + 1e-6:
                raise RuntimeError(f"HEN recovery {recovered} exceeds the {ID} process duty {process}.")
            rows[ID] = dict(baseline_kJph=baseline, process_stream_duty_kJph=process,
                            recovered_kJph=recovered,
                            remaining_external_kJph=baseline - recovered)
        return rows

    heating = unit_rows(("EC1", "D0", "C1"), "heating")
    cooling = unit_rows(("U3HX", "RC1", "EC1"), "cooling")
    recovered = sum(m["duty_kJph"] for m in matches)
    return dict(
        scenario_ec1_temperature_K=float(EC1.T),
        ec1_is_baseline_temperature=bool(getattr(EC1, "is_baseline_temperature", True)),
        dryer_option=dryer,
        dryer_option_status=(d0["status"] if d0 is not None
                             else "Baseline DrumDryer: not integrated (heat-acceptance temperature undefined)."),
        temperature_verified_recovery_kJph=sum(
            m["duty_kJph"] for m in matches if m["basis"] == "temperature_verified"),
        dryer_dependent_recovery_kJph=sum(
            m["duty_kJph"] for m in matches if m["basis"] == "unverified_dryer_assumption"),
        delta_T_min_K=dT,
        intermediate_loop_extra_approach_K=loop_dT,
        matches=matches,
        recovered_kJph=recovered,
        heating=heating,
        cooling=cooling,
        integrated_heating_baseline_kJph=sum(r["baseline_kJph"] for r in heating.values()),
        integrated_heating_remaining_kJph=sum(r["remaining_external_kJph"] for r in heating.values()),
        total_area_m2_UNVERIFIED_U=sum(m["area_m2_UNVERIFIED_U"] for m in matches),
        status="DESIGN_VERIFIED_NOT_CREDITED_IN_FLOWSHEET",
    )


def format_att_heat_exchanger_network(report: dict) -> str:
    """Plain-text summary of ``design_att_heat_exchanger_network``."""
    out = [f"=== HEN DESIGN | EC1 {report['scenario_ec1_temperature_K'] - 273.15:.0f} C "
           f"({'baseline' if report['ec1_is_baseline_temperature'] else 'SCENARIO'}) | "
           f"dryer: {report['dryer_option']} | dTmin {report['delta_T_min_K']:.0f} K "
           f"(+{report['intermediate_loop_extra_approach_K']:.0f} K via loop) ===",
           f"Dryer option status: {report['dryer_option_status']}"]
    for m in report["matches"]:
        loop = f" via loop at {m['loop_medium_T_K'] - 273.15:.1f} C" if m["intermediate_loop"] else ""
        tag = "" if m["basis"] == "temperature_verified" else "  [UNVERIFIED DRYER]"
        out.append(f"  {m['hot']:15s} {m['hot_T_in_K']-273.15:6.1f}->{m['hot_T_out_K']-273.15:6.1f} C  =>  "
                   f"{m['cold']:12s} {m['cold_T_in_K']-273.15:6.1f}->{m['cold_T_out_K']-273.15:6.1f} C : "
                   f"{m['duty_kJph']:8.1f} kJ/h, min approach {m['minimum_approach_K']:5.1f} K, "
                   f"area {m['area_m2_UNVERIFIED_U']:.3f} m2{loop}{tag}")
    for ID, r in report["heating"].items():
        out.append(f"  heating {ID:4s}: baseline {r['baseline_kJph']:8.1f}  recovered {r['recovered_kJph']:8.1f}  "
                   f"remaining {r['remaining_external_kJph']:8.1f} kJ/h")
    out.append(f"  D0+C1+EC1 external heating: {report['integrated_heating_baseline_kJph']:.1f} -> "
               f"{report['integrated_heating_remaining_kJph']:.1f} kJ/h (design, not credited)")
    out.append(f"  of which temperature-verified recovery {report['temperature_verified_recovery_kJph']:.1f}, "
               f"dryer-dependent (unverified) {report['dryer_dependent_recovery_kJph']:.1f} kJ/h")
    cooling = report["cooling"]
    out.append(f"  U3HX+RC1+EC1 external cooling: {sum(r['baseline_kJph'] for r in cooling.values()):.1f} -> "
               f"{sum(r['remaining_external_kJph'] for r in cooling.values()):.1f} kJ/h")
    return "\n".join(out)


def format_att_heat_recovery_assessment(report: dict) -> str:
    """Human-readable Step 7.8B/C temperature evidence and HEN target."""
    out = ["=== ATT HEAT INTEGRATION: BOUNDARIES AND SCREENING ===",
           "Heat utility signs: heating and cooling counted separately.",
           f"Heating (gross): {report['model_heating_kJph']:,.3f} kJ/h",
           f"Cooling (gross): {report['model_cooling_kJph']:,.3f} kJ/h",
           f"Identified U3HX+RC1 process-hot inventory: {report['previously_screened_hot_candidate_kJph']:,.3f} kJ/h",
           f"Arithmetic, NOT temperature-qualified bound: {report['arithmetic_hot_cold_upper_bound_kJph']:,.3f} kJ/h",
           "=== PROCESS TEMPERATURE EVIDENCE ==="]
    for row in report["temperature_audit"]:
        out.append(f"{row['unit_id']}: inlet={row['process_inlet_temperatures_K']} "
                   f"outlet={row['process_outlet_temperatures_K']} "
                   f"target={row['configured_target_K']} K; {row['status']}")
    out.append("=== OPTIONAL IDEAL HEAT CASCADE ===")
    out.append(f"Scenario uses approximate isothermal duties: {report['isothermal_screening_enabled']}")
    for seg in report["selected_segments"]:
        out.append(f"{seg.unit_id} {seg.kind} {seg.T_start_K:.2f} -> "
                   f"{seg.T_end_K:.2f} K, {seg.duty_kJph:.2f} kJ/h ({seg.provenance})")
    target = report["selected_temperature_cascade"]
    out.append(f"Conditional ideal (selected intervals only): {target['ideal_recovery_kJph']:,.3f} kJ/h")
    out.append(f"Actual implemented / TEA-LCA credited recovery: {report['credited_recovery_kJph']:,.3f} kJ/h")
    out.append(f"Current baseline external heating: {report['credited_external_heating_kJph']:,.3f} kJ/h")
    out.append(f"Current baseline external cooling: {report['credited_external_cooling_kJph']:,.3f} kJ/h")
    if report["unregistered_custom_thermal_duties"]:
        out.append("=== WARNING: CUSTOM UNIT THERMAL DUTY NOT REGISTERED ===")
        for row in report["unregistered_custom_thermal_duties"]:
            out.append(f"{row['unit_id']}: calculated {row['calculated_net_kJph']:.3f}, "
                       f"heat utility recorded {row['recorded_net_kJph']:.3f}, "
                       f"difference {row['difference_kJph']:.3f} kJ/h")
    out.append("=== LIMITATIONS AND NEXT ENGINEERING VALIDATION ===")
    out.extend("- " + s for s in report["caveats"])
    return "\n".join(out)
