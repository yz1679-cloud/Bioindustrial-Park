"""Convert independently calculated annual costs and impacts to ATT reporting bases.

Costs and coproduct revenue must be supplied separately. Capital charge is a
caller-defined annual amount; this module never derives treatment cost from MSP.
"""
import math


def normalize_case(*, wet_kgph, dry_kgph, h2_kgph, hours, flows_kgph,
                   operating_cost_usd_year, coproduct_revenue_usd_year,
                   capital_charge_usd_year, gross_gwp_per_kg_h2,
                   credit_gwp_per_kg_h2, msp_per_kg_h2):
    values = (wet_kgph, dry_kgph, h2_kgph, hours, operating_cost_usd_year,
              coproduct_revenue_usd_year, capital_charge_usd_year,
              gross_gwp_per_kg_h2, credit_gwp_per_kg_h2, msp_per_kg_h2,
              *flows_kgph.values())
    if not all(math.isfinite(float(x)) for x in values):
        raise ValueError('inputs must be finite')
    if wet_kgph <= 0 or h2_kgph <= 0 or hours <= 0 or not 0 <= dry_kgph <= wet_kgph:
        raise ValueError('invalid feed, hydrogen or operating-hours basis')
    if any(x < 0 for x in flows_kgph.values()):
        raise ValueError('material flows must be nonnegative')
    annual_wet_t = wet_kgph * hours / 1000
    net_cost = operating_cost_usd_year + capital_charge_usd_year - coproduct_revenue_usd_year
    annual = dict(wet_presscake_t=annual_wet_t, operating_cost_usd=operating_cost_usd_year,
                  coproduct_revenue_usd=coproduct_revenue_usd_year,
                  capital_charge_usd=capital_charge_usd_year, net_treatment_cost_usd=net_cost)
    def basis(multiplier, annual_denominator):
        result = dict(wet_presscake_kg=wet_kgph * multiplier,
                      dry_presscake_kg=dry_kgph * multiplier,
                      hydrogen_kg=h2_kgph * multiplier,
                      operating_cost_usd=operating_cost_usd_year / annual_denominator,
                      coproduct_revenue_usd=coproduct_revenue_usd_year / annual_denominator,
                      capital_charge_usd=capital_charge_usd_year / annual_denominator,
                      net_treatment_cost_usd=net_cost / annual_denominator,
                      gross_gwp_kg_co2e=gross_gwp_per_kg_h2 * h2_kgph * multiplier,
                      credit_gwp_kg_co2e=credit_gwp_per_kg_h2 * h2_kgph * multiplier,
                      net_gwp_kg_co2e=(gross_gwp_per_kg_h2 + credit_gwp_per_kg_h2) * h2_kgph * multiplier)
        result.update({key + '_kg': value * multiplier for key, value in flows_kgph.items()})
        return result
    return dict(annual=annual, per_kg_h2=basis(1 / h2_kgph, h2_kgph * hours),
                per_tonne_wet=basis(1000 / wet_kgph, annual_wet_t),
                hydrogen_msp_usd_per_kg=msp_per_kg_h2)
