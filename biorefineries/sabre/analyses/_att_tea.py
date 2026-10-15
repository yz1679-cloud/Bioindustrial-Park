"""
Preliminary TEA of the frozen ATT model: minimum H2 selling price (MSP).

Reuses SaBReTEA (tea.yaml financial assumptions; FCI = installed equipment
cost; FOC = 4 % of FCI) through a thin subclass that adds only what the
frozen unit models do not carry:

- extra installed capital: out-of-model equipment estimates from
  _att_inventory (C1/M2 tanks, U2 vessel, EC1 evaporator/condenser/vacuum),
  the preliminary PSA estimate and the U3K reciprocating-compressor
  correction (att_tea.yaml capex);
- extra annual operating cost: purge-neutralization H2SO4, estimated
  agitator/vacuum electricity, and the natural-gas cost adjustment that
  prices fuel = U2 duty / burner efficiency (as in the LCA) instead of the
  BioSTEAM agent flow.

Material and disposal prices are set on the frozen streams; utilities use
BioSTEAM agent prices (steam and cooling-water prices cover their
generation, so boiler gas and tower electricity are not priced again).
Prices and capital assumptions: data/att_tea.yaml.
"""
import biosteam as bst

from biorefineries.sabre._tea import SaBReTEA
from biorefineries.sabre.analyses import _att_inventory as inv
from biorefineries.sabre.analyses._att_lca import _h2so4_kgph
from biorefineries.sabre.utils import OPERATING_DAYS_PER_YEAR, load_assumptions

__all__ = (
    "ATTTEA",
    "create_att_tea_system",
    "evaluate_att_tea",
    "get_att_tea_sensitivity",
    "caco3_cake_price",
    "get_att_caco3_cases",
    "get_att_lime_price_cases",
    "get_att_p1_power_cases",
    "get_att_offgas_cases",
    "get_att_cost_year_comparison",
    "export_att_tea",
)

_T = load_assumptions("att_tea.yaml")["tea"]
_TEA_YAML = load_assumptions("tea.yaml")
_FIN = _TEA_YAML["tea"]
_PRICE = _TEA_YAML["price"]
_BURNER_EFFICIENCY = float(load_assumptions("att.yaml")["att"]["energy_sources"]["natural_gas"]["burner_efficiency"])


class ATTTEA(SaBReTEA):
    """SaBReTEA plus installed capital and annual costs outside the unit models."""

    def __init__(self, *args, extra_installed_cost=0.0, extra_VOC=0.0, **kwargs):
        self.extra_installed_cost = float(extra_installed_cost)
        self.extra_VOC = float(extra_VOC)
        super().__init__(*args, **kwargs)

    def _DPI(self, installed_equipment_cost):
        return installed_equipment_cost + self.extra_installed_cost

    @property
    def VOC(self):
        return super().VOC + self.extra_VOC


def create_att_tea_system():
    """Frozen ATT model at the SaBRe reference scale."""
    from biorefineries.sabre.systems._att_system import create_att_system

    scale = inv.get_att_reference_scale()
    sys = inv._simulate(create_att_system(dry_sargassum_kgph=scale["dry_feed_kgph"]), scale["dry_feed_kgph"])
    sys.operating_hours = scale["operating_hours_per_year"]
    return sys


def _prices(overrides=None):
    p = {k: float(v["value"]) for k, v in _T["prices"].items() if isinstance(v, dict)}
    p.update(overrides or {})
    return p


def caco3_cake_price(sys, fraction=0.0, price_usd_per_t=0.0, handling_usd_per_t=0.0, dispose_unsold=True):
    """
    Effective price of the wet CaCO3 cake [USD/kg wet cake]: the sold share
    earns (price - handling) on its CaCO3 content only; the unsold share is
    disposed at tea.yaml disposal_solid (dispose_unsold) or carries no cost.
    """
    cake = inv._streams(sys)["caco3_cake"]
    w = float(cake.imass["CaCO3"]) / float(cake.F_mass)
    disposal = float(_PRICE["disposal_solid"]["baseline"]) if dispose_unsold else 0.0
    return fraction * w * (price_usd_per_t - handling_usd_per_t) / 1e3 + (1.0 - fraction) * disposal


