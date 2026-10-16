"""
Key conversions, material usage, heat duties and energy return of the ATT
cases (ATT-only and ATT-integration), in the format of the UCLA energy and
exergy slides (per kg dry seaweed):

* conversions against theoretical values (H2 yield, carbon capture, NaOH
  loading, causticization, lime use, NaOH recovery);
* material usage per kg dry seaweed and per kg H2;
* heat duty by unit operation and by physical origin (heating duties before
  heat integration, MJ per kg dry seaweed), split into low-grade
  (<= 100 C) and high-grade heat;
* external versus internal heat (heat recovered by BioSTEAM's HXN and heat
  from burning the PSA tail gas, which is biomass derived) and the energy
  return on investment (EROI = H2 energy out / energy in).

Basis of "dry seaweed": the dry solids fed to the plant (fresh Sargassum
for the ATT-only case, the dry presscake for the integration case).
Written by ``analyses/att_key_metrics.py`` to ``results/``.
"""
import biosteam as bst
import pandas as pd

from biorefineries.sabre.analyses.att import inventory as inv
from biorefineries.sabre.analyses.att import lca
from biorefineries.sabre.units._att import _SARGASSUM_DRY_IDS
from biorefineries.sabre.utils import load_assumptions

__all__ = ("build_att_key_metrics", "CONFIGURATIONS")

CONFIGURATIONS = {"att_only": "ATT-only (wet Sargassum)", "integrated": "ATT-integration (presscake)"}
LOW_GRADE_T_K = 373.15            # <= 100 C = low-grade (waste-heat usable), as in the slides
_NA_MW, _NA2CO3_MW = 39.99711, 105.9888
_ELECTRICITY_MJ_PER_KWH = 3.6     # primary-energy convention of att.inventory
_ATT = load_assumptions("att.yaml")["att"]


def simulate(configuration, hxn):
    from biorefineries.sabre.systems._att_system import create_att_system

    scale = inv.get_att_reference_scale(configuration)
    sys = inv._simulate(create_att_system(dry_sargassum_kgph=scale["dry_feed_kgph"], configuration=configuration,
                                          heat_exchanger_network=hxn), scale["dry_feed_kgph"])
    sys.operating_hours = scale["operating_hours_per_year"]
    return sys


def _lhv_MJ_per_kg(ID):
    c = bst.settings.chemicals[ID]
    return float(c.LHV) / float(c.MW) / 1e3


def _hhv_MJ_per_kg(ID):
    c = bst.settings.chemicals[ID]
    return float(c.HHV) / float(c.MW) / 1e3


# --------------------------------------------------------------------------
# Conversions and material usage
# --------------------------------------------------------------------------

