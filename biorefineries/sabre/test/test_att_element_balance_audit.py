
from biorefineries.sabre.systems._att_system import create_att_system


ABS_TOL_KMOL_ATOM_PH = 1e-10
REL_TOL = 1e-8


def _mass(stream):
    return float(stream.F_mass)


def _stream_id(stream):
    return stream.ID if stream.ID else "<unnamed>"


def get_system_boundary_streams(sys):
    """Return fresh-feed streams and final product/waste streams."""
    units = set(sys.units)

    fresh_feeds = []
    final_outputs = []

    seen = set()
    for unit in sys.units:
        for stream in unit.ins:
            key = id(stream)
            if key in seen:
                continue
            if stream.source not in units:
                fresh_feeds.append(stream)
                seen.add(key)

    seen = set()
    for unit in sys.units:
        for stream in unit.outs:
            key = id(stream)
            if key in seen:
                continue
            if stream.sink not in units:
                final_outputs.append(stream)
                seen.add(key)

    return fresh_feeds, final_outputs


def _atomic_flow(stream, atom):
    """
    Return atomic flow [kmol atom/h].

    If ThermoSTEAM cannot evaluate the element because one or more
    pseudocomponents lack a usable formula, return None instead of
    fabricating a value.
    """
    try:
        return float(stream.get_atomic_flow(atom))
    except Exception:
        return None


def element_balance_audit(sys):
    fresh_feeds, final_outputs = get_system_boundary_streams(sys)

    print("\n=== SYSTEM-BOUNDARY ELEMENT BALANCE AUDIT ===")
    print(
        "Na and Ca are treated as the primary rigorous checks for the "
        "current alkali/causticization loop."
    )
    print(
        "C, H, O, and S are diagnostic only because U2 uses empirical "
        "gas yields and some Sargassum pseudocomponents are simplified."
    )

    atoms = ("Na", "Ca", "C", "H", "O", "S")
    results = {}

    for atom in atoms:
        feed_terms = []
        output_terms = []

        fully_auditable = True

        for stream in fresh_feeds:
            value = _atomic_flow(stream, atom)
            if value is None:
                fully_auditable = False
                break
            feed_terms.append((_stream_id(stream), value))

        if fully_auditable:
            for stream in final_outputs:
                value = _atomic_flow(stream, atom)
                if value is None:
                    fully_auditable = False
                    break
                output_terms.append((_stream_id(stream), value))

        print(f"\n--- {atom} ---")

        if not fully_auditable:
            print(
                "Not fully auditable with the current chemical definitions."
            )
            results[atom] = {
                "status": "NOT_FULLY_AUDITABLE",
            }
            continue

        total_in = sum(v for _, v in feed_terms)
        total_out = sum(v for _, v in output_terms)

        difference = total_in - total_out
        abs_difference = abs(difference)

        if abs(total_in) > 1e-30:
            relative_error = abs_difference / abs(total_in)
        else:
            relative_error = abs_difference

        print("Fresh-feed contributions:")
        for name, value in feed_terms:
            if abs(value) > 1e-14:
                print(
                    f"  {name:30s}"
                    f"{value: .12e} kmol-atom/h"
                )

        print("Final-output contributions:")
        for name, value in output_terms:
            if abs(value) > 1e-14:
                print(
                    f"  {name:30s}"
                    f"{value: .12e} kmol-atom/h"
                )

        print(f"Total {atom} input       : {total_in:.12e} kmol-atom/h")
        print(f"Total {atom} output      : {total_out:.12e} kmol-atom/h")
        print(f"Input - output           : {difference:.12e} kmol-atom/h")
        print(f"Absolute difference      : {abs_difference:.12e} kmol-atom/h")
        print(f"Relative error           : {relative_error:.12e}")

        status = "DIAGNOSTIC"

        # Only Na and Ca are asserted as rigorous at this stage.
        if atom in ("Na", "Ca"):
            tolerance = max(
                ABS_TOL_KMOL_ATOM_PH,
                REL_TOL * max(abs(total_in), 1.0),
            )
            passed = abs_difference <= tolerance
            status = "PASS" if passed else "FAIL"
            print(f"Tolerance                : {tolerance:.12e} kmol-atom/h")
            print(f"Status                   : {status}")

            if not passed:
                raise AssertionError(
                    f"{atom} element balance failed: "
                    f"input={total_in}, output={total_out}, "
                    f"difference={difference}, "
                    f"relative_error={relative_error}"
                )
        else:
            print("Status                   : DIAGNOSTIC ONLY")

        results[atom] = {
            "input_kmol_atom_ph": total_in,
            "output_kmol_atom_ph": total_out,
            "difference_kmol_atom_ph": difference,
            "absolute_difference_kmol_atom_ph": abs_difference,
            "relative_error": relative_error,
            "status": status,
        }

    print("\n=== ELEMENT AUDIT SUMMARY ===")
    print("Na:", results["Na"]["status"])
    print("Ca:", results["Ca"]["status"])
    print(
        "C/H/O/S are reported for diagnosis only and should not be "
        "interpreted as rigorous reaction-network closure yet."
    )

    return results


sys = create_att_system(
    dry_sargassum_kgph=1.0
)

sys.set_tolerance(
    mol=1e-9,
    rmol=1e-9,
    T=1e-5,
    rT=1e-5,
    maxiter=200,
    method="fixedpoint",
)

# Element-balance audit only; do not run design/costing.
sys.simulate(
    design_and_cost=False
)

print(
    "Simulation completed "
    "(design/cost disabled for element audit)."
)
print(
    "Units:",
    [unit.ID for unit in sys.units],
)

element_balance_audit(sys)