def _apply_prices(sys, p, cake_price=None, offgas_usd_per_t=0.0, feedstock_usd_per_wet_t=None):
    s = inv._streams(sys)
    s["att_sargassum_feed"].price = (float(_PRICE["sargassum"]["baseline"]) if feedstock_usd_per_wet_t is None
                                     else float(feedstock_usd_per_wet_t) / 1e3)
    s["fresh_naoh_solid"].price = p["NaOH"]
    s["lime"].price = p["CaOH2"]
    s["dissolution_water"].price = p["process_water"]
    for ID in _T["prices"]["wastewater_streams"]:
        s[ID].price = float(_PRICE["disposal_wastewater"]["baseline"])
    for ID in _T["prices"]["solid_waste_streams"]:
        s[ID].price = float(_PRICE["disposal_solid"]["baseline"])
    s["caco3_cake"].price = float(_T["prices"]["CaCO3_cake"]) if cake_price is None else float(cake_price)
    s["u3_tail_gas"].price = float(_T["prices"]["offgas"]) - float(offgas_usd_per_t) / 1e3
    s[_T["product"]].price = 0.0


def _ng_usd_per_MJ():
    agent = bst.HeatUtility.get_agent("natural_gas")
    return agent.regeneration_price / (bst.Chemical("CH4").LHV / 1e3)


def _psa_installed_cost(sys, factor=1.0):
    c = _T["capex"]["PSA"]
    h2_tpd = float(inv._streams(sys)["h2_product"].imass["H2"]) * 24.0 / 1e3
    return c["anchor_installed_cost_usd"] * (h2_tpd / c["anchor_capacity_t_H2_per_day"]) ** c["exponent"] * factor


def _u3k_reciprocating(sys):
    U3K = inv._units(sys)["U3K"]
    with inv._scratch_flowsheet():
        unit = bst.IsothermalCompressor("U3K_reciprocating_estimate", ins=U3K.ins[0].copy(), P=U3K.P,
                                        eta=U3K.eta, compressor_type=_T["capex"]["U3K"]["compressor_type"])
        unit.simulate()
    return unit


def _capital_items(sys, estimates, psa_factor=1.0, p1_alternative=False):
    """Extra installed capital beyond the frozen unit models [USD]."""
    u = inv._units(sys)
    items = [(f"{r['item']} (estimate)", r["installed_cost"], r["method"])
             for r in estimates if r["installed_cost"] == r["installed_cost"]]
    items.append(("PSA unit (PRELIMINARY)", _psa_installed_cost(sys, psa_factor), _T["capex"]["PSA"]["source"]))
    recip = _u3k_reciprocating(sys)
    items.append(("U3K: reciprocating replaces screw correlation (difference)",
                  recip.installed_cost - u["U3K"].installed_cost, _T["capex"]["U3K"]["reason"]))
    if p1_alternative:
        a = _T["sensitivities"]["P1_sabre_anchor"]
        dry_tph = inv._dry_feed_kgph(sys) / 1e3
        anchor = a["installed_usd"] * (dry_tph / a["ref_dry_tph"]) ** a["exponent"]
        items.append(("P1: SaBRe press anchor replaces BioSTEAM (difference)", anchor - u["P1"].installed_cost,
                      "preprocessing.yaml press capex anchor, 0.6 scaling"))
    return items


def _voc_items(sys, estimates, p, ng_factor=1.0, elec_factor=1.0, p1_kWh_per_t_dry=None):
    """Extra annual operating costs beyond material, utility and disposal prices [USD/yr]."""
    hours = sys.operating_hours
    elec = bst.PowerUtility.price
    gas = [hu for hu in sys.heat_utilities if hu.agent.ID == "natural_gas"]
    fuel_MJph = sum(hu.duty for hu in gas) / 1e3 / _BURNER_EFFICIENCY
    biosteam_gas_cost = sum(hu.cost for hu in gas)
    aux_kW = sum(r["power_kW"] for r in estimates if r["power_kW"] == r["power_kW"])
    items = [
        ("Purge neutralization H2SO4", _h2so4_kgph(sys) * p["H2SO4"] * hours),
        ("Electricity: agitators and EC1 vacuum (estimate)", aux_kW * elec * elec_factor * hours),
        ("Natural gas: price fuel = duty / 0.90 (adjustment to BioSTEAM agent cost)",
         (fuel_MJph * _ng_usd_per_MJ() * ng_factor - biosteam_gas_cost) * hours),
    ]
    if elec_factor != 1.0:
        items.append(("Electricity price change (unit power)",
                      (elec_factor - 1.0) * sys.power_utility.rate * elec * hours))
    if p1_kWh_per_t_dry is not None:
        P1 = inv._units(sys)["P1"]
        new_kW = p1_kWh_per_t_dry * inv._dry_feed_kgph(sys) / 1e3
        items.append(("P1 power alternative (difference)",
                      (new_kW - P1.power_utility.rate) * elec * elec_factor * hours))
    return items


