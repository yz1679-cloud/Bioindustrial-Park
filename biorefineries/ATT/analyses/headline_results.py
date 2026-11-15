"""Headline results of the S3 advisor report, computed from the model: external-energy EROI and the treatment cost and GWP
per tonne of presscake against illustrative hydrogen benchmarks.

EROI = H2 lower heating value / external energy (fuel LHV + delivered electricity at 3.6 MJ/kWh); recovered waste heat has
zero energy burden, so only the auxiliary power of the heat recovery is added. The benchmark price and GWP of the hydrogen
are assumptions of the advisor report (references in BENCHMARKS), not model results.
"""
from biorefineries.ATT.analyses import inventory, scenarios
from biorefineries.ATT.utils import load_assumptions
from biorefineries.ATT.analyses.s3_industrial import run as s3_run
from biorefineries.ATT.analyses.ree_tea_cases import collect_ree_tea

H2_LHV_MJ_PER_KG = 120.0
MJ_PER_KWH = 3.6

# name: (H2 price [USD/kg], H2 GWP [kg CO2e/kg]), from data/hydrogen_benchmarks.yaml (illustrative assumptions with their sources)
BENCHMARKS = {name: (float(v["price_usd_per_kg"]), float(v["gwp_kg_co2e_per_kg"]))
              for name, v in load_assumptions("hydrogen_benchmarks.yaml")["benchmarks"].items()}


def s3_energy_and_eroi(industrial=None, system=None):
    """External energy [MJ/kg dry feed] and EROI of S1 and S3 (REE on)."""
    system = system or scenarios.create(scenarios.ATT_S1, ree_recovery=True)
    industrial = industrial or s3_run(enable_ree_recovery=True)
    dry = inventory._dry_feed_kgph(system)
    u = {r["item"]: r["per_kg_dry"] for r in inventory.get_att_purchased_utilities(system)}
    fuel = u["U2 natural gas: fuel input (LHV)"]
    boiler = u["LP steam: boiler natural gas (LHV)"]
    electric = u["Electricity: total"] * MJ_PER_KWH
    avoided = industrial["used_average_kW"] * MJ_PER_KWH / dry / float(inventory._LCA["steam_boiler_efficiency"])
    aux = industrial["auxiliary_average_kW"] * MJ_PER_KWH / dry
    recovered = sum(r["steam_kW"] for r in industrial["source_details"]) * MJ_PER_KWH / dry
    output = H2_LHV_MJ_PER_KG * industrial["h2_kg_per_hour"] / dry
    external_s1 = fuel + boiler + electric
    external_s3 = external_s1 - avoided + aux
    return dict(fuel_MJ_per_kg_dry=fuel, boiler_fuel_S1_MJ_per_kg_dry=boiler, electricity_MJ_per_kg_dry=electric,
                avoided_boiler_fuel_MJ_per_kg_dry=avoided, whr_auxiliary_power_MJ_per_kg_dry=aux,
                recovered_heat_MJ_per_kg_dry=recovered,
                h2_output_MJ_per_kg_dry=output, external_S1_MJ_per_kg_dry=external_s1,
                external_S3_MJ_per_kg_dry=external_s3, EROI_S1=output / external_s1, EROI_S3=output / external_s3,
                EROI_S3_counting_recovered_heat=output / (external_s3 + recovered))


def benchmark_treatment(industrial=None, ree_tea=None):
    """Net treatment cost [USD/t dry feed] and GWP [kg CO2e/t dry feed] of S3 (REE on) when the hydrogen replaces each benchmark."""
    industrial = industrial or s3_run(enable_ree_recovery=True)
    ree_tea = ree_tea or collect_ree_tea()
    row = next(r for r in ree_tea["cases"] if r["scenario"] == "S3" and r["ree_enabled"])
    dry = scenarios.ATT_S1["dry_feed_kgph"]
    hours = industrial["operating_hours_per_year"]
    h2_per_t = industrial["h2_kg_per_hour"] / (dry / 1e3)                                # kg H2 per tonne of dry feed
    annual_t = dry * hours / 1e3
    cost = row["net_treatment_cost_usd_per_year"] / annual_t
    gwp = industrial["s3_GWP_kg_per_kg_H2"] * h2_per_t
    return {name: dict(treatment_cost_USD_per_t=cost - h2_per_t * price, treatment_GWP_kg_per_t=gwp - h2_per_t * ci)
            for name, (price, ci) in BENCHMARKS.items()}
