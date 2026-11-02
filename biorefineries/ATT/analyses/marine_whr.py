# Bioindustrial-Park: BioSTEAM's Premier Biorefinery Models and Results
# Copyright (C) 2026-, Yu Zhou,
#                      Yalin Li <mailto.yalin.li@gmail.com>
#
# This module is under the UIUC open-source license. See
# github.com/BioSTEAMDevelopmentGroup/biosteam/blob/master/LICENSE.txt
# for license details.

"""
ATT Scenario 2 (att_s2): marine engine waste heat recovery (WHR) for shipboard ATT, as an ACCOUNTING MODULE on top
of the unchanged ATT S1 process (same units, chemistry and balances). Data: data/marine_whr.yaml; design basis:
docs/ATT_S2_DESIGN_BASIS.md.

1. ``engine_sources``: heat of the main engine at a load (exhaust -> economizer steam; charge air -> hot-water loop;
   jacket water -> hot-water loop), bounded by the source temperatures (exhaust minimum outlet / acid dew point,
   economizer pinch, loop approach temperatures) and a delivery efficiency.
2. ``s1_heat_sinks``: the purchased heating of the simulated S1 system AFTER its heat exchanger network (HXN): the
   residual LP steam of D0, C1, EC1 (HXN life cycles) and U3D, and an optional U2 feed preheater (sensible heating
   of the U2 feed; the 500 C reaction heat is never a sink).
3. ``allocate``: temperature-feasible source -> sink assignment, lowest-grade source first, coldest sink first;
   a source is used once, a sink never receives more than its purchased duty, partial sensible coverage from the
   cold end. Saving = assigned heat (it replaces purchased utility heat 1:1).
4. ``whr_equipment``: itemized incremental equipment (area-based exchanger costs, BioSTEAM pumps, drum and
   allowances) and the pump electricity.
All flows are those of the simulated system (kW at its dry feed rate).
"""
from math import log

import biosteam as bst
from biosteam.units.heat_exchange import compute_floating_head_purchase_cost

from biorefineries.ATT.analyses import inventory as inv
from biorefineries.ATT.utils import load_assumptions

__all__ = ("load_whr_config", "engine_sources", "s1_heat_sinks", "allocate", "whr_equipment", "evaluate_whr",
           "SOURCE_IDS")

SOURCE_IDS = ("jacket", "scavenge", "exhaust")      # allocation order: lowest grade first
_K = 273.15


def load_whr_config():
    return load_assumptions("marine_whr.yaml")["marine_whr"]


def _load_point(cfg, load):
    points = {float(k): v for k, v in cfg["engine"]["load_points"].items()}
    if load in points:
        return points[load]
    lo = max((k for k in points if k <= load), default=None)
    hi = min((k for k in points if k >= load), default=None)
    if lo is None or hi is None:
        raise ValueError(f"engine load {load} outside the load_points {sorted(points)}")
    w = (load - lo) / (hi - lo)
    return {k: (1 - w) * points[lo][k] + w * points[hi][k] for k in points[lo]}