def get_conversions(sys):
    u = inv._units(sys)
    s = inv._streams(sys)
    U2, C1 = u["U2"], u["C1"]
    feed, (gas, residue) = U2.ins[0], U2.outs
    daf = float(U2._daf_sargassum_kgph)            # kg/h
    dry = inv._dry_feed_kgph(sys)
    h2_kg = float(s["h2_product"].imass["H2"])
    atoms = U2._organic_atoms_kmolph               # kmol/h of the organic feed
    C, H, O = (atoms.get(k, 0.0) for k in "CHO")
    e_feed = 4 * C + H - 2 * O                     # kmol e-/h (reference CO2, H2O)
    per_g = 1e3 / daf                              # kmol/h -> mmol/g daf
    h2_mol = float(gas.imol["H2"]); ch4 = float(gas.imol["CH4"]); co = float(gas.imol["CO"])
    co2_gas = float(gas.imol["CO2"])
    carbonate = float(residue.imol["Na2CO3"] - feed.imol["Na2CO3"])
    c_out = {"CO2 in gas": co2_gas, "CO2 captured as Na2CO3": carbonate, "CH4": ch4, "CO": co}
    c_unassigned = C - sum(c_out.values())
    naoh_gross = float(feed.imol["NaOH"])
    co2_total = co2_gas + carbonate
    makeup = float(s["fresh_naoh_solid"].imass["NaOH"])
    gross_kg = float(feed.imass["NaOH"])
    ledger = {r["item"]: r["value"] for r in inv.get_att_sodium_calcium_ledger(sys)}
    f = _NA_MW * 2 / _NA2CO3_MW                    # kg NaOH-eq per kg Na2CO3
    losses = {
        "CaCO3 cake (F2)": ledger["Loss: NaOH in CaCO3 cake"] + f * ledger["Loss: Na2CO3 in CaCO3 cake"],
        "Ash/char cake (F1)": f * ledger["Loss: Na2CO3 in ash/char cake"],
        "Liquor purge": ledger["Loss: NaOH in liquor purge"] + f * ledger["Loss: Na2CO3 in liquor purge"],
    }
    loss_total = sum(losses.values())
    lime = float(s["lime"].imass["CaOH2"])
    lime_stoich = float(C1.ins[0].imol["Na2CO3"]) * 74.093 / 1.0   # kg Ca(OH)2 for all Na2CO3 into C1 (1 mol / mol)
    caco3 = float(C1.outs[0].imass["CaCO3"])
    feed_HHV = float(U2.feed_HHV_MJ_per_kg_daf) * daf                # MJ/h
    gas_HHV = sum(float(gas.imass[i]) * _hhv_MJ_per_kg(i) for i in ("H2", "CH4", "CO"))
    h2_HHV = h2_kg * _hhv_MJ_per_kg("H2")
    rows = []

    def add(group, metric, value, unit, theoretical=None, basis="", note=""):
        frac = (value / theoretical) if (theoretical not in (None, 0) and isinstance(value, (int, float))) else None
        rows.append(dict(group=group, metric=metric, value=value, unit=unit, theoretical=theoretical,
                         theoretical_basis=basis, fraction_of_theoretical=frac, note=note))

    add("H2", "Available electrons in the feed organics (C, H, O)", e_feed * per_g, "mmol e-/g daf", note="4C + H - 2O")
    add("H2", "H2 yield at the U2 outlet", h2_mol * per_g, "mmol/g daf", e_feed / 2 * per_g,
        "all reducing power to H2 (C -> CO2)", "specified (experimental team)")
    add("H2", "H2 yield at the U2 outlet", float(gas.imass["H2"]) / daf, "kg/kg daf",
        e_feed / 2 * 2.016 / daf, "all reducing power to H2", "")
    add("H2", "H2 product per kg dry seaweed", h2_kg / dry, "kg/kg dry", e_feed / 2 * 2.016 / dry,
        "all reducing power to H2, 100 % PSA recovery", "includes the PSA recovery loss")
    add("H2", "PSA H2 recovery", float(_ATT["gas_treatment"]["psa_h2_recovery"]), "-", 1.0, "ideal", "specified")
    add("H2", "Reducing power in H2 / feed", 2 * h2_mol / e_feed, "-", 1.0, "all electrons to H2")
    add("H2", "Reducing power in CH4 + CO / feed", (8 * ch4 + 2 * co) / e_feed, "-")
    add("H2", "Reducing power unidentified / feed", 1 - (2 * h2_mol + 8 * ch4 + 2 * co) / e_feed, "-",
        note="not assigned to any identified product")
    add("Energy", "Gas carriers (H2, CH4, CO) HHV / feed HHV", gas_HHV / feed_HHV, "-")
    add("Energy", "H2 product HHV / feed HHV", h2_HHV / feed_HHV, "-")
    for k, v in c_out.items():
        add("Carbon", f"Organic C to {k}", v / C, "-")
    add("Carbon", "Organic C not assigned (residual C)", c_unassigned / C, "-")
    add("Carbon", "CO2 captured as carbonate / CO2 generated", carbonate / co2_total, "-", 1.0, "full capture")
    add("NaOH", "NaOH loading (gross, incl. recycled)", gross_kg / daf, "kg/kg daf", 2 * co2_total * _NA_MW / daf,
        "2 NaOH per CO2 generated (full capture)")
    add("NaOH", "NaOH -> Na2CO3 conversion in U2", 2 * carbonate / naoh_gross, "-", 1.0, "full conversion")
    add("NaOH", "Causticization conversion in C1", float(C1.conversion), "-", 1.0, "full conversion", "specified")
    add("NaOH", "Liquor recycle fraction (SP1)", float(_ATT["downstream"]["whole_liquor_recycle_fraction"]), "-", 1.0,
        "no purge", "specified")
    add("NaOH", "Effective NaOH recovery = 1 - makeup / gross", 1 - makeup / gross_kg, "-", 1.0, "no losses")
    add("NaOH", "NaOH makeup per kg dry seaweed", makeup / dry, "kg/kg dry", 0.0, "no losses")
    add("NaOH", "NaOH makeup per kg H2", makeup / h2_kg, "kg/kg H2", 0.0, "no losses")
    for k, v in losses.items():
        add("NaOH", f"NaOH loss share: {k}", v / loss_total if loss_total else 0.0, "-", note="NaOH equivalent")
    add("Ca(OH)2", "Ca(OH)2 fed / stoichiometric for the Na2CO3 into C1", lime / lime_stoich, "-", 1.0, "stoichiometric",
        "specified excess 1.1")
    add("Ca(OH)2", "Ca(OH)2 per kg H2", lime / h2_kg, "kg/kg H2", carbonate * 74.093 / h2_kg,
        "Ca(OH)2 for the carbonate formed in U2 (regeneration of the NaOH consumed)")
    add("Ca(OH)2", "CaCO3 formed per kg Ca(OH)2 fed (utilization)", caco3 * 74.093 / 100.087 / lime, "-", 1.0, "full utilization")
    water_in_u2 = float(feed.imass["Water"])
    add("Water", "Water fed to U2 per kg daf", water_in_u2 / daf, "kg/kg daf", note="experiment: 7.2 kg steam per kg daf (flow-through)")
    add("Water", "Fresh dissolution water per kg H2", float(s["dissolution_water"].F_mass) / h2_kg, "kg/kg H2")
    add("Water", "Condensate recycled to D1 / D1 demand",
        float(s["condensate_to_D1"].F_mass) / (float(s["condensate_to_D1"].F_mass) + float(s["dissolution_water"].F_mass)), "-")
    return rows