def evaluate_att_tea(sys, estimates=None, price_overrides=None, psa_factor=1.0, ng_factor=1.0, elec_factor=1.0,
                     fci_factor=1.0, p1_kWh_per_t_dry=None, p1_alternative_capex=False, caco3=None,
                     offgas_usd_per_t=0.0, feedstock_usd_per_wet_t=None):
    """
    Build the TEA for one case and solve the H2 MSP with SaBReTEA's DCF.

    caco3: None keeps the reference treatment (cake neither sold nor costed);
    otherwise keyword arguments of caco3_cake_price (Case A: fraction 0).
    feedstock_usd_per_wet_t: delivered Sargassum cost (collection and
    transport); None uses tea.yaml price.sargassum.baseline (0).
    """
    if estimates is None:
        estimates = inv.get_att_cost_estimates(sys)
    sys.operating_hours = OPERATING_DAYS_PER_YEAR * 24.0
    p = _prices(price_overrides)
    cake_price = None if caco3 is None else caco3_cake_price(sys, **caco3)
    _apply_prices(sys, p, cake_price, offgas_usd_per_t, feedstock_usd_per_wet_t)
    capital = _capital_items(sys, estimates, psa_factor, p1_alternative_capex)
    voc = _voc_items(sys, estimates, p, ng_factor, elec_factor, p1_kWh_per_t_dry)
    installed_units = sum(u.installed_cost for u in sys.units)
    extra_capital = sum(v for _, v, _ in capital)
    extra_capital += (fci_factor - 1.0) * (installed_units + extra_capital)
    tea = ATTTEA(
        system=sys, IRR=_FIN["IRR"], duration=tuple(_FIN["duration"]), depreciation=_FIN["depreciation"],
        income_tax=_FIN["income_tax"], operating_days=OPERATING_DAYS_PER_YEAR,
        construction_schedule=tuple(_FIN["construction_schedule"]), WC_over_FCI=_FIN["WC_over_FCI"],
        finance_interest=_FIN["finance_interest"], finance_years=_FIN["finance_years"],
        finance_fraction=_FIN["finance_fraction"], lang_factor=None, startup_months=_FIN["startup_months"],
        startup_FOCfrac=_FIN["startup_FOCfrac"], startup_VOCfrac=_FIN["startup_VOCfrac"],
        startup_salesfrac=_FIN["startup_salesfrac"], foc_frac_of_fci=_FIN["foc_frac_of_fci"],
        extra_installed_cost=extra_capital, extra_VOC=sum(v for _, v in voc),
    )
    product = inv._streams(sys)[_T["product"]]
    msp = tea.solve_price(product)
    product.price = msp
    return dict(tea=tea, msp=msp, capital_items=capital, voc_items=voc, prices=p, estimates=estimates)


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------

def _capex_table(sys, result):
    tea = result["tea"]
    rows = []
    estimated = {r["unit"] for r in result["estimates"]}
    for u in sys.units:
        if u.installed_cost > 0.0 or u.ID in estimated or u.ID == "U3P":
            warn = " (correlation out of bounds; corrected below)" if u.ID == "U3K" else ""
            rows.append(dict(item=f"{u.ID} {type(u).__name__}", purchase_cost=u.purchase_cost,
                             installed_cost=u.installed_cost,
                             source="BioSTEAM correlation" + warn if u.installed_cost > 0 else
                             "no model cost; see estimate rows"))
    for name, value, source in result["capital_items"]:
        rows.append(dict(item=name, purchase_cost=float("nan"), installed_cost=value, source=source))
    rows += [
        dict(item="Installed equipment cost = DPI = TDC = FCI (SaBRe: no indirect factors)",
             purchase_cost=float("nan"), installed_cost=tea.FCI, source="SaBReTEA"),
        dict(item="Working capital", purchase_cost=float("nan"), installed_cost=tea.working_capital, source="5 % of FCI"),
        dict(item="Total capital investment", purchase_cost=float("nan"), installed_cost=tea.TCI, source=""),
    ]
    for r in rows:
        r["share_of_FCI"] = r["installed_cost"] / tea.FCI if r["installed_cost"] == r["installed_cost"] else float("nan")
    return rows