def engine_sources(cfg=None, load=None, enabled=SOURCE_IDS, overrides=None):
    """
    Heat sources of the main engine [kW]: gross (to the reference temperature), recoverable (temperature-limited)
    and delivered (x delivery efficiency). ``overrides``: {key: value} for 'T_exhaust_C', 'T_charge_air_C',
    'specific_flow_kg_per_kWh', 'delivery_efficiency' (all sources).
    """
    cfg = load_whr_config() if cfg is None else cfg
    o = dict(overrides or {})
    eng = cfg["engine"]
    load = float(eng["load_fraction"] if load is None else load)
    shaft_kW = float(cfg["vessel"]["rated_power_kW"]) * load
    fuel_kW = shaft_kW / float(eng["shaft_efficiency"])
    active = load >= float(eng["min_load_for_recovery"])
    point = _load_point(cfg, load) if active else {"T_exhaust_C": float("nan"), "T_charge_air_C": float("nan")}
    T_exh = float(o.get("T_exhaust_C", point["T_exhaust_C"]))
    T_ca = float(o.get("T_charge_air_C", point["T_charge_air_C"]))
    ex = eng["exhaust"]
    m_exh = float(o.get("specific_flow_kg_per_kWh", ex["specific_flow_kg_per_kWh"])) * shaft_kW / 3600.0   # kg/s
    m_fuel = fuel_kW / float(eng["fuel_LHV_kJ_per_kg"])
    st = cfg["steam_system"]
    Water = bst.settings.chemicals["Water"]
    T_sat = float(Water.Tsat(float(st["pressure_bar_abs"]) * 1e5)) - _K
    sources = {}

    # Exhaust gas -> economizer -> steam (latent at T_sat)
    T_out = max(float(ex["min_outlet_C"]), T_sat + float(st["pinch_K"]))
    cp = float(ex["cp_kJ_per_kgK"])
    rec = m_exh * cp * max(T_exh - T_out, 0.0) if active else 0.0
    eff = float(o.get("delivery_efficiency", st["delivery_efficiency"]))
    sources["exhaust"] = dict(
        source="exhaust", kind="steam", medium=f"LP steam {st['pressure_bar_abs']} bar(a)", T_supply_C=T_sat,
        T_return_C=T_sat, T_source_in_C=T_exh, T_source_out_C=T_out if active else float("nan"),
        flow_kg_per_s=m_exh if active else 0.0,
        gross_kW=m_exh * cp * (T_exh - float(ex["gross_reference_C"])) if active else 0.0,
        recoverable_kW=rec, delivery_efficiency=eff, delivered_kW=rec * eff if "exhaust" in enabled else 0.0,
        enabled="exhaust" in enabled,
        backpressure_ok=float(ex["gas_side_dP_Pa"]) <= float(ex["max_added_backpressure_Pa"]),
        limit=f"gas out >= max(min outlet {ex['min_outlet_C']} C, T_sat {T_sat:.1f} + pinch {st['pinch_K']} K)",
        data_class="ENG (no OEM part-load data)")

    # Charge (scavenge) air -> HT recovery cooler -> hot-water loop
    sc, hw = eng["scavenge_air"], cfg["hot_water_loops"]["scavenge"]
    m_air = max(m_exh - m_fuel, 0.0)
    cpa = float(sc["cp_kJ_per_kgK"])
    T_air_out = float(hw["return_C"]) + float(hw["source_approach_K"])
    ok = active and T_ca >= float(hw["supply_C"]) + float(hw["source_approach_K"])
    rec = m_air * cpa * (T_ca - T_air_out) if ok else 0.0
    eff = float(o.get("delivery_efficiency", hw["delivery_efficiency"]))
    on = "scavenge" in enabled and bool(sc["enabled"])
    sources["scavenge"] = dict(
        source="scavenge", kind="hot_water", medium=f"HT hot water {hw['supply_C']}/{hw['return_C']} C",
        T_supply_C=float(hw["supply_C"]), T_return_C=float(hw["return_C"]), T_source_in_C=T_ca,
        T_source_out_C=T_air_out if ok else float("nan"), flow_kg_per_s=m_air if active else 0.0,
        gross_kW=m_air * cpa * (T_ca - float(sc["gross_cooled_to_C"])) if active else 0.0,
        recoverable_kW=rec, delivery_efficiency=eff, delivered_kW=rec * eff if on else 0.0, enabled=on,
        backpressure_ok=True,
        limit=f"charge air in >= loop supply + {hw['source_approach_K']} K; cooled to loop return + approach "
              f"({T_air_out} C); OEM-approved interface required",
        data_class="ENG (no OEM part-load data)")

    # Jacket water -> plate exchanger -> LT hot-water loop
    jw, lw = eng["jacket_water"], cfg["hot_water_loops"]["jacket"]
    gross = float(jw["gross_fraction_of_fuel"]) * fuel_kW if active else 0.0
    ok = active and float(jw["T_engine_outlet_C"]) >= float(lw["supply_C"]) + float(lw["source_approach_K"])
    rec = gross * float(jw["recoverable_fraction"]) if ok else 0.0
    eff = float(o.get("delivery_efficiency", lw["delivery_efficiency"]))
    on = "jacket" in enabled and bool(jw["enabled"])
    sources["jacket"] = dict(
        source="jacket", kind="hot_water", medium=f"LT hot water {lw['supply_C']}/{lw['return_C']} C",
        T_supply_C=float(lw["supply_C"]), T_return_C=float(lw["return_C"]), T_source_in_C=float(jw["T_engine_outlet_C"]),
        T_source_out_C=float("nan"), flow_kg_per_s=float("nan"), gross_kW=gross, recoverable_kW=rec,
        delivery_efficiency=eff, delivered_kW=rec * eff if on else 0.0, enabled=on, backpressure_ok=True,
        limit=f"recoverable fraction {jw['recoverable_fraction']} of the gross (engine temperature control)",
        data_class="previous pre-FEED fractions (attributed to Zhu et al. 2020) + ENG")
    for s in sources.values():
        s.update(engine_load=load, shaft_kW=shaft_kW, fuel_kW=fuel_kW)
    return [sources[ID] for ID in SOURCE_IDS]


