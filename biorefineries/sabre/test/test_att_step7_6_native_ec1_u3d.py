from biorefineries.sabre.systems._att_system import create_att_system
from biorefineries.sabre.analyses.att.mass_energy import (
    get_att_recycle_summary,
    get_att_u3_summary,
    get_att_energy_summary,
)


sys = create_att_system(dry_sargassum_kgph=1.0)
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

recycle = get_att_recycle_summary(sys)
u3 = get_att_u3_summary(sys)
energy = get_att_energy_summary(sys)

print("\n=== STEP 7.6 NATIVE EC1 CHECK ===")
for key in (
    "EC1_unit_type",
    "EC1_effect_count",
    "EC1_operating_pressure_Pa",
    "EC1_Na2CO3_crystals_kgph",
    "SP1_recovered_NaOH_kgph",
    "fresh_NaOH_kgph",
    "EC1_recycle_NaOH_wt_frac_NaOH_water_basis",
    "EC1_removed_water_kgph",
    "U2_feed_NaOH_kgph",
    "U2_feed_Na2CO3_kgph",
    "U2_feed_water_kgph",
):
    print(f"{key}: {recycle[key]}")

print(
    "EC1_positive_heat_utility_kJph:",
    energy["EC1_utility_heat_kJph"],
)
print("EC1_added_heat_loss_kJph:", energy["EC1_heat_loss_kJph"])

print("\n=== STEP 7.6 NATIVE U3D CHECK ===")
for key in (
    "U3D_unit_type",
    "U3D_dry_gas_total_kgph",
    "U3D_dry_gas_water_kgph",
    "U3D_removed_water_kgph",
    "U3D_power_kW",
    "U3D_heating_duty_kJph",
    "U3D_cooling_duty_kJph",
    "U3P_actual_H2_recovery",
    "U3K_H2_product_total_kgph",
):
    print(f"{key}: {u3[key]}")

# Equipment checks.
assert recycle["EC1_unit_type"] == "NaOHEvaporator"
assert recycle["EC1_effect_count"] == 1
# Electrolyte boiling pressure, far below pure-water Psat(90 C) = 70.2 kPa.
assert 10e3 < recycle["EC1_operating_pressure_Pa"] < 25e3
assert u3["U3D_unit_type"] == "MolecularSieve"

# Recycle basis: NaOH/(NaOH + H2O) = 0.50 after the M2 makeup.
assert abs(recycle["EC1_recycle_NaOH_wt_frac_NaOH_water_basis"] - 0.50) < 1e-8
assert abs(recycle["fresh_NaOH_makeup_water_kgph"]) < 1e-12
assert abs(
    recycle["U2_feed_NaOH_kgph"]
    - recycle["gross_NaOH_target_kgph"]
) < 1e-8

# Recycle state with the element-closed U2 (char residue instead of the
# unconverted-biomass proxy: smaller F1 cake, less carbonate liquor lost).
# Baseline uniform_redox_scaling (2026-10-12); the h2_priority closure gives
# 0.2394643 (less char, slightly smaller F1 cake).
assert abs(recycle["U2_feed_NaOH_kgph"] - 1.3094) < 1e-6
assert abs(recycle["U2_feed_Na2CO3_kgph"] - 0.2388918012416657) < 1e-5
# 1.0 kg/h biomass moisture + recycle water = NaOH (50 % NaOH/(NaOH + H2O)).
assert abs(recycle["U2_feed_water_kgph"] - (1.0 + 1.3094)) < 1e-5

# Dryer and PSA checks.
assert u3["U3D_dry_gas_water_kgph"] < 1e-12
assert abs(u3["U3P_actual_H2_recovery"] - 0.90) < 1e-9
assert u3["U3K_H2_product_total_kgph"] > 0.0

print("\nStep 7.6 native EC1 + U3D checks passed.")