def _opex_table(sys, result):
    """Annual costs and their contribution to the MSP (deductible costs pass through 1:1)."""
    tea = result["tea"]
    hours = sys.operating_hours
    s = inv._streams(sys)
    h2_yr = float(s[_T["product"]].F_mass) * hours
    dry_yr = inv._dry_feed_kgph(sys) * hours
    rows = []

    def add(item, category, usd_yr, basis):
        rows.append(dict(item=item, category=category, USD_per_yr=usd_yr, USD_per_kg_H2=usd_yr / h2_yr,
                         USD_per_kg_dry=usd_yr / dry_yr, basis=basis))

    for ID, label in (("fresh_naoh_solid", "NaOH makeup"), ("lime", "Ca(OH)2"),
                      ("dissolution_water", "Process water"), ("att_sargassum_feed", "Sargassum feedstock")):
        add(label, "materials", s[ID].cost * hours, f"{s[ID].price:.6g} USD/kg")
    for agent in ("natural_gas", "low_pressure_steam", "cooling_water"):
        add(f"Utility: {agent}", "utilities",
            sum(hu.cost for hu in sys.heat_utilities if hu.agent.ID == agent) * hours, "BioSTEAM agent price")
    add("Electricity: modeled units", "utilities", sys.power_utility.cost * hours,
        f"{bst.PowerUtility.price} USD/kWh")
    for name, value in result["voc_items"]:
        add(name, "extra VOC", value, "att_tea.yaml")
    for ID in (*_T["prices"]["wastewater_streams"], *_T["prices"]["solid_waste_streams"]):
        add(f"Disposal: {ID}", "waste disposal", -s[ID].price * s[ID].F_mass * hours, f"{s[ID].price} USD/kg")
    add("CaCO3 cake: disposal (+) or net sales (-)", "CaCO3 cake", -s["caco3_cake"].price * s["caco3_cake"].F_mass * hours,
        f"{s['caco3_cake'].price:.6g} USD/kg wet cake")
    add("PSA off-gas handling", "off-gas", -s["u3_tail_gas"].price * s["u3_tail_gas"].F_mass * hours,
        f"{s['u3_tail_gas'].price:.6g} USD/kg")
    add("Fixed operating cost (4 % of FCI; labor, maintenance, overhead)", "FOC", tea.FOC, "tea.yaml")
    covered = sum(r["USD_per_kg_H2"] for r in rows)
    rows.append(dict(item="Capital recovery, taxes and financing (MSP remainder)", category="capital",
                     USD_per_yr=(result["msp"] - covered) * h2_yr, USD_per_kg_H2=result["msp"] - covered,
                     USD_per_kg_dry=(result["msp"] - covered) * h2_yr / dry_yr, basis="MSP - sum of costs"))
    rows.append(dict(item="MSP", category="total", USD_per_yr=result["msp"] * h2_yr, USD_per_kg_H2=result["msp"],
                     USD_per_kg_dry=result["msp"] * h2_yr / dry_yr, basis="SaBReTEA.solve_price"))
    return rows


def get_att_tea_sensitivity(sys, estimates):
    """One-at-a-time MSP sensitivity (att_tea.yaml)."""
    sens = _T["sensitivities"]
    base = evaluate_att_tea(sys, estimates)["msp"]
    cases = [("Baseline", {})]
    for f in sens["PSA_capex_factor"]:
        cases.append((f"PSA CAPEX x{f}", dict(psa_factor=f)))
    for v in sens["CaOH2_price"]:
        cases.append((f"Ca(OH)2 {v} USD/kg", dict(price_overrides={"CaOH2": v})))
    for v in sens["NaOH_price"]:
        cases.append((f"NaOH {v} USD/kg", dict(price_overrides={"NaOH": v})))
    for f in sens["natural_gas_price_factor"]:
        cases.append((f"Natural gas price x{f}", dict(ng_factor=f)))
    for f in sens["electricity_price_factor"]:
        cases.append((f"Electricity price x{f}", dict(elec_factor=f)))
    for f in sens["FCI_factor"]:
        cases.append((f"FCI x{f}", dict(fci_factor=f)))
    for name, v in sens["P1_power_kWh_per_t_dry"].items():
        cases.append((f"P1 power {v} kWh/t dry ({name})", dict(p1_kWh_per_t_dry=v)))
    cases.append(("P1 CAPEX: SaBRe press anchor", dict(p1_alternative_capex=True)))
    rows = []
    for name, kw in cases:
        msp = evaluate_att_tea(sys, estimates, **kw)["msp"]
        rows.append(dict(case=name, MSP_USD_per_kg_H2=msp, delta=msp - base))
    evaluate_att_tea(sys, estimates)  # restore baseline prices
    return rows


def _msp(sys, estimates, **kw):
    return evaluate_att_tea(sys, estimates, **kw)["msp"]