def _heating_hus(unit):
    """Purchased heating utilities of a unit (steam agents; the fired natural gas of U2 is handled separately)."""
    return [hu for hu in unit.heat_utilities if hu.duty > 0.0 and "steam" in hu.agent.ID]


def s1_heat_sinks(sys, cfg=None):
    """
    Purchased heating of the simulated system that WHR may replace [kW], after the S1 HXN: residual LP steam per
    unit (from the HXN stream life cycles; units outside the HXN keep their full duty) and the optional U2 feed
    preheater. Also lists the U2 fired duty and every other heating duty as non-eligible rows.
    """
    cfg = load_whr_config() if cfg is None else cfg
    units = {u.ID: u for u in sys.units}
    hxn = next((f for f in sys.facilities if isinstance(f, bst.HeatExchangerNetwork)), None)
    residual = {}     # aux exchanger id -> (residual fraction of its duty, T_in K, T_out K, HXN-recovered kJ/h)
    if hxn is not None:
        for slc in hxn.stream_life_cycles:
            orig = hxn.original_heat_exchangers[slc.index]
            if orig.Q <= 0.0:
                continue
            utils = [ls.unit for ls in slc.life_cycle if isinstance(ls.unit, bst.HXutility)]
            res = sum(u.Q for u in utils)
            T_in = min(u.ins[0].T for u in utils) if utils else orig.outs[0].T
            residual[id(orig)] = (res / orig.Q, T_in, orig.outs[0].T, orig.Q - res)
    rows = []
    for ID in cfg["sinks"]["steam_units"]:
        u = units.get(ID)
        if u is None:
            continue
        hus = _heating_hus(u)
        aux = [getattr(u, n) for n in getattr(u, "auxiliary_unit_names", ()) if n.startswith("hxn_")]
        aux = [a for a in aux if (getattr(a, "Q", 0.0) or 0.0) > 0.0]
        for hu in hus:
            a = aux[0] if aux else None
            frac, T_in, T_out, hxn_rec = residual.get(id(a), (1.0, a.ins[0].T if a else float("nan"),
                                                             a.outs[0].T if a else float("nan"), 0.0))
            rows.append(dict(unit=ID, utility=hu.agent.ID, eligible=True,
                             purchased_before_hxn_kW=hu.duty / 3600.0,
                             hxn_recovered_kW=hxn_rec / 3600.0 * hu.duty / max(a.Q, 1e-30) if a else 0.0,
                             purchased_kW=frac * hu.duty / 3600.0, T_in_C=T_in - _K, T_out_C=T_out - _K,
                             usd_per_kWh=hu.cost / hu.duty * 3600.0,
                             note="residual LP steam after the S1 HXN" if a is not None and id(a) in residual
                             else "LP steam, not in the HXN"))
            aux = aux[1:]
    U2 = units["U2"]
    pre = cfg["sinks"]["u2_feed_preheat"]
    feed = U2.ins[0]
    T_target = float(pre["target_C"]) + _K
    Q_pre = 0.0
    if pre["enabled"] and T_target > feed.T:
        hot = feed.copy()
        hot.T = T_target
        Q_pre = float(hot.H - feed.H)                      # sensible process heat [kJ/h]
    from biorefineries.ATT.analyses.tea import _ng_usd_per_MJ, _BURNER_EFFICIENCY
    loss = 1.0 + float(U2.heat_loss_fraction)
    rows.append(dict(unit="U2 feed preheat (S2 boundary)", utility="natural_gas (U2 furnace)", eligible=bool(pre["enabled"]),
                     purchased_before_hxn_kW=Q_pre * loss / 3600.0, hxn_recovered_kW=0.0,
                     purchased_kW=Q_pre * loss / 3600.0, T_in_C=feed.T - _K, T_out_C=T_target - _K,
                     usd_per_kWh=_ng_usd_per_MJ() / _BURNER_EFFICIENCY * 3.6,
                     note="sensible feed preheat to target; reduces the U2 fired duty (x (1 + heat loss)); conceptual preheater"))
    U2_hu = sum(hu.duty for hu in U2.heat_utilities if hu.duty > 0) / 3600.0
    rows.append(dict(unit="U2 (500 C reaction heat, fired)", utility="natural_gas", eligible=False,
                     purchased_before_hxn_kW=U2_hu, hxn_recovered_kW=0.0, purchased_kW=U2_hu - Q_pre * loss / 3600.0,
                     T_in_C=float("nan"), T_out_C=float(U2.target_temperature_K) - _K,
                     usd_per_kWh=_ng_usd_per_MJ() / _BURNER_EFFICIENCY * 3.6,
                     note="not eligible: high-temperature reaction heat stays on the U2 furnace"))
    listed = set(cfg["sinks"]["steam_units"]) | {"U2"}
    for u in sys.units:
        if u.ID in listed or u in sys.facilities:     # the HXN's utility changes are already in the residuals
            continue
        for hu in _heating_hus(u):
            rows.append(dict(unit=u.ID, utility=hu.agent.ID, eligible=False, purchased_before_hxn_kW=hu.duty / 3600.0,
                             hxn_recovered_kW=0.0, purchased_kW=hu.duty / 3600.0, T_in_C=float("nan"),
                             T_out_C=float("nan"), usd_per_kWh=hu.cost / hu.duty * 3600.0, note="not configured as a sink"))
    return rows


