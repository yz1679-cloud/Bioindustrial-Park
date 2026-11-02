# Bioindustrial-Park: BioSTEAM's Premier Biorefinery Models and Results
# Copyright (C) 2026-, Yu Zhou,
#                      Yalin Li <mailto.yalin.li@gmail.com>
#
# This module is under the UIUC open-source license. See
# github.com/BioSTEAMDevelopmentGroup/biosteam/blob/master/LICENSE.txt
# for license details.

"""
Preliminary TEA of the frozen ATT model: minimum H2 selling price (MSP).

Reuses SaBReTEA (tea.yaml financial assumptions; FCI = installed equipment
cost; FOC = 4 % of FCI) through a thin subclass that adds only what the
frozen unit models do not carry:

- extra installed capital: only the P1 BioSTEAM-ScrewPress alternative and the
  PSA cost-factor sensitivity (all equipment is costed inside the units: the
  U2 vessel and furnace, the C1 tank, the EC1 evaporator, condenser and vacuum
  system, the PSA in U3P and the reciprocating compressor U3K);
- extra annual operating cost: purge-neutralization H2SO4 and the natural-gas cost adjustment that
  prices fuel = U2 duty / burner efficiency (as in the LCA) instead of the
  BioSTEAM agent flow.

Material and disposal prices are set on the frozen streams; utilities use
BioSTEAM agent prices (steam and cooling-water prices cover their
generation, so boiler gas and tower electricity are not priced again).
Prices and capital assumptions: data/att_tea.yaml.

Scenario basis: ``create_att_tea_system()`` is the ATT S1 system (scenarios.create, 5029.17 kg dry/h) and the
standard TEA is ``evaluate_att_tea(sys, **scenarios.tea_config(spec))`` (waste lime at 0 USD/kg, CaCO3 cakes
disposed unless att_tea.yaml caco3_sales is enabled). ``evaluate_att_tea`` without those keywords prices the lime
at the fresh-lime price (att_tea.yaml prices.CaOH2).
"""
import biosteam as bst

from biorefineries.ATT._tea import SaBReTEA
from biorefineries.ATT.analyses import inventory as inv
from biorefineries.ATT.analyses import scenarios as scen
from biorefineries.ATT.analyses.lca import _h2so4_kgph, caco3_saleable_fraction
from biorefineries.ATT.utils import OPERATING_DAYS_PER_YEAR, load_assumptions