def get_material_usage(sys):
    s = inv._streams(sys)
    dry = inv._dry_feed_kgph(sys)
    h2 = float(s["h2_product"].imass["H2"])
    util = {r["item"]: r["per_kg_dry"] for r in inv.get_att_purchased_utilities(sys, inv.get_att_cost_estimates(sys))}
    rows = []

    def add(kind, item, kgph, note=""):
        rows.append(dict(kind=kind, item=item, kg_per_kg_dry=kgph / dry, kg_per_kg_H2=kgph / h2, note=note))

    f = s["att_sargassum_feed"]
    add("input", "Sargassum, dry", dry); add("input", "Sargassum, water as received", float(f.imass["Water"]))
    add("input", "NaOH makeup", float(s["fresh_naoh_solid"].imass["NaOH"]))
    add("input", "Ca(OH)2", float(s["lime"].imass["CaOH2"]))
    add("input", "Fresh water (D1 makeup)", float(s["dissolution_water"].F_mass))
    add("input", "Drying air", float(s["dryer_air"].F_mass))
    add("output", "H2 product", h2)
    if "biostimulant_juice" in s:
        add("output", "Biostimulant juice (P1)", float(s["biostimulant_juice"].F_mass), "coproduct, zero price")
    add("output", "PSA tail gas (CO2 mostly), burned in U2", float(s["u3_tail_gas"].F_mass))
    add("output", "  of which CO2", float(s["u3_tail_gas"].imass["CO2"]) if "CO2" in s["u3_tail_gas"].chemicals else float(s["u3_tail_gas"].imass["CarbonDioxide"]))
    add("output", "CaCO3 cake (wet)", float(s["caco3_cake"].F_mass))
    add("output", "Ash/char cake (wet)", float(s["ash_residue_cake"].F_mass))
    add("output", "Liquor purge", float(s["liquor_purge"].F_mass))
    add("output", "Wastewater (U3D water + excess condensate)",
        float(s["u3_dryer_removed_water"].F_mass + s["excess_condensate"].F_mass))
    add("output", "Dryer exhaust water", float(s["dryer_exhaust"].imass["Water"]))
    for k, unit in (("U2 natural gas: fuel input (LHV)", "MJ"), ("LP steam: utility heat incl. 5 % loss", "MJ"),
                    ("Cooling water: heat removed", "MJ"), ("Electricity: total", "kWh")):
        v = util[k]
        rows.append(dict(kind="utility", item=f"{k} [{unit}]", kg_per_kg_dry=v, kg_per_kg_H2=v / (h2 / dry), note=f"{unit}/kg"))
    return rows