def _reach(source, sink, dT):
    """Fraction of a sink's duty a source can supply from the sink's cold end (linear sensible profile)."""
    T_s, T_r = source["T_supply_C"], source["T_return_C"]
    T_in, T_out = sink["T_in_C"], sink["T_out_C"]
    if T_r - dT < T_in - 1e-9:                     # cold end: the medium return must stay above the sink inlet
        return 0.0
    T_max = T_s - dT
    if T_out - T_in < 0.5:                         # latent / isothermal sink
        return 1.0 if T_max >= T_out - 1e-9 else 0.0
    return max(0.0, min(1.0, (T_max - T_in) / (T_out - T_in)))


def allocate(sources, sinks, min_approach_K):
    """
    Assign delivered source heat to eligible sinks [kW]: sources lowest grade first, sinks coldest first; each
    sink is covered from its cold end (``covered`` fraction), never above its purchased duty; each source is
    used once. Returns (assignments, remaining source kW by id, external kW by sink).
    """
    left = {s["source"]: s["delivered_kW"] for s in sources}
    elig = sorted([k for k in sinks if k["eligible"] and k["purchased_kW"] > 0.0], key=lambda k: (k["T_out_C"], k["T_in_C"]))
    covered = {id(k): 0.0 for k in elig}
    out = []
    for s in sources:
        for k in elig:
            if left[s["source"]] <= 0.0:
                break
            f = _reach(s, k, min_approach_K)
            avail = max(0.0, f - covered[id(k)]) * k["purchased_kW"]
            q = min(avail, left[s["source"]])
            if q > 0.0:
                covered[id(k)] += q / k["purchased_kW"]
                left[s["source"]] -= q
                out.append(dict(source=s["source"], sink=k["unit"], assigned_kW=q, usd_per_kWh=k["usd_per_kWh"],
                                sink_utility=k["utility"]))
    external = {k["unit"]: k["purchased_kW"] * (1.0 - covered.get(id(k), 0.0)) for k in sinks}
    return out, left, external


def _hx_cost(Q_kW, U, LMTD, F_BM):
    A = Q_kW / (U * LMTD)                                       # m2
    A_ft2 = max(A * 10.7639, 150.0)                             # correlation lower bound (Seider) 150 ft2
    purchase = compute_floating_head_purchase_cost(A_ft2, bst.CE)
    return A, purchase, purchase * F_BM


def _lmtd(dT1, dT2):
    return dT1 if abs(dT1 - dT2) < 1e-9 else (dT1 - dT2) / log(dT1 / dT2)


