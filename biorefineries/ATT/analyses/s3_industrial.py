"""Independent S3 screening on the unchanged land-based S1 flowsheet.

Run: python -m biorefineries.ATT.analyses.s3_industrial [--no-ree]
"""
import argparse
import json
import math

from biorefineries.ATT.analyses import industrial_whr as whr


def run(enable_ree_recovery=True, reference_hours=7920., host_hours=7920., utilization=1.,
        approach_C=20., effectiveness=.9, installed_cost_usd_per_kW=500.,
        auxiliary_kW_per_kW=.01, heat_price_usd_per_MWh=0., heat_burden_kg_per_MWh=0., system=None,
        return_tea=False):
    """Simulate S1 and add an illustrative industrial heat accounting case.

    Host hours imply constant annual nominal production scaled by utilization;
    annual ATT recovery assumes the two plants overlap for min(host, ATT) hours.
    Capital and auxiliaries are explicitly uncertain screening inputs, not quotes.
    ``system`` may supply an already simulated ATT system for composition
    sensitivities; when supplied, its REE setting takes precedence.
    ``return_tea`` exposes the evaluated TEA object for detailed accounting;
    the default return remains JSON-compatible.
    """
    import biosteam as bst
    from biorefineries.ATT.analyses import scenarios, marine_whr, lca, tea, inventory
    from biorefineries.ATT.analyses.breakdown import build_att_breakdown

    for x in (installed_cost_usd_per_kW, auxiliary_kW_per_kW, heat_price_usd_per_MWh, heat_burden_kg_per_MWh):
        if not math.isfinite(x) or x < 0:
            raise ValueError('cost, auxiliary and burden inputs must be finite and nonnegative')
    if system is None:
        system = scenarios.create(scenarios.ATT_S1, ree_recovery=enable_ree_recovery)
    enable_ree_recovery = any(u.ID == 'LC1' for u in system.units)
    def boundary_snapshot():
        return tuple((stream.ID, float(stream.T), float(stream.P), tuple(float(x) for x in stream.mass))
                     for stream in (*system.feeds, *system.products))
    original_flows = boundary_snapshot()
    baseline = build_att_breakdown('att_s1', sys=system)['summary']
    baseline_raw_aoc = tea.evaluate_att_tea(system)['tea'].AOC
    mass_audit = inventory.check_att_inventory(system)
    hxn = next(f for f in system.facilities if isinstance(f, bst.HeatExchangerNetwork))
    hxn_audit = whr.audit_hxn_enthalpy(hxn)
    hxn_scale_kW = sum(abs(x.outs[0].H - x.ins[0].H) for x in hxn.original_heat_exchangers) / 3600.
    hxn_tolerance_kW = 1e-6 * max(1., hxn_scale_kW)
    if max(hxn_audit['max_lifecycle_error_kW'], hxn_audit['max_exchanger_error_kW']) > hxn_tolerance_kW:
        raise ValueError('HXN stream enthalpy audit failed; S3 results withheld')
    hours = float(system.operating_hours)
    overlap_fraction = min(hours, host_hours) / hours
    cfg = marine_whr.load_whr_config()
    cfg['sinks']['u2_feed_preheat']['enabled'] = False
    sinks = whr.reconcile_sinks(system, marine_whr.s1_heat_sinks(system, cfg))
    steam_hu = next(hu for hu in system.heat_utilities if hu.agent and hu.agent.ID == 'low_pressure_steam')
    steam_kW = steam_hu.duty / 3600.
    agent = steam_hu.agent
    if agent.T_limit is not None or agent.phase != 'g' or steam_hu.flow <= 0:
        raise ValueError('S3 steam generation requires the modeled condensing-vapor LP steam agent')
    latent_kJ_per_kg = steam_hu.duty / (steam_hu.flow * agent.MW)
    if not math.isfinite(latent_kJ_per_kg) or latent_kJ_per_kg <= 0:
        raise ValueError('invalid LP steam latent enthalpy')
    whr.check_steam_inventory(sinks, steam_kW)
    sources = whr.industrial_sources(reference_hours, host_hours, utilization)
    ideal = whr.generate_steam(sources, sinks, agent.T - 273.15, approach_C, effectiveness)
    # The reporting basis is average over all ATT operating hours, not just overlap.
    allocations = ideal['allocations']
    used = ideal['used_kW'] * overlap_fraction
    avoided_cost_h = sum(a['used_kW'] * sinks[a['sink_index']]['usd_per_kWh'] for a in allocations) * overlap_fraction
    installed = ideal['used_kW'] * installed_cost_usd_per_kW
    pump = ideal['used_kW'] * auxiliary_kW_per_kW * overlap_fraction
    purchased = sum(max(0., hu.duty) for hu in system.heat_utilities if hu.agent and hu.agent.ID in ('natural_gas', 'low_pressure_steam')) / 3600.
    voc = [('Industrial WHR: avoided heat', -avoided_cost_h * hours),
           ('Industrial WHR: auxiliary electricity', pump * bst.PowerUtility.price * hours),
           ('Industrial WHR: heat purchase', used * heat_price_usd_per_MWh / 1000 * hours)]
    capital = [('Industrial WHR installed screening allowance', installed, 'user-configurable USD/kW placeholder')]
    result = tea.evaluate_att_tea(system, extra_capital=capital, extra_voc=voc, operating_hours=hours)
    t = result['tea']
    f = lca._factors(None)
    ng = f['natural_gas_combustion'] + f['natural_gas_upstream']
    avoided_emissions = used * 3.6 / lca._LCA['natural_gas']['boiler_efficiency'] * ng
    aux_emissions = pump * f['electricity']
    heat_emissions = used * heat_burden_kg_per_MWh / 1000
    h2 = float(inventory._streams(system)['h2_product'].imass['H2'])
    delta = (aux_emissions + heat_emissions - avoided_emissions) / h2
    products = {stream.ID: dict(mass_kg_per_h=float(stream.F_mass),
                **{f'{component}_kg_per_h': float(stream.imass[component]) for component in ('H2', 'CaCO3', 'REO')})
                for stream in system.products}
    output = dict(ree_enabled=enable_ree_recovery, sources=sources, sinks=sinks, allocations=allocations,
        operating_hours_per_year=hours, product_flows=products, boundary_flows_unchanged=boundary_snapshot() == original_flows,
        configuration=dict(reference_hours=reference_hours, host_hours=host_hours, utilization=utilization,
                           approach_C=approach_C, effectiveness=effectiveness,
                           installed_cost_usd_per_kW=installed_cost_usd_per_kW,
                           auxiliary_kW_per_kW=auxiliary_kW_per_kW,
                           heat_price_usd_per_MWh=heat_price_usd_per_MWh,
                           heat_burden_kg_per_MWh=heat_burden_kg_per_MWh),
        overlap_fraction=overlap_fraction, available_kW=ideal['available_kW'], feasible_overlap_kW=ideal['feasible_kW'],
        source_details=ideal['sources'], source_extracted_overlap_kW=ideal['extracted_kW'],
        transfer_loss_overlap_kW=ideal['loss_kW'], useful_steam_overlap_kW=ideal['used_kW'],
        steam_agent=dict(temperature_C=agent.T-273.15, pressure_Pa=agent.P, phase=agent.phase,
                         latent_heat_kJ_per_kg=latent_kJ_per_kg,
                         utility_to_process_ratio=steam_hu.unit_duty/steam_hu.duty,
                         return_assumption='saturated liquid condensate at the steam-agent temperature'),
        steam_generated_average_kg_per_h=used*3600/latent_kJ_per_kg,
        process_heat_equivalent_average_kW=used*steam_hu.unit_duty/steam_hu.duty,
        baseline_steam_kW=steam_kW, remaining_steam_average_kW=steam_kW-used,
        remaining_fired_heating_kW=purchased-steam_kW,
        avoided_boiler_fuel_average_kW=used/float(lca._LCA['natural_gas']['boiler_efficiency']),
        used_average_kW=used, unused_overlap_kW=ideal['unused_kW'], heating_before_kW=purchased,
        heating_after_average_kW=purchased-used, recovered_MWh_per_year=used*hours/1000,
        recovered_GJ_per_year=whr.annual_heat(used, hours)[1], auxiliary_average_kW=pump,
        incremental_capex_usd=installed, incremental_foc_usd_per_year=installed*float(tea._FIN['foc_frac_of_fci']),
        auxiliary_electricity_cost_usd_per_year=pump*bst.PowerUtility.price*hours,
        heat_purchase_cost_usd_per_year=used*heat_price_usd_per_MWh/1000*hours,
        avoided_cost_usd_per_year=avoided_cost_h*hours, extra_voc_usd_per_year=sum(x[1] for x in voc),
        s1=baseline, mass_audit=mass_audit, hxn_enthalpy_audit=hxn_audit,
        hxn_energy_balance_percent_error=hxn.energy_balance_percent_error,
        s3_FCI_usd=t.FCI, s3_AOC_usd_per_year=t.AOC,
        s3_net_AOC_usd_per_year=baseline['AOC_MUSD_per_yr']*1e6 + t.AOC-baseline_raw_aoc,
        s3_MSP_usd_per_kg_H2=result['msp'],
        MSP_change_usd_per_kg_H2=result['msp']-baseline['MSP_USD_per_kg_H2'],
        s3_GWP_kg_per_kg_H2=baseline['GWP_kgCO2e_per_kg_H2']+delta, GWP_change_kg_per_kg_H2=delta,
        avoided_emissions_kg_per_hour=avoided_emissions, auxiliary_emissions_kg_per_hour=aux_emissions,
        heat_burden_kg_per_hour=heat_emissions, h2_kg_per_hour=h2,
        net_operating_benefit_usd_per_year=avoided_cost_h*hours-sum(x[1] for x in voc[1:])-installed*float(tea._FIN['foc_frac_of_fci']))
    if return_tea:
        output['tea_result'] = result
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--no-ree', action='store_true')
    args = parser.parse_args()
    print(json.dumps(run(enable_ree_recovery=not args.no_ree), indent=2, default=float))


if __name__ == '__main__':
    main()