def get_att_caco3_cases(sys, estimates):
    """Case A (no CaCO3 sales) and Case B (marketable fraction x price x handling) for both lime prices."""
    c = _T["caco3_coproduct"]
    s = inv._streams(sys)
    dry = inv._dry_feed_kgph(sys)
    hours = sys.operating_hours
    caco3_kgph = float(s["caco3_cake"].imass["CaCO3"])
    rows = []
    for lime_label, lime in (("0.24 (original)", _T["prices"]["CaOH2"]["value"]),
                             ("0.28 (USGS MCS 2026, 2025e)", _T["prices"]["CaOH2_updated"]["value"])):
        po = {"CaOH2": float(lime)}
        ref = _msp(sys, estimates, price_overrides=po)
        rows.append(dict(lime_price=lime_label, case="Reference (cake neither sold nor disposed; commit 1473af06 basis)",
                         CaCO3_price_usd_per_t=float("nan"), handling_usd_per_t=float("nan"),
                         marketable_fraction=float("nan"), CaCO3_sold_t_per_yr=0.0,
                         MSP_USD_per_kg_H2=ref, delta_vs_case_A=float("nan")))
        case_a = _msp(sys, estimates, price_overrides=po, caco3=dict(fraction=0.0))
        rows.append(dict(lime_price=lime_label, case="Case A: no CaCO3 sales, whole cake disposed",
                         CaCO3_price_usd_per_t=float("nan"), handling_usd_per_t=float("nan"),
                         marketable_fraction=0.0, CaCO3_sold_t_per_yr=0.0, MSP_USD_per_kg_H2=case_a,
                         delta_vs_case_A=0.0))
        for price in c["price_usd_per_t_CaCO3"]:
            for handling in c["handling_usd_per_t_CaCO3"]:
                for f in c["marketable_fractions"]:
                    if f == 0.0:
                        continue
                    msp = _msp(sys, estimates, price_overrides=po,
                               caco3=dict(fraction=f, price_usd_per_t=price, handling_usd_per_t=handling))
                    label = ("Case B optimistic potential" if (price == max(c["price_usd_per_t_CaCO3"])
                                                               and handling == 0.0 and f == 1.0) else "Case B")
                    rows.append(dict(lime_price=lime_label, case=label, CaCO3_price_usd_per_t=price,
                                     handling_usd_per_t=handling, marketable_fraction=f,
                                     CaCO3_sold_t_per_yr=f * caco3_kgph * hours / 1e3,
                                     MSP_USD_per_kg_H2=msp, delta_vs_case_A=msp - case_a))
    _msp(sys, estimates)  # restore reference prices
    for r in rows:
        r["CaCO3_equivalent_kg_per_kg_dry"] = caco3_kgph / dry
        r["wet_cake_kg_per_kg_dry"] = float(s["caco3_cake"].F_mass) / dry
    return rows


def get_att_lime_price_cases(sys, estimates):
    rows = []
    for label, value in (("USGS MCS 2026, 2023 value (234.6 USD/t)", 0.2346),
                         ("Original reference 0.24 (MCS 2025, 2024e)", _T["prices"]["CaOH2"]["value"]),
                         ("USGS MCS 2026 2024 value (274.2 USD/t)", 0.2742),
                         ("Updated 0.28 (MCS 2026, 2025e)", _T["prices"]["CaOH2_updated"]["value"]),
                         ("High: plant price + delivery allowance", _T["prices"]["CaOH2"]["range"][1])):
        for case, kw in (("Reference (no cake cost)", {}), ("Case A (cake disposed)", dict(caco3=dict(fraction=0.0)))):
            msp = _msp(sys, estimates, price_overrides={"CaOH2": float(value)}, **kw)
            rows.append(dict(lime_price=label, USD_per_kg=float(value), case=case, MSP_USD_per_kg_H2=msp,
                             basis="average value at plant (f.o.b.); transport not included"
                             if "delivery" not in label else "assumed delivered"))
    ref = {r["case"]: r["MSP_USD_per_kg_H2"] for r in rows if r["USD_per_kg"] == _T["prices"]["CaOH2"]["value"]}
    for r in rows:
        r["delta_vs_0.24"] = r["MSP_USD_per_kg_H2"] - ref[r["case"]]
    _msp(sys, estimates)
    return rows