def _pump(name, kgps, T_C, dP_bar, eta):
    """BioSTEAM pump on a water stream in a scratch flowsheet: (installed USD, power kW)."""
    if kgps <= 0.0:
        return 0.0, 0.0
    with inv._scratch_flowsheet():
        s = bst.Stream(None, Water=kgps * 3600.0, units="kg/hr", T=T_C + _K, P=101325.0)
        p = bst.Pump(name, ins=s, P=101325.0 + dP_bar * 1e5)
        p.simulate()
        cost, power = p.installed_cost, p.power_utility.rate
    # BioSTEAM sizes its motor and efficiency; report its power (eta in marine_whr.yaml is for the hand check)
    return cost, power


def whr_equipment(sources, assignments, cfg=None, capex_factor=1.0):
    """Itemized incremental WHR equipment for the sources that are actually used: [(name, installed USD, basis)], kW."""
    cfg = load_whr_config() if cfg is None else cfg
    eq = cfg["equipment"]
    U, F_BM = eq["U_kW_per_m2K"], float(eq["hx_bare_module_factor"])
    used = {}
    for a in assignments:
        used.setdefault(a["source"], {}).setdefault(a["sink"], 0.0)
        used[a["source"]][a["sink"]] += a["assigned_kW"]
    src = {s["source"]: s for s in sources}
    items, power = [], 0.0
    eta = float(cfg["pump_efficiency"])
    if "exhaust" in used:
        s = src["exhaust"]
        q_rec = sum(used["exhaust"].values()) / s["delivery_efficiency"]          # heat taken from the gas
        lm = _lmtd(s["T_source_in_C"] - s["T_supply_C"], s["T_source_out_C"] - s["T_supply_C"])
        A, _, inst = _hx_cost(q_rec, U["economizer"], lm, F_BM)
        items.append((f"WHR: exhaust gas economizer ({A:.0f} m2, {q_rec:.0f} kW, LMTD {lm:.1f} K)", inst,
                      "BioSTEAM floating-head correlation (proxy for a finned water-tube economizer) x F_BM"))
        items.append(("WHR: steam drum / boiler interface", float(eq["steam_drum_installed_usd"]), "ENG placeholder"))
        steam_kgps = q_rec / (bst.settings.chemicals["Water"].Hvap(s["T_supply_C"] + _K) / 18.01528)   # kJ/kg
        c, p = _pump("WHR_feedwater_pump", steam_kgps, 60.0, float(cfg["steam_system"]["feedwater_dP_bar"]), eta)
        items.append((f"WHR: feedwater/condensate pump ({steam_kgps:.2f} kg/s)", c, "BioSTEAM Pump"))
        power += p
    for ID, key, U_key in (("scavenge", "scavenge", "scavenge_recovery_cooler"), ("jacket", "jacket", "jacket_plate_hx")):
        if ID not in used:
            continue
        s, loop = src[ID], cfg["hot_water_loops"][key]
        q_rec = sum(used[ID].values()) / s["delivery_efficiency"]
        if ID == "scavenge":
            lm = _lmtd(s["T_source_in_C"] - loop["supply_C"], s["T_source_out_C"] - loop["return_C"])
            label = "charge-air HT recovery cooler (OEM-approved interface)"
        else:
            lm = _lmtd(s["T_source_in_C"] - loop["supply_C"], s["T_source_in_C"] - 10.0 - loop["return_C"])
            label = "jacket-water plate heat exchanger"
        A, _, inst = _hx_cost(q_rec, U[U_key], lm, F_BM)
        items.append((f"WHR: {label} ({A:.0f} m2, {q_rec:.0f} kW, LMTD {lm:.1f} K)", inst,
                      "BioSTEAM floating-head correlation (proxy) x F_BM"))
        kgps = q_rec / (4.19 * (loop["supply_C"] - loop["return_C"]))
        c, p = _pump(f"WHR_{ID}_loop_pump", kgps, loop["return_C"], float(loop["loop_dP_bar"]), eta)
        items.append((f"WHR: {ID} hot-water loop pump ({kgps:.1f} kg/s)", c, "BioSTEAM Pump"))
        power += p
    pre = [(a["source"], a["assigned_kW"]) for a in assignments if a["sink"].startswith("U2 feed preheat")]
    if pre:
        q = sum(v for _, v in pre)
        s = src[max(pre, key=lambda x: x[1])[0]]
        lm = max(s["T_return_C"] - 75.0, 5.0)                    # conservative: medium return vs feed inlet
        A, _, inst = _hx_cost(q, U["u2_feed_preheater"], lm, F_BM)
        items.append((f"WHR: U2 feed preheater ({A:.0f} m2, {q:.0f} kW)", inst,
                      "BioSTEAM floating-head correlation (proxy for a slurry heater) x F_BM"))
    if items:
        base = sum(v for _, v, _ in items)
        items.append(("WHR: piping, valves, bypass, sootblowing, instruments, controls, insulation",
                      float(eq["piping_controls_allowance_fraction"]) * base, "ENG allowance fraction"))
    if eq["buffer_tank"]["enabled"]:
        items.append(("WHR: optional thermal buffer tank", float(eq["buffer_tank"]["installed_usd"]), "ENG placeholder"))
    items = [(n, v * capex_factor, b + (f" x WHR CAPEX factor {capex_factor:g}" if capex_factor != 1.0 else ""))
             for n, v, b in items]
    return items, power