__all__ = (
    "ATTTEA",
    "create_att_tea_system",
    "evaluate_att_tea",
    "get_att_tea_sensitivity",
    "caco3_cake_price",
    "get_att_caco3_cases",
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

    def __init__(self, *args, extra_installed_cost=0.0, extra_VOC=0.0, foc_fixed=0.0, **kwargs):
        self.extra_installed_cost = float(extra_installed_cost)
        self.extra_VOC = float(extra_VOC)
        self.foc_fixed = float(foc_fixed)     # fixed annual FOC added to foc_frac_of_fci x FCI (S2 labor); 0 in S1
        super().__init__(*args, **kwargs)

    def _FOC(self, FCI):
        return super()._FOC(FCI) + self.foc_fixed

    def _DPI(self, installed_equipment_cost):
        return installed_equipment_cost + self.extra_installed_cost

    @property
    def VOC(self):
        return super().VOC + self.extra_VOC


def create_att_tea_system(scenario="att_s1", lime_recycle=None):
    """
    Simulated system of an ATT scenario (scenarios.create; default ATT S1 at its capacity). ``lime_recycle`` is
    kept for backward compatibility and must agree with the scenario.
    """
    if scenario not in scen.ALL_SCENARIOS:
        raise ValueError(f"unknown ATT scenario {scenario!r} (expected one of {tuple(scen.ALL_SCENARIOS)})")
    spec = scen.ALL_SCENARIOS[scenario]
    if lime_recycle is not None and bool(lime_recycle) != (spec["lime"] == "recycled"):
        raise ValueError(f"lime_recycle={lime_recycle} contradicts {scenario} (lime: {spec['lime']})")
    return scen.create(spec)


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


def caco3_sales_accounting(sys, price_usd_per_metric_ton, saleable_fraction=1.0, streams=("caco3_cake",),
                           disposal_of_sold_caco3=False, dispose_non_caco3_mass=True,
                           saleable_fraction_by_stream=None, **_):
    """
    CaCO3 byproduct sales per cake stream (att_tea.yaml caco3_sales) [per hour]: the saleable fraction of the
    CaCO3 COMPONENT is sold at the price; the cake mass that is not sold CaCO3 (moisture, excess Ca(OH)2,
    entrained NaOH/Na2CO3, unsold CaCO3) is disposed at tea.yaml disposal_solid (dispose_non_caco3_mass). Returns
    {ID: dict(...)} for the streams that are system products, with the net stream price [USD/kg wet cake].
    """
    s = inv._streams(sys)
    products = {p.ID for p in sys.products}
    disposal = float(_PRICE["disposal_solid"]["baseline"])        # negative = cost
    out = {}
    for ID in streams:
        if ID not in s or ID not in products or not float(s[ID].F_mass):
            continue
        cake = s[ID]
        caco3 = float(cake.imass["CaCO3"])
        fraction = caco3_saleable_fraction(ID, dict(streams=streams, saleable_fraction=saleable_fraction,
                                                    saleable_fraction_by_stream=saleable_fraction_by_stream))
        sold = fraction * caco3
        disposed = ((float(cake.F_mass) - caco3 if dispose_non_caco3_mass else 0.0)   # moisture and impurities
                    + (caco3 - sold)                                                   # unsold CaCO3
                    + (sold if disposal_of_sold_caco3 else 0.0))
        revenue = sold * price_usd_per_metric_ton / 1e3                    # USD/h
        disposal_usd = -disposal * disposed                                # USD/h, cost
        out[ID] = dict(wet_kgph=float(cake.F_mass), dry_kgph=float(cake.F_mass) - float(cake.imass["Water"]),
                       caco3_kgph=caco3, sold_caco3_kgph=sold, disposed_kgph=disposed, revenue_usd_ph=revenue,
                       disposal_usd_ph=disposal_usd, price_usd_per_kg=(revenue - disposal_usd) / float(cake.F_mass))
    return out


def _apply_prices(sys, p, cake_price=None, offgas_usd_per_t=0.0, feedstock_usd_per_wet_t=None):
    s = inv._streams(sys)
    s["att_sargassum_feed"].price = (float(_PRICE["sargassum"]["baseline"]) if feedstock_usd_per_wet_t is None
                                     else float(feedstock_usd_per_wet_t) / 1e3)
    s["fresh_naoh_solid"].price = p["NaOH"]
    # The price is per kg of Ca(OH)2; the waste carbide lime stream also carries water and impurities.
    for ID in ("lime", "scrubber_lime"):
        if ID in s:
            fraction = float(s[ID].imass["CaOH2"]) / float(s[ID].F_mass) if float(s[ID].F_mass) > 0.0 else 1.0
            s[ID].price = p["CaOH2"] * fraction
    s["dissolution_water"].price = p["process_water"]
    if "biostimulant_juice" in s:
        s["biostimulant_juice"].price = float(_T["prices"]["juice"])
    if "slaking_water" in s:
        s["slaking_water"].price = p["process_water"]
    if "scrubber_makeup_water" in s:
        s["scrubber_makeup_water"].price = p["process_water"]
    if "f2_wash_water" in s:
        s["f2_wash_water"].price = p["process_water"]
    for ID in _T["prices"]["wastewater_streams"]:
        if ID in s:
            s[ID].price = float(_PRICE["disposal_wastewater"]["baseline"])
    for ID in _T["prices"]["solid_waste_streams"]:
        if ID in s:
            s[ID].price = float(_PRICE["disposal_solid"]["baseline"])
    s["caco3_cake"].price = float(_T["prices"]["CaCO3_cake"]) if cake_price is None else float(cake_price)
    if "u3_tail_gas" in s:
        s["u3_tail_gas"].price = float(_T["prices"]["offgas"]) - float(offgas_usd_per_t) / 1e3
    s[_T["product"]].price = 0.0


def _ng_usd_per_MJ():
    agent = bst.HeatUtility.get_agent("natural_gas")
    return agent.regeneration_price / (bst.Chemical("CH4").LHV / 1e3)


def _biosteam_screwpress(sys):
    """BioSTEAM ScrewPress on the P1 feed (alternative to the municipal-press basis); None without P1."""
    units = inv._units(sys)
    if "P1" not in units:
        return None
    from biorefineries.ATT.system import get_att_press_retention

    P1 = units["P1"]
    with inv._scratch_flowsheet():
        unit = bst.ScrewPress("P1_biosteam_screwpress", ins=P1.ins[0].copy(),
                              split={ID: r for ID, r in get_att_press_retention().items()},
                              moisture_content=1.0 - P1.cake_solids_wt_frac)
        unit.simulate()
    return unit


def _capital_items(sys, estimates, psa_factor=1.0, p1_biosteam_screwpress=False):
    """Extra installed capital beyond the frozen unit models [USD]."""
    u = inv._units(sys)
    items = [(f"{r['item']} (estimate)", r["installed_cost"], r["method"])
             for r in estimates if r["installed_cost"] == r["installed_cost"]]
    if psa_factor != 1.0 and "U3P" in u:
        items.append((f"PSA capital x{psa_factor} (adjustment of the U3P cost)",
                      (psa_factor - 1.0) * u["U3P"].installed_cost, "att_tea.yaml sensitivities.PSA_capex_factor"))
    alt = _biosteam_screwpress(sys) if p1_biosteam_screwpress else None
    if alt is not None:
        items.append(("P1: BioSTEAM ScrewPress replaces municipal press (difference)",
                      alt.installed_cost - u["P1"].installed_cost, "bst.ScrewPress cost correlation (Perry), parallel units"))
    return items


def _voc_items(sys, estimates, p, ng_factor=1.0, elec_factor=1.0, p1_biosteam_screwpress=False):
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
    offset = inv.get_att_tail_gas_offset(sys)
    if offset["offset_MJph"]:
        items.append(("Natural gas displaced by PSA tail gas (burned in the U2 burner)",
                      -offset["offset_MJph"] * _ng_usd_per_MJ() * ng_factor * hours))
    if elec_factor != 1.0:
        items.append(("Electricity price change (unit power)",
                      (elec_factor - 1.0) * sys.power_utility.rate * elec * hours))
    alt = _biosteam_screwpress(sys) if p1_biosteam_screwpress else None
    if alt is not None:
        items.append(("P1 power: BioSTEAM ScrewPress replaces municipal press (difference)",
                      (alt.power_utility.rate - inv._units(sys)["P1"].power_utility.rate) * elec * elec_factor * hours))
    return items


def evaluate_att_tea(sys, estimates=None, price_overrides=None, psa_factor=1.0, ng_factor=1.0, elec_factor=1.0,
                     fci_factor=1.0, p1_biosteam_screwpress=False, caco3=None,
                     offgas_usd_per_t=0.0, feedstock_usd_per_wet_t=None, caco3_sales=None,
                     operating_hours=None, extra_capital=(), extra_voc=(), foc_frac_of_fci=None, foc_fixed=0.0):
    """
    Build the TEA for one case and solve the H2 MSP with SaBReTEA's DCF.

    caco3: None keeps the reference treatment (cake neither sold nor costed);
    otherwise keyword arguments of caco3_cake_price (Case A: fraction 0).
    caco3_sales: None, or the keyword arguments of caco3_sales_accounting
    (att_tea.yaml caco3_sales): CaCO3 component sold, the rest of each listed
    cake disposed; it sets the price of those streams (after ``caco3``).
    feedstock_usd_per_wet_t: delivered Sargassum cost (collection and
    transport); None uses tea.yaml price.sargassum.baseline (0).
    ATT S2 (marine) hooks, all neutral by default: operating_hours (None:
    tea.yaml operating days x 24); extra_capital [(name, USD, basis)] added
    AFTER fci_factor (not multiplied); extra_voc [(name, USD/yr)];
    foc_frac_of_fci (None: tea.yaml) and foc_fixed [USD/yr] for FOC.
    """
    if estimates is None:
        estimates = inv.get_att_cost_estimates(sys)
    hours = OPERATING_DAYS_PER_YEAR * 24.0 if operating_hours is None else float(operating_hours)
    sys.operating_hours = hours
    p = _prices(price_overrides)
    cake_price = None if caco3 is None else caco3_cake_price(sys, **caco3)
    _apply_prices(sys, p, cake_price, offgas_usd_per_t, feedstock_usd_per_wet_t)
    sales = {} if caco3_sales is None else caco3_sales_accounting(sys, **caco3_sales)
    for ID, r in sales.items():
        inv._streams(sys)[ID].price = r["price_usd_per_kg"]
    capital = _capital_items(sys, estimates, psa_factor, p1_biosteam_screwpress)
    voc = _voc_items(sys, estimates, p, ng_factor, elec_factor, p1_biosteam_screwpress) + list(extra_voc)
    installed_units = sum(u.installed_cost for u in sys.units)
    if fci_factor != 1.0:      # itemized so that the capital tables sum to the FCI
        capital.append((f"FCI factor x{fci_factor:g}: adjustment of the process installed capital",
                        (fci_factor - 1.0) * (installed_units + sum(v for _, v, _ in capital)), "fci_factor"))
    capital += list(extra_capital)
    extra_capital_usd = sum(v for _, v, _ in capital)
    tea = ATTTEA(
        system=sys, IRR=_FIN["IRR"], duration=tuple(_FIN["duration"]), depreciation=_FIN["depreciation"],
        income_tax=_FIN["income_tax"], operating_days=hours / 24.0,
        construction_schedule=tuple(_FIN["construction_schedule"]), WC_over_FCI=_FIN["WC_over_FCI"],
        finance_interest=_FIN["finance_interest"], finance_years=_FIN["finance_years"],
        finance_fraction=_FIN["finance_fraction"], lang_factor=None, startup_months=_FIN["startup_months"],
        startup_FOCfrac=_FIN["startup_FOCfrac"], startup_VOCfrac=_FIN["startup_VOCfrac"],
        startup_salesfrac=_FIN["startup_salesfrac"],
        foc_frac_of_fci=_FIN["foc_frac_of_fci"] if foc_frac_of_fci is None else float(foc_frac_of_fci),
        extra_installed_cost=extra_capital_usd, extra_VOC=sum(v for _, v in voc), foc_fixed=foc_fixed,
    )
    product = inv._streams(sys)[_T["product"]]
    # The functional unit is 1 kg H2. Without a PSA the product gas also holds CH4 and CO (no credit), so the
    # price solved per kg of gas is restated per kg of H2 it contains (identical with a PSA: pure H2).
    gas_msp = tea.solve_price(product)
    msp = gas_msp * float(product.F_mass) / float(product.imass["H2"])
    product.price = gas_msp
    return dict(tea=tea, msp=msp, capital_items=capital, voc_items=voc, prices=p, estimates=estimates,
                caco3=caco3, caco3_sales=sales)


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------

def _capex_table(sys, result):
    tea = result["tea"]
    rows = []
    estimated = {r["unit"] for r in result["estimates"]}
    for u in sys.units:
        if u.installed_cost > 0.0 or u.ID in estimated:
            warn = ""
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
    h2_yr = float(s[_T["product"]].imass["H2"]) * hours
    dry_yr = inv._dry_feed_kgph(sys) * hours
    rows = []

    def add(item, category, usd_yr, basis):
        rows.append(dict(item=item, category=category, USD_per_yr=usd_yr, USD_per_kg_H2=usd_yr / h2_yr,
                         USD_per_kg_dry=usd_yr / dry_yr, basis=basis))

    for ID, label in (("fresh_naoh_solid", "NaOH makeup"), ("lime", "Ca(OH)2"),
                      ("dissolution_water", "Process water"), ("att_sargassum_feed", "Sargassum feedstock")):
        add(label, "materials", s[ID].cost * hours, f"{s[ID].price:.6g} USD/kg")
    if "f2_wash_water" in s:
        add("Process water (F2 washing)", "materials", s["f2_wash_water"].cost * hours,
            f"{s['f2_wash_water'].price:.6g} USD/kg fresh wash water")
    if "slaking_water" in s:
        add("Process water", "materials", s["slaking_water"].cost * hours, f"{s['slaking_water'].price:.6g} USD/kg (slaking)")
    if "scrubber_lime" in s:
        add("Ca(OH)2", "materials", s["scrubber_lime"].cost * hours, f"{s['scrubber_lime'].price:.6g} USD/kg (CO2 scrubber)")
        add("Process water", "materials", s["scrubber_makeup_water"].cost * hours,
            f"{s['scrubber_makeup_water'].price:.6g} USD/kg (CO2 scrubber makeup)")
    if "biostimulant_juice" in s:
        add("Biostimulant juice transfer (coproduct)", "juice", -s["biostimulant_juice"].cost * hours,
            f"{s['biostimulant_juice'].price:.6g} USD/kg")
    for agent in ("natural_gas", "low_pressure_steam", "cooling_water"):
        add(f"Utility: {agent}", "utilities",
            sum(hu.cost for hu in sys.heat_utilities if hu.agent.ID == agent) * hours, "BioSTEAM agent price")
    add("Electricity: modeled units", "utilities", sys.power_utility.cost * hours,
        f"{bst.PowerUtility.price} USD/kWh")
    for name, value in result["voc_items"]:
        add(name, "extra VOC", value, "att_tea.yaml")
    sales = result.get("caco3_sales", {})
    for ID, r in sales.items():            # net stream price split into its two parts (sum = -price x mass)
        add(f"CaCO3 sales: {ID}", "CaCO3 sales", -r["revenue_usd_ph"] * hours,
            f"{r['sold_caco3_kgph']:.6g} kg/h CaCO3 sold")
        add(f"CaCO3 cake disposal (non-sold mass): {ID}", "CaCO3 cake", r["disposal_usd_ph"] * hours,
            f"{r['disposed_kgph']:.6g} kg/h disposed")
    for ID in (*_T["prices"]["wastewater_streams"], *_T["prices"]["solid_waste_streams"]):
        if ID not in {p.ID for p in sys.products} or ID in sales:
            continue
        add(f"Disposal: {ID}", "waste disposal", -s[ID].price * s[ID].F_mass * hours, f"{s[ID].price} USD/kg")
    if s["caco3_cake"] in sys.products and "caco3_cake" not in sales:   # with the lime recycle it is internal
        add("CaCO3 cake: disposal (+) or net sales (-)", "CaCO3 cake", -s["caco3_cake"].price * s["caco3_cake"].F_mass * hours,
            f"{s['caco3_cake'].price:.6g} USD/kg wet cake")
    tail = inv._tail_gas(sys)
    add("PSA off-gas handling", "off-gas", -tail.price * tail.F_mass * hours, f"{tail.price:.6g} USD/kg")
    add("Fixed operating cost (4 % of FCI; labor, maintenance, overhead)", "FOC", tea.FOC, "tea.yaml")
    covered = sum(r["USD_per_kg_H2"] for r in rows)
    rows.append(dict(item="Capital recovery, taxes and financing (MSP remainder)", category="capital",
                     USD_per_yr=(result["msp"] - covered) * h2_yr, USD_per_kg_H2=result["msp"] - covered,
                     USD_per_kg_dry=(result["msp"] - covered) * h2_yr / dry_yr, basis="MSP - sum of costs"))
    rows.append(dict(item="MSP", category="total", USD_per_yr=result["msp"] * h2_yr, USD_per_kg_H2=result["msp"],
                     USD_per_kg_dry=result["msp"] * h2_yr / dry_yr, basis="SaBReTEA.solve_price"))
    return rows


def _with(base, **kw):
    """evaluate_att_tea keywords: the scenario ``base`` (scenarios.tea_config) updated by a case (prices merged)."""
    out = dict(base or {})
    prices = {**(out.get("price_overrides") or {}), **(kw.pop("price_overrides", None) or {})}
    out.update(kw, price_overrides=prices or None)
    return out


def get_att_tea_sensitivity(sys, estimates, base=None):
    """One-at-a-time MSP sensitivity (att_tea.yaml) around ``base`` (scenarios.tea_config; None = reference)."""
    sens = _T["sensitivities"]
    base_kw = base
    base = evaluate_att_tea(sys, estimates, **_with(base_kw))["msp"]
    cases = [("Baseline", {})]
    for f in (sens["PSA_capex_factor"] if "U3P" in inv._units(sys) else ()):      # only with a PSA
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
    if "P1" in inv._units(sys) and sens.get("P1_biosteam_screwpress"):
        cases.append(("P1: BioSTEAM ScrewPress (power and CAPEX)", dict(p1_biosteam_screwpress=True)))
    rows = []
    for name, kw in cases:
        msp = evaluate_att_tea(sys, estimates, **_with(base_kw, **kw))["msp"]
        rows.append(dict(case=name, MSP_USD_per_kg_H2=msp, delta=msp - base))
    evaluate_att_tea(sys, estimates, **_with(base_kw))  # restore baseline prices
    return rows


def _msp(sys, estimates, base=None, **kw):
    return evaluate_att_tea(sys, estimates, **_with(base, **kw))["msp"]


CASE_BASIS = ("waste lime (ATT S1), F2 cake only, single-stream CaCO3 treatment (evaluate_att_tea caco3=); "
              "not the att_tea.yaml caco3_sales option")


def get_att_caco3_cases(sys, estimates):
    """
    Case A (no CaCO3 sales, whole F2 cake disposed) and Case B (marketable fraction x price x handling) on the ATT S1
    basis (waste lime). Leaves a non-scenario treatment applied (re-apply the scenario TEA afterwards).
    """
    c = _T["caco3_coproduct"]
    s = inv._streams(sys)
    dry = inv._dry_feed_kgph(sys)
    hours = sys.operating_hours
    caco3_kgph = float(s["caco3_cake"].imass["CaCO3"])
    po = {"CaOH2": 0.0}                     # waste lime (scenarios.tea_config)
    rows = []
    case_a = _msp(sys, estimates, price_overrides=po, caco3=dict(fraction=0.0))
    rows.append(dict(case="Case A: no CaCO3 sales, whole cake disposed",
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
                rows.append(dict(case=label, CaCO3_price_usd_per_t=price,
                                 handling_usd_per_t=handling, marketable_fraction=f,
                                 CaCO3_sold_t_per_yr=f * caco3_kgph * hours / 1e3,
                                 MSP_USD_per_kg_H2=msp, delta_vs_case_A=msp - case_a))
    _msp(sys, estimates)  # restore reference prices
    for r in rows:
        r["CaCO3_equivalent_kg_per_kg_dry"] = caco3_kgph / dry
        r["wet_cake_kg_per_kg_dry"] = float(s["caco3_cake"].F_mass) / dry
        r["basis"] = CASE_BASIS
    return rows


def get_att_p1_power_cases(sys, estimates, base=None):
    """
    P1 (fresh-Sargassum case): municipal biosolids press (adopted) vs BioSTEAM
    ScrewPress, power, installed cost, MSP and GWP deltas. Empty without P1.
    """
    from biorefineries.ATT.analyses import lca

    units = inv._units(sys)
    if "P1" not in units:
        return []
    hours = sys.operating_hours
    dry = inv._dry_feed_kgph(sys)
    P1 = units["P1"]
    alt = _biosteam_screwpress(sys)
    ef = float(lca._EF["electricity"]["value"])
    h2 = float(inv._streams(sys)["h2_product"].imass["H2"]) / dry
    base_msp = _msp(sys, estimates, base)
    wet_t = float(P1.ins[0].F_mass) / 1e3
    rows = []
    for name, unit, adopted in (("Municipal biosolids press (HUBER-type; 5 kWh/t dry; 3.1 MUSD per 0.953 dry t/h)", P1, True),
                                ("BioSTEAM ScrewPress (Perry; 37.2 kWh/t total wet feed)", alt, False)):
        kW = unit.power_utility.rate
        msp = base_msp if adopted else _msp(sys, estimates, base, p1_biosteam_screwpress=True)
        d_kWh_per_kg_dry = (kW - P1.power_utility.rate) / dry
        rows.append(dict(case=name, P1_kW=kW, P1_kWh_per_t_dry=kW / dry * 1e3, P1_kWh_per_t_wet=kW / wet_t,
                         P1_GWh_per_yr=kW * hours / 1e6, P1_installed_MUSD=unit.installed_cost / 1e6,
                         MSP_USD_per_kg_H2=msp, delta_MSP=msp - base_msp,
                         delta_GWP_kgCO2e_per_kg_H2=d_kWh_per_kg_dry * ef / h2,
                         status="adopted" if adopted else "alternative, not adopted"))
    _msp(sys, estimates, base)
    return rows


def get_att_offgas_cases(sys, estimates, base=None):
    tail = inv._tail_gas(sys)
    dry = inv._dry_feed_kgph(sys)
    hours = sys.operating_hours
    if not tail.F_mass:      # no PSA, no off-gas
        return [dict(item="Off-gas flow", value=0.0, unit="kg/kg dry (no PSA)",
                     MSP_USD_per_kg_H2=_msp(sys, estimates, base))]
    mol = {ID: float(tail.imol[ID]) for ID in ("H2", "CO2", "CH4", "CO") if tail.imol[ID] > 0}
    total_mol = sum(mol.values())
    rows = [dict(item="Off-gas flow", value=float(tail.F_mass) / dry, unit="kg/kg dry", MSP_USD_per_kg_H2=float("nan")),
            dict(item="Off-gas flow", value=float(tail.F_mass) * hours / 1e3, unit="t/yr", MSP_USD_per_kg_H2=float("nan"))]
    for ID, n in mol.items():
        rows.append(dict(item=f"{ID} in off-gas", value=n / total_mol, unit="mol fraction",
                         MSP_USD_per_kg_H2=float("nan")))
        rows.append(dict(item=f"{ID} in off-gas", value=float(tail.imass[ID]) / float(tail.F_mass),
                         unit="mass fraction", MSP_USD_per_kg_H2=float("nan")))
    base_msp = _msp(sys, estimates, base)
    for cost in _T["offgas_handling_usd_per_t"]:
        msp = _msp(sys, estimates, base, offgas_usd_per_t=cost)
        rows.append(dict(item=f"Handling cost {cost} USD/t off-gas" + (" (reference)" if cost == 0 else " (placeholder)"),
                         value=cost * float(tail.F_mass) / 1e3 * hours / 1e6, unit="MUSD/yr",
                         MSP_USD_per_kg_H2=msp))
    # Upper-bound CH4 credit (tea.yaml biomethane price; purification not costed).
    ch4_price = float(_PRICE["biomethane_mmbtu"]["baseline"]) * float(_PRICE["biomethane_mmbtu"]["mmbtu_per_kg"])
    ch4_frac = float(tail.imass["CH4"]) / float(tail.F_mass) if tail.F_mass else 0.0
    if ch4_frac > 0.0:
        credit = -ch4_frac * ch4_price * 1e3
        msp = _msp(sys, estimates, base, offgas_usd_per_t=credit)
        rows.append(dict(item=f"CH4 credit at tea.yaml biomethane {_PRICE['biomethane_mmbtu']['baseline']} USD/MMBtu "
                              "(upper bound; purification not costed)", value=-credit * float(tail.F_mass) / 1e3 * hours / 1e6,
                         unit="MUSD/yr revenue", MSP_USD_per_kg_H2=msp))
    rows.append(dict(item="Note", value=float("nan"), unit=_T["offgas_note"], MSP_USD_per_kg_H2=base_msp))
    _msp(sys, estimates, base)
    return rows


def get_att_cost_year_comparison(sys, base=None):
    """Reference CEPCI vs approximate 2024 CEPCI (equipment only), around ``base``; original results untouched."""
    cy = _T["cost_year"]
    original = bst.CE
    rows = []
    try:
        for label, CE in ((f"CEPCI {cy['reference_CE']} (2020, reference)", cy["reference_CE"]),
                          (f"CEPCI {cy['comparison_CE']} (~2024, approximate)", cy["comparison_CE"])):
            bst.CE = CE
            sys.simulate()  # re-costs at this CEPCI (flows reconverge to the same state)
            est = inv.get_att_cost_estimates(sys)
            r = evaluate_att_tea(sys, est, **_with(base))
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


def _configuration(sys):
    return "fresh_sargassum" if "P1" in inv._units(sys) else "presscake"


def _checks(sys, result, fingerprint, scenario="att_s1"):
    """Accounting checks; ``scenario``: the ATT scenario whose capacity is expected (None = the reference scale)."""
    tea = result["tea"]
    scale = (inv.get_att_reference_scale(_configuration(sys)) if scenario is None
             else scen.scale(scen.ALL_SCENARIOS[scenario]))
    s = inv._streams(sys)
    sales = result.get("caco3_sales") or {}
    if sales:      # the net cake value is booked once, on the stream prices set by caco3_sales_accounting
        cake_value = sum(s[ID].price * float(s[ID].F_mass) for ID in sales)
        cake_expected = sum(r["revenue_usd_ph"] - r["disposal_usd_ph"] for r in sales.values())
    else:
        cake_value = s["caco3_cake"].price
        cake_expected = (float(_T["prices"]["CaCO3_cake"]) if result.get("caco3") is None
                         else caco3_cake_price(sys, **result["caco3"]))
    hours = sys.operating_hours
    gas = [hu for hu in sys.heat_utilities if hu.agent.ID == "natural_gas"]
    fuel = sum(hu.duty for hu in gas) / 1e3 / _BURNER_EFFICIENCY * hours
    ng_cost = sum(hu.cost for hu in gas) * hours + next(v for n, v in result["voc_items"] if n.startswith("Natural"))
    h2 = float(inv._streams(sys)["h2_product"].imass["H2"]) / inv._dry_feed_kgph(sys)
    unchanged = _same_flows(sys, fingerprint)
    rows = [
        (f"Dry feed [t/d] = {scale.get('scenario', 'reference scale')} capacity",
         inv._dry_feed_kgph(sys) * 24.0 / 1e3, scale["dry_feed_t_per_day"]),
        ("Operating hours = 330 d x 24 h", hours, 7920.0),
        ("TEA operating days x 24 = system hours", tea.operating_days * 24, hours),
        ("FCI = unit installed + extra capital", tea.FCI,
         sum(u.installed_cost for u in sys.units) + tea.extra_installed_cost),
        ("Natural gas cost = fuel (duty/0.90) x USD/MJ", ng_cost, fuel * _ng_usd_per_MJ()),
        ("H2 product = model yield x daf x PSA recovery [kg/kg dry]", h2,
         inv._units(sys)["U2"]._model_gas_yield_mmol_per_g_daf["H2"]
         * float(inv._units(sys)["U2"]._daf_sargassum_kgph) / inv._dry_feed_kgph(sys) * 2.01588 / 1e3 * (float(inv._ATT["gas_treatment"]["psa_h2_recovery"]) if "U3P" in inv._units(sys) else 1.0)),
        ("NPV at MSP", tea.NPV, 0.0),
        ("Off-gas revenue (none)", inv._tail_gas(sys).price, 0.0),
        ("CaCO3 cake value = configured treatment, counted once [USD/h or USD/kg]", cake_value, cake_expected),
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


def export_att_tea(out_dir=None, scenario="att_s1"):
    """
    MSP, CAPEX/OPEX tables, sensitivity and checks of an ATT scenario (default ATT S1, with its waste-lime and
    CaCO3-sales assumptions from scenarios.tea_config) to CSV/Excel (default results/full_scale/tea). The SaBRe
    The Case A/B table (06) is a CaCO3-treatment sensitivity (single-stream CaCO3 mechanism, waste lime).
    """
    import os
    import pandas as pd
    from biorefineries.ATT.analyses.paths import output_dir

    out_dir = os.fspath(out_dir or output_dir("tea"))

    spec = scen.SCENARIOS[scenario]          # land-based scenarios only (ATT S2: analyses/att_s2_marine.py)
    base = scen.tea_config(spec)
    sys = create_att_tea_system(scenario)
    fingerprint = [float(x) for st in (*sys.feeds, *sys.products) for x in st.mass]
    estimates = inv.get_att_cost_estimates(sys)
    result = evaluate_att_tea(sys, estimates, **base)
    scale = scen.scale(spec)
    hours = sys.operating_hours
    h2_yr = float(inv._streams(sys)["h2_product"].imass["H2"]) * hours
    tea = result["tea"]
    sales = result["caco3_sales"]
    summary = [
        ("H2 MSP", result["msp"], f"USD/kg H2 ({spec['short']})"),
        ("H2 production", h2_yr / 1e3, "t/yr"),
        ("Plant capacity", scale["dry_feed_t_per_day"], f"dry t/d ({scale['basis']}; 330 d/yr)"),
        ("Fixed capital investment (FCI)", tea.FCI / 1e6, "MUSD"),
        ("Total capital investment (TCI)", tea.TCI / 1e6, "MUSD"),
        ("Variable operating cost (VOC)", tea.VOC / 1e6, "MUSD/yr"),
        ("Fixed operating cost (FOC)", tea.FOC / 1e6, "MUSD/yr"),
        ("CaCO3 sales revenue", sum(r["revenue_usd_ph"] for r in sales.values()) * hours / 1e6,
         f"MUSD/yr ({base['caco3_sales']['price_usd_per_metric_ton']:g} USD/t CaCO3; booked once on the cake prices)"
         if sales else "MUSD/yr (no CaCO3 sales)"),
        ("Coproduct revenue (CH4, off-gas)", 0.0, "MUSD/yr (none)"),
        ("Scenario", float("nan"), spec["label"]),
        ("Lime", float("nan"), f"{spec['lime']} Ca(OH)2 at {inv._streams(sys)['lime'].price:g} USD/kg"),
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
    checks = _checks(sys, result, fingerprint, scenario)
    s = inv._streams(sys)
    checks += [dict(check=a, value=b, expected=d, status="PASS" if abs(b - d) <= 1e-9 * max(1.0, abs(d)) else "FAIL")
               for a, b, d in (
                   ("Lime price = scenario assumption [USD/kg]", s["lime"].price,
                    0.0 if spec["lime"] == "waste" else _prices()["CaOH2"]),
                   ("CaCO3 sales streams = att_tea.yaml caco3_sales (system products)", float(len(sales)),
                    float(sum(ID in s and s[ID] in sys.products for ID in (base["caco3_sales"] or {}).get("streams", ())))),
               )]
    tables["04_msp_sensitivity"] = get_att_tea_sensitivity(sys, estimates, base)
    caco3 = get_att_caco3_cases(sys, estimates)
    tables["06_caco3_cases"] = caco3
    tables["08_P1_electricity_cases"] = get_att_p1_power_cases(sys, estimates, base)
    tables["09_offgas_handling"] = get_att_offgas_cases(sys, estimates, base)
    tables["10_cost_year_comparison"] = get_att_cost_year_comparison(sys, base)
    tables["11_limitations"] = [dict(limitation=x) for x in _T["limitations"]]
    # CaCO3-treatment headline cases (waste lime, single-stream mechanism), after the scenario rows.
    pick = {(r["case"], r["CaCO3_price_usd_per_t"], r["handling_usd_per_t"],
             r["marketable_fraction"]): r["MSP_USD_per_kg_H2"] for r in caco3}
    cases = [("MSP Case A (waste lime, no CaCO3 sales, F2 cake disposed at tea.yaml price)",
              next(r["MSP_USD_per_kg_H2"] for r in caco3 if r["case"].startswith("Case A")))]
    for f in _T["caco3_coproduct"]["marketable_fractions"][1:]:
        cases.append((f"MSP Case B: {f:.0%} marketable, 250 USD/t, no handling cost",
                      pick[("Case B optimistic potential" if f == 1.0 else "Case B", 250.0, 0.0, f)]))
    tables["00_summary"] += [dict(item=a, value=b, unit=f"USD/kg H2 ({CASE_BASIS})") for a, b in cases]
    _msp(sys, estimates, base)  # leave the scenario TEA applied
    same = _same_flows(sys, fingerprint)
    checks.append(dict(check="Frozen model flows unchanged after all cases (rel. 1e-8)", value=float(same),
                       expected=1.0, status="PASS" if same else "FAIL"))
    tables["05_checks"] = checks
    os.makedirs(out_dir, exist_ok=True)
    with pd.ExcelWriter(os.path.join(out_dir, "att_tea_msp.xlsx"), engine="openpyxl") as writer:
        for name, rows in tables.items():
            df = pd.DataFrame(rows)
            df.to_csv(os.path.join(out_dir, f"{name}.csv"), index=False)
            df.to_excel(writer, sheet_name=name[:31], index=False)
    return tables
