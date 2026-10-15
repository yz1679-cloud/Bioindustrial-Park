
from biorefineries.sabre.systems._att_system import create_att_system


ABS_TOL_KGPH = 1e-8
REL_TOL = 1e-8


def _mass(stream):
    return float(stream.F_mass)


def _stream_id(stream):
    return stream.ID if stream.ID else "<unnamed>"


def get_system_boundary_streams(sys):
    """
    Identify material streams crossing the boundary of the current ATT system.

    Fresh feeds:
        Streams entering a system unit whose source is not another unit
        in this system.

    Final products / wastes:
        Streams leaving a system unit whose sink is not another unit
        in this system.

    Internal recycle streams are therefore excluded automatically.
    """
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


def system_boundary_mass_audit(sys):
    fresh_feeds, final_outputs = get_system_boundary_streams(sys)

    print("\n=== SYSTEM-BOUNDARY TOTAL MASS BALANCE AUDIT ===")

    print("\n--- FRESH FEEDS ---")
    for stream in fresh_feeds:
        print(
            f"{_stream_id(stream):35s}"
            f"{_mass(stream):>18.9f} kg/h"
        )

    print("\n--- FINAL PRODUCTS / WASTES ---")
    for stream in final_outputs:
        print(
            f"{_stream_id(stream):35s}"
            f"{_mass(stream):>18.9f} kg/h"
        )

    total_in = sum(_mass(s) for s in fresh_feeds)
    total_out = sum(_mass(s) for s in final_outputs)

    difference = total_in - total_out
    abs_difference = abs(difference)

    if abs(total_in) > 1e-30:
        relative_error = abs_difference / abs(total_in)
    else:
        relative_error = abs_difference

    tolerance = max(
        ABS_TOL_KGPH,
        REL_TOL * max(abs(total_in), 1.0),
    )

    passed = abs_difference <= tolerance

    print("\n=== BOUNDARY MASS BALANCE SUMMARY ===")
    print(f"Total fresh-feed input : {total_in:.12f} kg/h")
    print(f"Total final output     : {total_out:.12f} kg/h")
    print(f"Input - output         : {difference:.12e} kg/h")
    print(f"Absolute difference    : {abs_difference:.12e} kg/h")
    print(f"Relative error         : {relative_error:.12e}")
    print(f"Tolerance              : {tolerance:.12e} kg/h")
    print(f"Status                 : {'PASS' if passed else 'FAIL'}")

    if not passed:
        raise AssertionError(
            "System-boundary mass balance failed: "
            f"input={total_in}, output={total_out}, "
            f"difference={difference}, "
            f"relative_error={relative_error}"
        )

    return {
        "fresh_feeds": fresh_feeds,
        "final_outputs": final_outputs,
        "total_input_kgph": total_in,
        "total_output_kgph": total_out,
        "difference_kgph": difference,
        "absolute_difference_kgph": abs_difference,
        "relative_error": relative_error,
        "status": "PASS",
    }


# ----------------------------------------------------------
# Run current ATT baseline
# ----------------------------------------------------------

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

sys.simulate()

print("Simulation completed.")
print("Units:", [unit.ID for unit in sys.units])

system_boundary_mass_audit(sys)