def get_att_p1_power_cases(sys, estimates):
    """P1 electricity: BioSTEAM ScrewPress basis vs SaBRe press basis (TEA and GWP deltas)."""
    from biorefineries.sabre.analyses import _att_lca as lca

    hours = sys.operating_hours
    dry = inv._dry_feed_kgph(sys)
    P1 = inv._units(sys)["P1"]
    aux_kW = sum(r["power_kW"] for r in estimates if r["power_kW"] == r["power_kW"])
    plant_kW = sys.power_utility.rate + aux_kW
    ef = float(lca._EF["electricity"]["value"])
    h2 = float(inv._streams(sys)["h2_product"].imass["H2"]) / dry
    base_msp = _msp(sys, estimates)
    cases = [("BioSTEAM ScrewPress: 37.2 kWh per t total wet feed (frozen model)", None, P1.power_utility.rate),
             ("Same 37.2 kWh applied per t dry solids", 37.2, 37.2 * dry / 1e3),
             ("SaBRe press: 5 kWh per t dry solids (preprocessing.yaml)", 5.0, 5.0 * dry / 1e3)]
    rows = []
    for name, value, kW in cases:
        msp = base_msp if value is None else _msp(sys, estimates, p1_kWh_per_t_dry=value)
        d_kWh_per_kg_dry = (kW - P1.power_utility.rate) / dry
        rows.append(dict(case=name, P1_kW=kW, P1_GWh_per_yr=kW * hours / 1e6,
                         plant_electricity_GWh_per_yr=(plant_kW - P1.power_utility.rate + kW) * hours / 1e6,
                         P1_kWh_per_t_dry=kW / dry * 1e3, MSP_USD_per_kg_H2=msp, delta_MSP=msp - base_msp,
                         delta_GWP_kgCO2e_per_kg_dry=d_kWh_per_kg_dry * ef,
                         delta_GWP_kgCO2e_per_kg_H2=d_kWh_per_kg_dry * ef / h2,
                         status="frozen baseline" if value is None else "alternative, not adopted"))
    _msp(sys, estimates)
    return rows


def get_att_offgas_cases(sys, estimates):
    tail = inv._streams(sys)["u3_tail_gas"]
    dry = inv._dry_feed_kgph(sys)
    hours = sys.operating_hours
    mol = {ID: float(tail.imol[ID]) for ID in ("H2", "CO2", "CH4", "CO") if tail.imol[ID] > 0}
    total_mol = sum(mol.values())
    rows = [dict(item="Off-gas flow", value=float(tail.F_mass) / dry, unit="kg/kg dry", MSP_USD_per_kg_H2=float("nan")),
            dict(item="Off-gas flow", value=float(tail.F_mass) * hours / 1e3, unit="t/yr", MSP_USD_per_kg_H2=float("nan"))]
    for ID, n in mol.items():
        rows.append(dict(item=f"{ID} in off-gas", value=n / total_mol, unit="mol fraction",
                         MSP_USD_per_kg_H2=float("nan")))
        rows.append(dict(item=f"{ID} in off-gas", value=float(tail.imass[ID]) / float(tail.F_mass),
                         unit="mass fraction", MSP_USD_per_kg_H2=float("nan")))
    base = _msp(sys, estimates)
    for cost in _T["offgas_handling_usd_per_t"]:
        msp = _msp(sys, estimates, offgas_usd_per_t=cost)
        rows.append(dict(item=f"Handling cost {cost} USD/t off-gas" + (" (reference)" if cost == 0 else " (placeholder)"),
                         value=cost * float(tail.F_mass) / 1e3 * hours / 1e6, unit="MUSD/yr",
                         MSP_USD_per_kg_H2=msp))
    # Upper-bound CH4 credit (tea.yaml biomethane price; purification not costed).
    ch4_price = float(_PRICE["biomethane_mmbtu"]["baseline"]) * float(_PRICE["biomethane_mmbtu"]["mmbtu_per_kg"])
    ch4_frac = float(tail.imass["CH4"]) / float(tail.F_mass) if tail.F_mass else 0.0
    if ch4_frac > 0.0:
        credit = -ch4_frac * ch4_price * 1e3
        msp = _msp(sys, estimates, offgas_usd_per_t=credit)
        rows.append(dict(item=f"CH4 credit at tea.yaml biomethane {_PRICE['biomethane_mmbtu']['baseline']} USD/MMBtu "
                              "(upper bound; purification not costed)", value=-credit * float(tail.F_mass) / 1e3 * hours / 1e6,
                         unit="MUSD/yr revenue", MSP_USD_per_kg_H2=msp))
    rows.append(dict(item="Note", value=float("nan"), unit=_T["offgas_note"], MSP_USD_per_kg_H2=base))
    _msp(sys, estimates)
    return rows


