"""Sodium (Na) ledger for the simulated ATT flowsheet.

Read-only audit: per-unit Na balances and the external Na balance across
the actual graph of ``sys.units``. Run only after convergence.
"""
from __future__ import annotations

import math
from collections.abc import Mapping

MW_NA = 22.98976928  # g/mol
MW_NAOH = 39.997  # g/mol
MW_NA2CO3 = 105.9888
NAOH_NA_FRACTION = MW_NA / MW_NAOH
CARBONATE_NA_FRACTION = 2 * MW_NA / MW_NA2CO3
COMPONENTS = ('NaOH', 'Na2CO3', 'Water')


def number(value, name, nonnegative=True):
    try:
        v = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{name}: expected finite numeric value') from exc
    if not math.isfinite(v) or (nonnegative and v < 0):
        raise ValueError(f'{name}: expected finite nonnegative value')
    return v


def composition(values):
    if not isinstance(values, Mapping) or set(values) != set(COMPONENTS):
        raise ValueError('Composition requires exactly NaOH, Na2CO3, Water')
    return {k: number(values[k], k) for k in COMPONENTS}


def sodium_kgph(values):
    d = composition(values)
    return d['NaOH'] * NAOH_NA_FRACTION + d['Na2CO3'] * CARBONATE_NA_FRACTION


def get_stream_sodium(stream):
    """Stream Na ledger: species-based and elemental cross-check (if available)."""
    naoh = number(stream.imass['NaOH'], 'stream NaOH')
    carbonate = number(stream.imass['Na2CO3'], 'stream Na2CO3')
    comp = {'NaOH': naoh, 'Na2CO3': carbonate, 'Water': 0.0}
    species_na = sodium_kgph(comp)
    atomic = None
    if hasattr(stream, 'get_atomic_flow'):
        atomic = number(stream.get_atomic_flow('Na'), 'atomic Na') * MW_NA
    extra = atomic - species_na if atomic is not None else None
    return {'id': str(stream.ID), 'naoh_kgph': naoh, 'na2co3_kgph': carbonate,
            'explicit_species_na_kgph': species_na,
            'all_chemicals_atomic_na_kgph': atomic,
            'other_Na_in_other_species_or_thermo_kgph': extra}


def native_unit_sodium_ledger(unit, *, tolerance_kgph=1e-7):
    """READ ONLY; no simulation or changes performed here."""
    ins = [get_stream_sodium(s) for s in unit.ins]
    outs = [get_stream_sodium(s) for s in unit.outs]
    in_na = sum((r['all_chemicals_atomic_na_kgph'] if r['all_chemicals_atomic_na_kgph'] is not None else r['explicit_species_na_kgph']) for r in ins)
    out_na = sum((r['all_chemicals_atomic_na_kgph'] if r['all_chemicals_atomic_na_kgph'] is not None else r['explicit_species_na_kgph']) for r in outs)
    err = out_na - in_na
    return {'unit_id': str(unit.ID), 'input_streams': ins, 'output_streams': outs,
            'na_in_kgph': in_na, 'na_out_kgph': out_na, 'na_balance_residual_kgph': err,
            'balance_pass': abs(err) <= max(tolerance_kgph, abs(in_na)*1e-7)}


def read_only_att_na_probe(sys):
    """Audit all simulated process units, including optional W2.

    The boundary is the actual graph of ``sys.units``, not a hard-coded
    list of historic 18 unit IDs. An internal stream is never counted as
    an external product, even if its BioSTEAM source/sink is unusual.
    Run only after convergence; this function is read-only.
    """
    process_units = list(sys.units)
    if not process_units:
        raise ValueError('No process units found in simulated ATT system')
    unit_ids = [str(unit.ID) for unit in process_units]
    if len(set(unit_ids)) != len(unit_ids):
        raise ValueError('Duplicate process unit IDs in sodium audit')
    ledger = [native_unit_sodium_ledger(unit) for unit in process_units]

    inlet_streams = {}
    outlet_streams = {}
    for unit in process_units:
        for stream in unit.ins:
            inlet_streams[id(stream)] = stream
        for stream in unit.outs:
            outlet_streams[id(stream)] = stream

    # Identity sets determine the boundary. Internal connections cancel.
    # Do not depend on globally registered stream.source / stream.sink:
    # they can include units outside the audited system.
    external_feeds = [stream for key, stream in inlet_streams.items()
                      if key not in outlet_streams]
    external_products = [stream for key, stream in outlet_streams.items()
                         if key not in inlet_streams]

    def na_mass(stream):
        record = get_stream_sodium(stream)
        return (record['all_chemicals_atomic_na_kgph']
                if record['all_chemicals_atomic_na_kgph'] is not None
                else record['explicit_species_na_kgph'])

    in_na = sum(na_mass(s) for s in external_feeds)
    out_na = sum(na_mass(s) for s in external_products)
    return {
        'stage': 'READ_ONLY_ACTUAL_BIOSTEAM_NA_LEDGER_GRAPH_BOUNDARY',
        'audited_unit_ids': unit_ids,
        'audited_unit_count': len(process_units),
        'unit_ledger': ledger,
        'all_unit_Na_balances_pass': all(x['balance_pass'] for x in ledger),
        'external_feed_streams': [get_stream_sodium(s) for s in external_feeds],
        'external_product_streams': [get_stream_sodium(s) for s in external_products],
        'external_Na_in_kgph': in_na, 'external_Na_out_kgph': out_na,
        'external_Na_residual_kgph': out_na-in_na,
        'total_external_Na_balance_pass': abs(out_na-in_na) <= max(1e-7, abs(in_na)*1e-7),
    }