# --------------------------------------------------------------------------
# Heat
# --------------------------------------------------------------------------

def _u2_low_share(U2):
    """Share of U2's feed-heating duty that is needed at <= 100 C (liquid heating, vaporization at 100 C, solids to 100 C)."""
    feed = U2.ins[0]
    T_in, T_out = float(feed.T), float(U2.target_temperature_K)
    st = U2._make_thermal_state
    w_low = float(st(feed, ("Water",), "g", LOW_GRADE_T_K).H - st(feed, ("Water",), "l", T_in).H)
    sensible = [(_SARGASSUM_DRY_IDS, "s"), (("NaOH",), "l")]
    s_low = sum(float(st(feed, ids, ph, LOW_GRADE_T_K).H - st(feed, ids, ph, T_in).H) for ids, ph in sensible)
    return w_low, s_low


def get_heat(sys):
    """Heating duties [kJ/h] by unit and by physical origin, utility basis (incl. the 5 % heat-loss allowance)."""
    u = inv._units(sys)
    dry = inv._dry_feed_kgph(sys)
    water = bst.settings.chemicals["Water"]
    U2, C1, EC1, D0, U3D = u["U2"], u["C1"], u["EC1"], u["D0"], u["U3D"]

    def heating(unit):
        return sum(hu.duty for hu in unit.heat_utilities if hu.duty > 0.0)

    unit_heat = {"D0": heating(D0), "U2": heating(U2), "C1": heating(C1), "EC1": heating(EC1), "U3D": heating(U3D)}
    loss = {"U2": float(U2._heat_loss_kJph), "C1": float(C1._heat_loss_kJph), "EC1": float(EC1._heat_loss_kJph)}
    # D0: latent heat of the evaporated water; the rest is sensible (solids, air)
    d0_latent = float(D0.design_results["Evaporation"]) * float(water.Hvap(D0.T)) / float(water.MW)
    d0_sensible = unit_heat["D0"] - d0_latent
    # U2 breakdown
    hf, aq = float(U2._feed_Hf_HHV_correction_kJph), float(U2._aqueous_feed_correction_kJph)
    u2_rxn_all = float(U2._reaction_and_product_state_kJph)
    naoh_solution = -aq                               # NaOH heat of solution released in M1, not recovered
    reaction = u2_rxn_all - naoh_solution             # reaction + product state (+ feed Hf re-referenced to the HHV)
    u2_water = float(U2._water_heating_duty_kJph)
    u2_sens = float(U2._dry_sargassum_heating_duty_kJph + U2._naoh_heating_duty_kJph + U2._other_heating_duty_kJph)
    w_low, s_low = _u2_low_share(U2)
    u2_process = float(U2._heat_duty_kJph)
    u2_low_proc = w_low + s_low
    u2_low_share = u2_low_proc / u2_process
    c1_process, ec1_process = float(C1._heat_duty_kJph), float(EC1._heat_duty_kJph)
    u3d_heat = unit_heat["U3D"]

    origin = {   # step -> (kJ/h, low-grade kJ/h)
        "Reaction enthalpy (U2)": (reaction, 0.0),
        "NaOH heat of solution (not recovered)": (naoh_solution, 0.0),
        "Water heating and vaporization (U2)": (u2_water, w_low),
        "Sensible heat of solids and NaOH (U2)": (u2_sens, s_low),
        "Water evaporation, feed dryer (D0)": (d0_latent, d0_latent),
        "Sensible heat in the dryer (D0)": (d0_sensible, d0_sensible),
        "Causticizing (C1)": (c1_process, c1_process),
        "Water evaporation, NaOH concentrator (EC1)": (ec1_process, ec1_process),
        "Gas-drying regeneration (U3D)": (u3d_heat, 0.0),
        "Heat losses": (sum(loss.values()),
                        loss["U2"] * u2_low_share + loss["C1"] + loss["EC1"]),
    }
    # Informational, not in the model's energy balance: Na2CO3 heat of solution (-26.7 kJ/mol) in D1
    na2co3_kmol = float(u["D1"].ins[0].imol["Na2CO3"])
    dissolution_estimate = -26.7e3 * na2co3_kmol                    # kJ/kmol x kmol/h = kJ/h
    total = sum(v for v, _ in origin.values())
    assert abs(total - sum(unit_heat.values())) < 1e-6 * total, (total, sum(unit_heat.values()))
    low = sum(l for _, l in origin.values())
    return dict(unit=unit_heat, origin=origin, total=total, dissolution_estimate_kJph=dissolution_estimate, low=low, high=total - low, dry=dry,
                water_handling=sum(origin[k][0] for k in origin if k.startswith("Water")) )