def get_att_cost_year_comparison(sys):
    """Reference CEPCI vs approximate 2024 CEPCI (equipment only); original results untouched."""
    cy = _T["cost_year"]
    original = bst.CE
    rows = []
    try:
        for label, CE in ((f"CEPCI {cy['reference_CE']} (2017, reference)", cy["reference_CE"]),
                          (f"CEPCI {cy['comparison_CE']} (~2024, approximate)", cy["comparison_CE"])):
            bst.CE = CE
            sys.simulate()  # re-costs at this CEPCI (flows reconverge to the same state)
            est = inv.get_att_cost_estimates(sys)
            r = evaluate_att_tea(sys, est)
            rows.append(dict(case=label, CE=CE, FCI_MUSD=r["tea"].FCI / 1e6, TCI_MUSD=r["tea"].TCI / 1e6,
                             FOC_MUSD_per_yr=r["tea"].FOC / 1e6, MSP_USD_per_kg_H2=r["msp"],
                             note=cy["reference_note"] if CE == cy["reference_CE"] else cy["comparison_note"]))
    finally:
        bst.CE = original
        sys.simulate()
    rows[1]["delta_MSP"] = rows[1]["MSP_USD_per_kg_H2"] - rows[0]["MSP_USD_per_kg_H2"]
    return rows


def _same_flows(sys, fingerprint, rtol=1e-8):
    now = [float(x) for st in (*sys.feeds, *sys.products) for x in st.mass]
    return all(abs(a - b) <= rtol * max(abs(b), 1e-6) for a, b in zip(now, fingerprint))


def _checks(sys, result, fingerprint):
    tea = result["tea"]
    scale = inv.get_att_reference_scale()
    hours = sys.operating_hours
    gas = [hu for hu in sys.heat_utilities if hu.agent.ID == "natural_gas"]
    fuel = sum(hu.duty for hu in gas) / 1e3 / _BURNER_EFFICIENCY * hours
    ng_cost = sum(hu.cost for hu in gas) * hours + next(v for n, v in result["voc_items"] if n.startswith("Natural"))
    h2 = float(inv._streams(sys)["h2_product"].imass["H2"]) / inv._dry_feed_kgph(sys)
    unchanged = _same_flows(sys, fingerprint)
    rows = [
        ("Dry feed [t/d] = 15000 x (1 - 0.8673)", scale["dry_feed_t_per_day"], 15000 * (1 - 0.8673)),
        ("Operating hours = 330 d x 24 h", hours, 7920.0),
        ("TEA operating days x 24 = system hours", tea.operating_days * 24, hours),
        ("FCI = unit installed + extra capital", tea.FCI,
         sum(u.installed_cost for u in sys.units) + tea.extra_installed_cost),
        ("Natural gas cost = fuel (duty/0.90) x USD/MJ", ng_cost, fuel * _ng_usd_per_MJ()),
        ("H2 product = model yield x daf x PSA [kg/kg dry]", h2,
         inv._units(sys)["U2"]._model_gas_yield_mmol_per_g_daf["H2"]
         * float(inv._units(sys)["U2"]._daf_sargassum_kgph) / inv._dry_feed_kgph(sys) * 2.01588 / 1e3 * 0.9),
        ("NPV at MSP", tea.NPV, 0.0),
        ("Off-gas and CaCO3 revenue (baseline)", inv._streams(sys)["u3_tail_gas"].price
         + inv._streams(sys)["caco3_cake"].price, 0.0),
        ("Frozen model flows unchanged", float(unchanged), 1.0),
    ]
    out = []
    for name, value, expected in rows:
        # NPV: solver tolerance relative to the total capital investment.
        tol = 1e-6 * max(1.0, abs(expected)) if name != "NPV at MSP" else 1e-6 * tea.TCI
        if name.startswith("H2 product"):
            tol = 1e-4
        out.append(dict(check=name, value=value, expected=expected,
                        status="PASS" if abs(value - expected) <= tol else "FAIL"))
    return out


