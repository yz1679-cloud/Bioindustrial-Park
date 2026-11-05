"""Conservative temperature-interval screening for ATT industrial heat (kW)."""
from math import isfinite


def annual_heat(power_kW, hours):
    """Delivered heat as (MWh/year, GJ/year)."""
    return power_kW * hours / 1000., power_kW * hours * .0036


def steam_duty_kW(utilities):
    """Actual positive steam utility, never the unsigned HXutility.Q magnitude."""
    return sum(hu.duty for hu in utilities
               if hu.agent is not None and hu.agent.ID == 'low_pressure_steam' and hu.duty > 0) / 3600.


def audit_hxn_enthalpy(hxn):
    """Check lifecycle end-to-end and two-sided process exchanger enthalpy closure."""
    lifecycle_errors = []
    for life in hxn.stream_life_cycles:
        original = hxn.original_heat_exchangers[life.index]
        target = original.outs[0].H - original.ins[0].H
        actual = sum(stage.unit.outs[stage.index].H - stage.unit.ins[stage.index].H for stage in life.life_cycle)
        lifecycle_errors.append(abs(actual - target) / 3600.)
    exchanger_errors = [abs(sum(o.H - i.H for i, o in zip(hx.ins, hx.outs))) / 3600. for hx in hxn.new_HXs]
    return dict(lifecycle_count=len(lifecycle_errors), exchanger_count=len(exchanger_errors),
                max_lifecycle_error_kW=max(lifecycle_errors, default=0.),
                max_exchanger_error_kW=max(exchanger_errors, default=0.))


def reconcile_sinks(system, sinks):
    """Replace HXN-matched sink duties with their signed residual utility objects."""
    import biosteam as bst
    hxn = next(f for f in system.facilities if isinstance(f, bst.HeatExchangerNetwork))
    by_unit = {}
    for life in hxn.stream_life_cycles:
        orig = hxn.original_heat_exchangers[life.index]
        if not any(hu.agent and hu.agent.ID == 'low_pressure_steam' and hu.duty > 0
                   for hu in orig.heat_utilities):
            continue
        owner = orig.owner.ID
        if owner in by_unit:
            raise ValueError(f'multiple steam lifecycles for {owner}; attribution ambiguous')
        utils = [stage.unit for stage in life.life_cycle if isinstance(stage.unit, bst.HXutility)]
        by_unit[owner] = (sum(steam_duty_kW(u.heat_utilities) for u in utils), utils)
    counts = {}
    for sink in sinks:
        if sink['utility'] != 'low_pressure_steam' or sink['unit'] not in by_unit:
            continue
        ID = sink['unit']
        counts[ID] = counts.get(ID, 0) + 1
        if counts[ID] != 1:
            raise ValueError(f'multiple steam sink rows for {ID}; attribution ambiguous')
        residual, utils = by_unit[ID]
        sink['purchased_kW'] = residual
        sink['hxn_recovered_kW'] = sink['purchased_before_hxn_kW'] - residual
        sink['note'] = ('HXN residual from signed utility agents; cooling is not purchased steam' if utils
                        else 'fully recovered by HXN')
    return sinks


def check_steam_inventory(sinks, system_steam_kW):
    """Fail closed if per-unit residual duties do not reconcile with system steam."""
    listed = sum(s['purchased_kW'] for s in sinks if 'steam' in s['utility'])
    if abs(listed - system_steam_kW) > 1e-6 * max(1., abs(system_steam_kW)):
        raise ValueError(f'steam inventory mismatch: sink total {listed:.6f} kW, '
                         f'system total {system_steam_kW:.6f} kW; S3 results withheld')


def industrial_sources(reference_hours=7920.0, host_hours=7920.0, utilization=1.0):
    """Scale annual nominal production; rates assume uniform output during host hours."""
    if not (0 < reference_hours <= 8760 and 0 < host_hours <= 8760 and 0 <= utilization <= 1):
        raise ValueError('hours must be in (0, 8760] and utilization in [0, 1]')
    factor = .90718474 * reference_hours / host_hours * utilization
    return [dict(source=name, available_kW=q * factor, T_in_C=hi, T_out_C=lo)
            for name, q, hi, lo in [('H1', 12040., 1664.4, 800.), ('H3', 3930., 800., 40.)]]