def get_energy_supply(sys_no, sys_hxn, heat):
    """External versus internal heat (kJ/h) and the EROI, from the system without and with the HXN."""
    s = inv._streams(sys_hxn)
    burner = float(lca._LCA["natural_gas"]["burner_efficiency"]); boiler = float(lca._LCA["natural_gas"]["boiler_efficiency"])
    steam = lambda sys: sum(hu.duty for hu in sys.heat_utilities if hu.agent.ID.endswith("steam"))
    ng = lambda sys: sum(hu.duty for hu in sys.heat_utilities if hu.agent.ID == "natural_gas")
    offset = inv.get_att_tail_gas_offset(sys_hxn)
    tail_delivered = offset["offset_MJph"] * 1e3 * burner      # heat delivered by the tail gas, kJ/h
    recovered = steam(sys_no) - steam(sys_hxn)                  # process heat recovered (steam avoided), kJ/h
    low = heat["low"]; high = heat["high"]; total = heat["total"]
    # recovered heat serves low-grade sinks (D0, EC1, C1); tail gas fires U2 (high-grade)
    ext_low_no, ext_high_no = low, high
    ext_low = low - recovered; ext_high = high - tail_delivered
    h2_kg = float(s["h2_product"].imass["H2"])
    h2_MJ = h2_kg * _lhv_MJ_per_kg("H2")
    dry = heat["dry"]
    def electricity_MJ(sys):
        util = {r["item"]: r["per_kg_dry"] for r in inv.get_att_purchased_utilities(sys, inv.get_att_cost_estimates(sys))}
        return util["Electricity: total"] * dry * _ELECTRICITY_MJ_PER_KWH

    elec_MJ, elec_MJ_no = electricity_MJ(sys_hxn), electricity_MJ(sys_no)

    def fuel(sys, tail):   # primary fuel (LHV, MJ/h) for the heat purchased
        return (ng(sys) / 1e3 / burner - (offset["offset_MJph"] if tail else 0.0)) + steam(sys) / 1e3 / boiler

    scen = {
        "No heat integration, tail gas not used": dict(ext_low=ext_low_no, ext_high=ext_high_no, int_hxn=0.0, int_tail=0.0,
                                                       fuel=fuel(sys_no, False), elec=elec_MJ_no),
        "Tail gas burned in U2": dict(ext_low=ext_low_no, ext_high=ext_high_no - tail_delivered, int_hxn=0.0,
                                      int_tail=tail_delivered, fuel=fuel(sys_no, True), elec=elec_MJ_no),
        "Tail gas + HXN": dict(ext_low=ext_low, ext_high=ext_high, int_hxn=recovered, int_tail=tail_delivered,
                               fuel=fuel(sys_hxn, True), elec=elec_MJ),
    }
    for k, v in scen.items():
        v["ext_total"] = v["ext_low"] + v["ext_high"]
        v["EROI_heat_delivered"] = h2_MJ * 1e3 / v["ext_total"]           # H2 LHV out / external heat in (slide definition)
        v["EROI_fuel"] = h2_MJ / v["fuel"]
        v["EROI_fuel_plus_electricity"] = h2_MJ / (v["fuel"] + v["elec"])
    return scen, dict(h2_MJph=h2_MJ, recovered_kJph=recovered, tail_delivered_kJph=tail_delivered, total_kJph=total)


def build_att_key_metrics():
    out = {}
    for cfg in CONFIGURATIONS:
        sys_no = simulate(cfg, hxn=False)
        conv, mat = get_conversions(sys_no), get_material_usage(sys_no)
        heat = get_heat(sys_no)
        sys_h = simulate(cfg, hxn=True)
        scen, extra = get_energy_supply(sys_no, sys_h, heat)
        conv_h, mat_h = get_conversions(sys_h), get_material_usage(sys_h)
        out[cfg] = dict(conversions=conv_h, materials=mat_h, heat=heat, scenarios=scen, extra=extra)
    return out
