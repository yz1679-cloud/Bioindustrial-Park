
from biorefineries.sabre.systems._att_system import create_att_system


ABS_TOL_KGPH = 1e-8
REL_TOL = 1e-8


def unit_mass_balance_audit(sys):
    """
    Audit total mass balance for every unit in the ATT system.

    Prints, for each unit:
        - total inlet mass flow [kg/h]
        - total outlet mass flow [kg/h]
        - mass difference = inlet - outlet [kg/h]
        - relative error = |difference| / inlet

    Notes
    -----
    Internal recycle streams are handled automatically because the audit
    is performed unit-by-unit after system convergence.
    """

    print("\n=== UNIT-BY-UNIT TOTAL MASS BALANCE AUDIT ===")

    results = []
    failed = []

    for unit in sys.units:

        mass_in = sum(
            float(stream.F_mass)
            for stream in unit.ins
        )

        mass_out = sum(
            float(stream.F_mass)
            for stream in unit.outs
        )

        delta = mass_in - mass_out

        if abs(mass_in) > 1e-30:
            rel_error = abs(delta) / abs(mass_in)
        else:
            rel_error = abs(delta)

        passed = (
            abs(delta)
            <= max(
                ABS_TOL_KGPH,
                REL_TOL * max(abs(mass_in), 1.0),
            )
        )

        results.append(
            (
                unit.ID,
                type(unit).__name__,
                mass_in,
                mass_out,
                delta,
                rel_error,
                passed,
            )
        )

        if not passed:
            failed.append(results[-1])

    # Header
    print(
        f"{'Unit':<8}"
        f"{'Type':<28}"
        f"{'Mass in (kg/h)':>18}"
        f"{'Mass out (kg/h)':>19}"
        f"{'Delta (kg/h)':>17}"
        f"{'Relative error':>18}"
        f"{'Status':>10}"
    )
    print("-" * 118)

    # Rows
    for (
        unit_id,
        unit_type,
        mass_in,
        mass_out,
        delta,
        rel_error,
        passed,
    ) in results:

        print(
            f"{unit_id:<8}"
            f"{unit_type:<28}"
            f"{mass_in:>18.9f}"
            f"{mass_out:>19.9f}"
            f"{delta:>17.3e}"
            f"{rel_error:>18.3e}"
            f"{'PASS' if passed else 'FAIL':>10}"
        )

    # Summary
    worst = max(
        results,
        key=lambda x: abs(x[4]),
    )

    print("\n=== AUDIT SUMMARY ===")
    print(
        "Units checked:",
        len(results),
    )
    print(
        "Worst absolute mass difference:",
        worst[0],
        "=",
        worst[4],
        "kg/h",
    )
    print(
        "Worst relative error:",
        worst[0],
        "=",
        worst[5],
    )

    if failed:
        print("\nFAILED UNITS:")
        for row in failed:
            print(
                f"  {row[0]} "
                f"({row[1]}): "
                f"delta={row[4]:.6e} kg/h, "
                f"rel={row[5]:.6e}"
            )

        raise AssertionError(
            f"{len(failed)} unit(s) failed the total-mass audit."
        )

    print("\nAll unit total mass balances passed.")

    return results


# ----------------------------------------------------------
# Run the current ATT baseline
# ----------------------------------------------------------

sys = create_att_system(
    dry_sargassum_kgph=1.0
)

# Keep the seeded recycle and fixed-point solver used by the
# validated Step 7.4-7.6 baseline. The recycle tolerance must be tighter
# than the audit tolerance, because M1 reads the tear stream of the
# previous iteration.
sys.set_tolerance(
    mol=1e-11,
    rmol=1e-11,
    T=1e-5,
    rT=1e-5,
    maxiter=200,
    method="fixedpoint",
)

sys.simulate()

print("Simulation completed.")
print(
    "Units:",
    [unit.ID for unit in sys.units],
)

unit_mass_balance_audit(sys)