def export_att_tea(out_dir="att_tea"):
    """Baseline MSP, CAPEX/OPEX tables, sensitivity and checks to CSV/Excel."""
    import os
    import pandas as pd

    sys = create_att_tea_system()
    fingerprint = [float(x) for st in (*sys.feeds, *sys.products) for x in st.mass]
    estimates = inv.get_att_cost_estimates(sys)
    result = evaluate_att_tea(sys, estimates)
    scale = inv.get_att_reference_scale()
    hours = sys.operating_hours
    h2_yr = float(inv._streams(sys)["h2_product"].F_mass) * hours
    tea = result["tea"]
    summary = [
        ("H2 MSP", result["msp"], "USD/kg H2"),
        ("H2 production", h2_yr / 1e3, "t/yr"),
        ("Plant capacity", scale["dry_feed_t_per_day"], "dry t/d (15000 wet t/d, 330 d/yr)"),
        ("Fixed capital investment (FCI)", tea.FCI / 1e6, "MUSD"),
        ("Total capital investment (TCI)", tea.TCI / 1e6, "MUSD"),
        ("Variable operating cost (VOC)", tea.VOC / 1e6, "MUSD/yr"),
        ("Fixed operating cost (FOC)", tea.FOC / 1e6, "MUSD/yr"),
        ("Coproduct revenue (CaCO3, CH4, off-gas)", 0.0, "MUSD/yr (baseline: none)"),
        ("Equipment cost basis", float("nan"), _T["cost_year_note"]),
        ("Financial basis", float("nan"),
         ", ".join(f"{k}={_FIN[k]}" for k in ("IRR", "duration", "depreciation", "income_tax", "WC_over_FCI",
                                              "finance_fraction", "finance_interest", "foc_frac_of_fci"))),
    ]
    assumptions = [dict(item=k, value=v["value"], range=str(v.get("range", "")), source=v["source"])
                   for k, v in _T["prices"].items() if isinstance(v, dict)]
    assumptions += [dict(item=k, value=float("nan"), range="", source=v)
                    for k, v in _T["prices"].items() if k.endswith("_note")]
    assumptions += [
        dict(item="Sargassum price", value=_PRICE["sargassum"]["baseline"], range=str(_PRICE["sargassum"]["range"]),
             source="tea.yaml (USD/kg wet)"),
        dict(item="Wastewater disposal", value=_PRICE["disposal_wastewater"]["baseline"], range="",
             source="tea.yaml (USD/kg)"),
        dict(item="Solid disposal", value=_PRICE["disposal_solid"]["baseline"], range="", source="tea.yaml (USD/kg wet)"),
        dict(item="Natural gas", value=_ng_usd_per_MJ() * 1e3, range="", source="USD/GJ LHV (BioSTEAM default)"),
        dict(item="LP steam", value=bst.HeatUtility.get_agent("low_pressure_steam").regeneration_price, range="",
             source="USD/kmol (BioSTEAM default)"),
        dict(item="Electricity", value=bst.PowerUtility.price, range="", source="USD/kWh (BioSTEAM default)"),
    ]
    tables = {
        "00_summary": [dict(item=a, value=b, unit=c) for a, b, c in summary],
        "01_price_and_capital_assumptions": assumptions,
        "02_capex": _capex_table(sys, result),
        "03_opex_and_msp_breakdown": _opex_table(sys, result),
    }
    checks = _checks(sys, result, fingerprint)
    tables["04_msp_sensitivity"] = get_att_tea_sensitivity(sys, estimates)
    caco3 = get_att_caco3_cases(sys, estimates)
    tables["06_caco3_cases"] = caco3
    tables["07_lime_price_cases"] = get_att_lime_price_cases(sys, estimates)
    tables["08_P1_electricity_cases"] = get_att_p1_power_cases(sys, estimates)
    tables["09_offgas_handling"] = get_att_offgas_cases(sys, estimates)
    tables["10_cost_year_comparison"] = get_att_cost_year_comparison(sys)
    tables["11_limitations"] = [dict(limitation=x) for x in _T["limitations"]]
    # Headline cases (original lime price 0.24 USD/kg).
    pick = {(r["lime_price"], r["case"], r["CaCO3_price_usd_per_t"], r["handling_usd_per_t"],
             r["marketable_fraction"]): r["MSP_USD_per_kg_H2"] for r in caco3}
    lime0 = "0.24 (original)"
    headline = [
        ("MSP Reference (no CaCO3 revenue, cake not costed; commit 1473af06)", result["msp"]),
        ("MSP Case A (no CaCO3 sales, cake disposed at tea.yaml price)",
         next(r["MSP_USD_per_kg_H2"] for r in caco3 if r["lime_price"] == lime0 and r["case"].startswith("Case A"))),
    ]
    for f in _T["caco3_coproduct"]["marketable_fractions"][1:]:
        headline.append((f"MSP Case B: {f:.0%} marketable, 250 USD/t, no handling cost",
                         pick[(lime0, "Case B optimistic potential" if f == 1.0 else "Case B", 250.0, 0.0, f)]))
    tables["00_summary"] = [dict(item=a, value=b, unit="USD/kg H2") for a, b in headline] + tables["00_summary"]
    _msp(sys, estimates)  # leave the reference case applied
    same = _same_flows(sys, fingerprint)
    checks.append(dict(check="Frozen model flows unchanged after all cases (rel. 1e-8)", value=float(same),
                       expected=1.0, status="PASS" if same else "FAIL"))
    tables["05_checks"] = checks
    os.makedirs(out_dir, exist_ok=True)
    with pd.ExcelWriter(os.path.join(out_dir, "att_tea_msp.xlsx")) as writer:
        for name, rows in tables.items():
            df = pd.DataFrame(rows)
            df.to_csv(os.path.join(out_dir, f"{name}.csv"), index=False)
            df.to_excel(writer, sheet_name=name[:31], index=False)
    return tables