def generate_steam(sources, sinks, steam_temperature_C, approach_C=20., effectiveness=.9):
    """Isothermal LP-steam generation from saturated returned condensate, in kW.

    Source capacity above steam temperature + approach is assumed linear in
    temperature. An extracted heat fraction reaches the steam header, which
    displaces the same BioSTEAM utility duty. Losses and unused source heat
    are separate; allocations are tracked once per source and steam sink.
    """
    if not all(map(isfinite, (steam_temperature_C, approach_C, effectiveness))) or approach_C < 0 or not 0 <= effectiveness <= 1:
        raise ValueError('invalid steam temperature, approach or effectiveness')
    source_ids = [source['source'] for source in sources]
    if len(source_ids) != len(set(source_ids)):
        raise ValueError('duplicate industrial source identifier')
    eligible = []
    for i, sink in enumerate(sinks):
        q = float(sink['purchased_kW'])
        if not isfinite(q) or q < 0:
            raise ValueError('sink duty must be finite and nonnegative')
        if sink.get('eligible') and sink.get('utility') == 'low_pressure_steam' and q:
            eligible.append((i, sink))
    left = {i: float(s['purchased_kW']) for i, s in eligible}
    results, allocations = [], []
    threshold = steam_temperature_C + approach_C
    for source in sorted(sources, key=lambda s: s['T_in_C']):
        hi, lo, q = (float(source[k]) for k in ('T_in_C', 'T_out_C', 'available_kW'))
        if not all(map(isfinite, (hi, lo, q))) or hi <= lo or q < 0:
            raise ValueError('invalid source')
        feasible = q * max(0., hi-max(lo, threshold)) / (hi-lo)
        remaining = feasible
        for i, sink in eligible:
            if not effectiveness:
                break
            extracted = min(remaining, left[i] / effectiveness)
            if extracted <= 0:
                continue
            delivered = extracted * effectiveness
            remaining -= extracted
            left[i] -= delivered
            allocations.append(dict(source=source['source'], unit=sink['unit'], sink_index=i,
                                    feasible_kW=extracted, extracted_kW=extracted, used_kW=delivered,
                                    interval_bottom_C=max(lo, threshold), sink_temperature_C=steam_temperature_C))
        extracted = feasible - remaining
        results.append(dict(source=source['source'], available_kW=q, temperature_feasible_kW=feasible,
                            extracted_kW=extracted, loss_kW=extracted * (1-effectiveness),
                            steam_kW=extracted * effectiveness, unused_kW=q-extracted))
    return dict(sources=results, allocations=allocations,
                available_kW=sum(x['available_kW'] for x in results),
                feasible_kW=sum(x['temperature_feasible_kW'] for x in results),
                extracted_kW=sum(x['extracted_kW'] for x in results),
                loss_kW=sum(x['loss_kW'] for x in results),
                used_kW=sum(x['steam_kW'] for x in results),
                unused_kW=sum(x['unused_kW'] for x in results))


def allocate(sources, sinks, approach_C=20., effectiveness=.9):
    """Split hot streams at all sink thresholds; credit each interval at most once.

    Each sink is conservatively treated as isothermal at its highest temperature.
    Effectiveness represents a fraction of the ideal matched duty delivered; source
    energy not delivered is reported as unused, including transfer losses.
    """
    if not (isfinite(approach_C) and approach_C >= 0 and 0 <= effectiveness <= 1):
        raise ValueError('invalid approach or effectiveness')
    eligible = []
    for i, sink in enumerate(sinks):
        q = float(sink['purchased_kW'])
        if not isfinite(q) or q < 0:
            raise ValueError('sink duty must be finite and nonnegative')
        if sink['eligible'] and q and isfinite(sink['T_out_C']):
            eligible.append((i, sink))
    left = {i: float(s['purchased_kW']) for i, s in eligible}
    assignments = []
    for source in sorted(sources, key=lambda s: s['T_in_C']):
        hi, lo, q = (float(source[k]) for k in ('T_in_C', 'T_out_C', 'available_kW'))
        if not all(map(isfinite, (hi, lo, q))) or hi <= lo or q < 0:
            raise ValueError('invalid source')
        cuts = sorted({lo, hi} | {min(hi, max(lo, s['T_out_C'] + approach_C)) for _, s in eligible}, reverse=True)
        for top, bottom in zip(cuts, cuts[1:]):
            band = q * (top - bottom) / (hi - lo)
            for i, sink in sorted(eligible, key=lambda item: item[1]['T_out_C'], reverse=True):
                if bottom + 1e-10 < sink['T_out_C'] + approach_C:
                    continue
                matched = min(band, left[i])
                if matched > 0:
                    band -= matched
                    left[i] -= matched
                    assignments.append(dict(source=source['source'], unit=sink['unit'], sink_index=i,
                                            feasible_kW=matched, used_kW=matched * effectiveness,
                                            interval_bottom_C=bottom, sink_temperature_C=sink['T_out_C']))
    feasible = sum(a['feasible_kW'] for a in assignments)
    used = sum(a['used_kW'] for a in assignments)
    total = sum(s['available_kW'] for s in sources)
    return dict(allocations=assignments, feasible_kW=feasible, used_kW=used,
                available_kW=total, unused_kW=total-used)