def evaluate_whr(sys, enabled=SOURCE_IDS, load=None, overrides=None, capex_factor=1.0, cfg=None):
    """Full WHR accounting for a simulated ATT system (kW at its feed rate)."""
    cfg = load_whr_config() if cfg is None else cfg
    sources = engine_sources(cfg, load, enabled, overrides)
    sinks = s1_heat_sinks(sys, cfg)
    assignments, left, external = allocate(sources, sinks, float(cfg["sinks"]["min_approach_K"]))
    items, pump_kW = whr_equipment(sources, assignments, cfg, capex_factor)
    used = sum(a["assigned_kW"] for a in assignments)
    by_source = {s["source"]: sum(a["assigned_kW"] for a in assignments if a["source"] == s["source"]) for s in sources}
    for s in sources:
        s["utilized_kW"] = by_source[s["source"]]
        s["unutilized_kW"] = s["delivered_kW"] - by_source[s["source"]]
    for k in sinks:
        k["assigned_kW"] = sum(a["assigned_kW"] for a in assignments if a["sink"] == k["unit"])
        k["external_after_kW"] = k["purchased_kW"] - k["assigned_kW"] if k["eligible"] else k["purchased_kW"]
    purchased_before = sum(k["purchased_kW"] for k in sinks)
    return dict(sources=sources, sinks=sinks, assignments=assignments, equipment=items, pump_kW=pump_kW,
                utilized_kW=used, external_before_kW=purchased_before, external_after_kW=purchased_before - used,
                savings_usd_per_h=sum(a["assigned_kW"] * a["usd_per_kWh"] for a in assignments),
                capex_usd=sum(v for _, v, _ in items))


def check_whr(whr, tol=1e-6):
    """Accounting checks of a WHR result: [(check, value, PASS/FAIL)]."""
    rows = []

    def add(name, ok, value=float("nan")):
        rows.append(dict(check=name, value=value, status="PASS" if ok else "FAIL"))

    for s in whr["sources"]:
        add(f"{s['source']}: delivered <= recoverable <= gross",
            s["delivered_kW"] <= s["recoverable_kW"] + tol and s["recoverable_kW"] <= s["gross_kW"] + tol,
            s["delivered_kW"])
        add(f"{s['source']}: utilized <= delivered (used once)", s["utilized_kW"] <= s["delivered_kW"] + tol,
            s["utilized_kW"])
        add(f"{s['source']}: exhaust backpressure within the assumed limit", bool(s["backpressure_ok"]))
    for k in whr["sinks"]:
        add(f"{k['unit']}: assigned <= purchased duty", k["assigned_kW"] <= k["purchased_kW"] + tol, k["assigned_kW"])
        add(f"{k['unit']}: remaining purchased heating >= 0", k["external_after_kW"] >= -tol, k["external_after_kW"])
        if not k["eligible"]:
            add(f"{k['unit']}: not eligible -> no WHR", k["assigned_kW"] <= tol, k["assigned_kW"])
    total = sum(a["assigned_kW"] for a in whr["assignments"])
    add("utilized = sum of assignments (no double count)", abs(total - whr["utilized_kW"]) <= tol, total)
    add("external after = before - utilized", abs(whr["external_before_kW"] - total - whr["external_after_kW"]) <= tol,
        whr["external_after_kW"])
    add("WHR pump electricity accounted when heat is used", whr["pump_kW"] > 0.0 or total == 0.0, whr["pump_kW"])
    return rows
