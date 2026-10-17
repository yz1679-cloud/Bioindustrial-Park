# Bioindustrial-Park: BioSTEAM's Premier Biorefinery Models and Results
# Copyright (C) 2026-, Yu Zhou,
#                      Yalin Li <mailto.yalin.li@gmail.com>
#
# This module is under the UIUC open-source license. See
# github.com/BioSTEAMDevelopmentGroup/biosteam/blob/master/LICENSE.txt
# for license details.

from math import ceil, exp, log, pi

import biosteam as bst
import numpy as np
import thermosteam as tmo
from biosteam.units.design_tools import PressureVessel
from biosteam.units.design_tools.specification_factors import pressure_vessel_material_factors
from biosteam.units.design_tools.vacuum import compute_vacuum_system_power_and_cost

from biorefineries.sabre.utils import load_assumptions

__all__ = (
    "ATTPress",
    "ATTReactor",
    "close_att_u2_balance",
    "CausticizationReactor",
    "NaOHEvaporator",
    "aqueous_naoh_enthalpy_correction_kJph",
    "ATTDrumDryer",
    "ATTCompressor",
    "ATTMolecularSieve",
    "ATTVesselCost",
    "ATTPSA",
    "ATTLimeKiln",
    "ATTLimeSlaker",
)

_ATT_DATA = load_assumptions("att.yaml")["att"]

_ATT = _ATT_DATA["reactor"]
_ATT_DOWNSTREAM = _ATT_DATA["downstream"]
_EQUIPMENT = _ATT_DATA["inventory"]["cost_estimates"]   # sizing of equipment BioSTEAM has no unit model for
_NAOH_HEAT_OF_SOLUTION_kJ_per_kg = float(_ATT_DOWNSTREAM["naoh_heat_of_solution_kJ_per_kg"])

_SARGASSUM_DRY_IDS = (
    "Ash",
    "Protein",
    "Lignin",
    "Glucan",
    "Xylan",
    "Mannan",
    "Galactan",
    "Arabinan",
    "Alginate",
    "Fucoidan",
    "Mannitol",
    "OtherSolids",
)


def _att_add_proxy_exchanger(unit, name, efficiency=None):
    """Create the auxiliary HXutility used by ``_att_proxy_exchanger`` (call in the unit's init)."""
    aux = unit.auxiliary(f"hxn_{name}", bst.HXutility, ins=bst.Stream(None),
                         heat_transfer_efficiency=efficiency)
    unit.register_auxiliary(aux, f"hxn_{name}")   # costs and utilities roll up into the parent unit
    return aux


def _att_proxy_exchanger(unit, name, duty_kJph, T_in, T_out=None, *, latent=False, hxn_ok=True,
                         costed=True):
    """
    Carry a heating or cooling duty of ``unit`` in an auxiliary BioSTEAM
    ``HXutility`` whose process side is a water stream, so that the duty has
    an exchanger (capital, utility) and, when ``hxn_ok``, process streams that
    BioSTEAM's HeatExchangerNetwork can match.

    The water stream is a PROXY for a process stream that BioSTEAM's unit
    models do not carry or that cannot be flashed (solids, NaOH/Na2CO3
    liquor): sensible duty between ``T_in`` and ``T_out`` (water of equal
    heat capacity) or latent duty at ``T_in`` (evaporating, duty > 0, or
    condensing, duty < 0, water). ``costed=False`` zeroes the exchanger cost
    where the heating or cooling surface is already inside the unit's own
    cost correlation or estimate.
    """
    if abs(duty_kJph) <= 1e-9:
        return None
    hx = getattr(unit, f"hxn_{name}")   # created in the unit's _init by _att_add_proxy_exchanger
    Water = bst.settings.chemicals["Water"]
    if latent:
        P = float(Water.Psat(T_in))
        heating = duty_kJph > 0.0
        s_in = bst.Stream(None, Water=1.0, T=T_in, P=P, phase="l" if heating else "g")
        s_out = bst.Stream(None, Water=1.0, T=T_in, P=P, phase="g" if heating else "l")
        per_kmol = abs(Water.Hvap(T_in))
    else:
        s_in = bst.Stream(None, Water=1.0, T=T_in, P=101325.0, phase="l")
        s_out = bst.Stream(None, Water=1.0, T=T_out, P=101325.0, phase="l")
        per_kmol = s_out.H - s_in.H
    scale = abs(duty_kJph) / abs(per_kmol)
    s_in.scale(scale)
    s_out.scale(scale)
    hx.simulate_as_auxiliary_exchanger(ins=[s_in], outs=[s_out], duty=duty_kJph, vle=latent or False,
                                       hxn_ok=hxn_ok)
    if not costed:
        for d in (hx.baseline_purchase_costs, hx.purchase_costs, hx.installed_costs):
            for k in list(d):
                d[k] = 0.0
    return hx


class ATTDrumDryer(bst.DrumDryer):
    """
    BioSTEAM DrumDryer whose steam duty is carried by an auxiliary exchanger
    (water evaporating at the drum temperature) that BioSTEAM's
    HeatExchangerNetwork can match. The exchanger cost is zero: the heated
    drum is already inside the DrumDryer cost correlation.

    BioSTEAM sizes a single drum from the evaporation rate. Here the load is
    split over identical parallel drums no larger than ``max_drum_diameter_m``
    (cost and power per drum from the BioSTEAM correlation, times the number
    of drums).
    """

    def _init(self, *args, max_drum_diameter_m=None, **kwargs):
        super()._init(*args, **kwargs)
        self.max_drum_diameter_m = None if max_drum_diameter_m is None else float(max_drum_diameter_m)
        self._N_drums = 1
        _att_add_proxy_exchanger(self, "steam")

    def _design(self):
        n = len(self.heat_utilities)
        super()._design()
        self._N_drums = 1
        D_max = self.max_drum_diameter_m
        if D_max is not None:
            from math import ceil, pi
            from biosteam.units.design_tools import cylinder_diameter_from_volume, cylinder_area
            results = self.design_results
            V_max = pi / 4.0 * D_max ** 2 * (D_max * self.length_to_diameter)
            N = max(1, int(ceil(results["Volume"] / V_max - 1e-9)))
            if N > 1:
                results["Volume"] = V = results["Volume"] / N
                results["Diameter"] = D = cylinder_diameter_from_volume(V, self.length_to_diameter)
                results["Length"] = L = D * self.length_to_diameter
                results["Peripheral drum area"] = cylinder_area(D, L)
            self._N_drums = N
        self.design_results["Number of drums"] = self._N_drums
        for hu in self.heat_utilities[n:]:
            self.heat_utilities.remove(hu)
            _att_proxy_exchanger(self, "steam", hu.unit_duty, self.T, latent=True, costed=False)

    def _cost(self):
        super()._cost()   # one drum
        N = self._N_drums
        if N > 1:
            for k in self.baseline_purchase_costs:
                self.baseline_purchase_costs[k] *= N
            self.power_utility.scale(N)


class ATTCompressor(bst.IsothermalCompressor):
    """
    IsothermalCompressor whose intercooling duty is carried by a costed
    auxiliary cooler (water proxy, sensible from ``intercooler_T_K`` to the
    outlet temperature). Kept out of the heat exchanger network: the
    interstage temperature is an assumption, not a modeled stream.
    """

    def _init(self, *args, intercooler_T_K=400.0, **kwargs):
        super()._init(*args, **kwargs)
        self.intercooler_T_K = float(intercooler_T_K)
        _att_add_proxy_exchanger(self, "intercooler")

    def _design(self):
        n = len(self.heat_utilities)
        super()._design()
        for hu in self.heat_utilities[n:]:
            self.heat_utilities.remove(hu)
            _att_proxy_exchanger(self, "intercooler", hu.unit_duty, self.intercooler_T_K, self.outs[0].T,
                                 hxn_ok=False)


class ATTMolecularSieve(bst.MolecularSieve):
    """
    MolecularSieve whose regeneration heating and cooling duties are carried
    by costed auxiliary exchangers (water proxy at ``regeneration_T_K``).
    Kept out of the heat exchanger network (provisional BioSTEAM duties).
    """

    def _init(self, *args, regeneration_T_K=450.0, **kwargs):
        super()._init(*args, **kwargs)
        self.regeneration_T_K = float(regeneration_T_K)
        _att_add_proxy_exchanger(self, "regeneration_heater")
        _att_add_proxy_exchanger(self, "regeneration_cooler")

    def _design(self):
        n = len(self.heat_utilities)
        super()._design()
        new = list(self.heat_utilities[n:])
        for hu in new:
            self.heat_utilities.remove(hu)
        T_in = float(self.ins[0].T)
        for hu in new:
            if hu.unit_duty > 0.0:
                _att_proxy_exchanger(self, "regeneration_heater", hu.unit_duty, T_in, self.regeneration_T_K,
                                     hxn_ok=False)
            else:
                _att_proxy_exchanger(self, "regeneration_cooler", hu.unit_duty, self.regeneration_T_K, T_in,
                                     hxn_ok=False)



class ATTVesselCost(bst.Unit, PressureVessel):
    """
    Vertical vessel of a given volume, costed with BioSTEAM's pressure-vessel
    correlation (auxiliary unit of the ATT reactor; no mass or energy effect).
    """
    _N_ins = _N_outs = 1
    _units = {"Pressure": "psi", "Diameter": "ft", "Length": "ft", "Wall thickness": "in", "Weight": "lb"}
    _F_BM_default = {"Vertical pressure vessel": 4.16, "Platform and ladders": 1.0}

    def __init__(self, ID="", ins=None, outs=(), thermo=None, *, volume_m3=1.0, length_to_diameter=3.0,
                 material="Inconel-600"):
        super().__init__(ID, ins, outs, thermo)
        self.volume_m3 = float(volume_m3)
        self.length_to_diameter = float(length_to_diameter)
        self.vessel_type = "Vertical"
        # BioSTEAM has no density for most alloys: size the wall with SS316
        # and apply the material factor of the specified alloy.
        self.vessel_material = "Stainless steel 316"
        self.F_M["Vertical pressure vessel"] = pressure_vessel_material_factors[material]

    def _run(self):
        self.outs[0].copy_like(self.ins[0])

    def _design(self):
        D_m = (4.0 * self.volume_m3 / (pi * self.length_to_diameter)) ** (1.0 / 3.0)
        self._design_and_cost_pressure_vessel(
            101325.0, D_m, self.length_to_diameter * D_m,
            pressure_units="Pa", length_units="m",
        )

    def _cost(self):
        pass


class ATTPSA(bst.Splitter):
    """
    Idealized PSA (component splitter) with a capital cost: BioSTEAM has no PSA
    model, so one installed-cost item, anchor x (H2 product / anchor capacity)
    ** exponent x cost_factor, is carried by the unit (bare-module factor 1,
    the anchor being an installed cost). PRELIMINARY: see att.yaml gas_treatment.psa_cost.
    """
    _F_BM_default = {"PSA unit": 1.0}

    def _init(self, *args, anchor_installed_cost_usd, anchor_capacity_t_H2_per_day, exponent=0.6, cost_factor=1.0,
              **kwargs):
        super()._init(*args, **kwargs)
        self.anchor_installed_cost_usd = float(anchor_installed_cost_usd)
        self.anchor_capacity_t_H2_per_day = float(anchor_capacity_t_H2_per_day)
        self.exponent = float(exponent)
        self.cost_factor = float(cost_factor)

    def _design(self):
        self.design_results["H2 product (t/d)"] = float(self.outs[0].imass["H2"]) * 24.0 / 1e3
        self._units["H2 product (t/d)"] = "t/d"

    def _cost(self):
        tpd = self.design_results["H2 product (t/d)"]
        self.baseline_purchase_costs["PSA unit"] = (
            self.anchor_installed_cost_usd * (tpd / self.anchor_capacity_t_H2_per_day) ** self.exponent
            * self.cost_factor
        )


class ATTLimeKiln(bst.Unit):
    """
    Lime kiln of the lime recycle: dries and calcines the F2 cake.

    CaCO3 -> CaO + CO2 (``calcination_conversion``) and Ca(OH)2 -> CaO + H2O; the cake water is
    evaporated; NaOH, Na2CO3 and any other solids pass through unchanged (sodium rides with the lime).
    ins: [0] cake. outs: [0] hot-end lime solids (cooled to ``solids_outlet_temperature_K``; the heat
    of the lime is recovered inside the kiln), [1] exhaust (CO2, water vapor).

    Heat: the net duty (products at their outlet temperatures minus the cake) is supplied by natural gas
    through an auxiliary furnace (BioSTEAM furnace correlation). Shell: rotating drum costed with
    BioSTEAM's drum-dryer correlation on a peripheral area proportional to the CaO capacity, times an
    assumed refractory factor, with the dryer correlation's drive and fan power. PRELIMINARY.
    """
    _N_ins = 1
    _N_outs = 2
    auxiliary_unit_names = ("heat_exchanger",)
    _F_BM_default = {"Rotary kiln": 2.06}
    _units = {"CaO capacity": "t/d", "Kiln shell area": "m2"}

    def _init(self, calcination_conversion=0.98, solids_outlet_temperature_K=363.15, exhaust_temperature_K=473.15,
              heat_loss_fraction=0.10, kiln_area_m2_per_t_CaO_per_day=3.14, refractory_factor=2.0):
        self.calcination_conversion = float(calcination_conversion)
        self.solids_outlet_temperature_K = float(solids_outlet_temperature_K)
        self.exhaust_temperature_K = float(exhaust_temperature_K)
        self.heat_loss_fraction = float(heat_loss_fraction)
        self.kiln_area_m2_per_t_CaO_per_day = float(kiln_area_m2_per_t_CaO_per_day)
        self.refractory_factor = float(refractory_factor)
        self.auxiliary("heat_exchanger", bst.HXutility, ins=self.ins, T=1173.15, rigorous=False, heat_only=True,
                       heat_transfer_efficiency=1.0 / (1.0 + self.heat_loss_fraction))

    def _run(self):
        cake = self.ins[0]
        solids, exhaust = self.outs
        solids.empty()
        exhaust.empty()
        solids.phase, exhaust.phase = "s", "g"
        for chemical in cake.chemicals:
            ID = chemical.ID
            n = float(cake.imol[ID])
            if n and ID not in ("Water", "CaCO3", "CaOH2"):
                solids.imol[ID] = n
        caco3 = float(cake.imol["CaCO3"])
        calcined = self.calcination_conversion * caco3
        dehydrated = float(cake.imol["CaOH2"])
        solids.imol["CaCO3"] = caco3 - calcined
        solids.imol["BurntLime"] += calcined + dehydrated
        exhaust.imol["CO2"] = calcined
        exhaust.imol["Water"] = float(cake.imol["Water"]) + dehydrated
        solids.T, exhaust.T = self.solids_outlet_temperature_K, self.exhaust_temperature_K
        solids.P = exhaust.P = cake.P

    def _design(self):
        cake = self.ins[0]
        solids, exhaust = self.outs
        duty = float(solids.Hnet + exhaust.Hnet - cake.Hnet)          # kJ/h, net of the internal heat recovery
        hx = self.heat_exchanger
        hx.outs[0].copy_like(cake)
        hx.outs[0].T = 1173.15
        hx.simulate(run=False, design_kwargs={"duty": duty})
        cao_tpd = float(solids.imol["BurntLime"]) * 56.0774 * 24.0 / 1e3
        self._cao_tpd = cao_tpd
        self.design_results["CaO capacity"] = cao_tpd
        self.design_results["Kiln shell area"] = self.kiln_area_m2_per_t_CaO_per_day * cao_tpd
        self.design_results["Net heat duty"] = duty
        self._units["Net heat duty"] = "kJ/hr"

    def _cost(self):
        area = self.design_results["Kiln shell area"]
        if area > 0.0:
            ratio = area / 1235.35
            # BioSTEAM DrumDryer: 0.52 x 2.268 MUSD at 1235 m2 peripheral area (CE 525.4, 2007), exponent 0.6, 939 kW.
            self.baseline_purchase_costs["Rotary kiln"] = (
                0.52 * 2268000.0 * bst.CE / 525.4 * ratio ** 0.6 * self.refractory_factor)
            self.add_power_utility(938.866 * ratio ** 0.6)


class ATTLimeSlaker(bst.Unit):
    """
    Slaker of the lime recycle: CaO + water -> Ca(OH)2 (semi-dry: ``water_ratio`` kmol water per kmol
    CaO, so the hydrate leaves as a dry solid). The heat of slaking is removed by a costed auxiliary
    cooler (water proxy) to ``T``; not matched in the HXN.
    ins: [0] lime solids from the kiln (after the purge), [1] slaking water (set here). outs: [0] hydrated lime.
    """
    _N_ins = 2
    _N_outs = 1

    def _init(self, T=363.15, water_ratio=1.0):
        self.T = float(T)
        self.water_ratio = float(water_ratio)
        _att_add_proxy_exchanger(self, "cooler")

    def _run(self):
        lime, water = self.ins
        out = self.outs[0]
        n_cao = float(lime.imol["BurntLime"])
        water.empty()
        water.imol["Water"] = self.water_ratio * n_cao
        water.phase, water.T = "l", 298.15
        out.empty()
        out.phase = "s"
        for chemical in lime.chemicals:
            ID = chemical.ID
            n = float(lime.imol[ID])
            if n and ID != "BurntLime":
                out.imol[ID] = n
        out.imol["CaOH2"] += n_cao
        out.imol["Water"] += (self.water_ratio - 1.0) * n_cao
        out.T, out.P = self.T, lime.P

    def _design(self):
        lime, water = self.ins
        duty = float(self.outs[0].Hnet - lime.Hnet - water.Hnet)       # kJ/h, negative: heat released
        if duty < 0.0:
            _att_proxy_exchanger(self, "cooler", duty, 400.0, self.T, hxn_ok=False)


class ATTPress(bst.Unit):
    """
    P1: screw press of the fresh-Sargassum plant, with the cost and power basis of a
    municipal biosolids screw press (att.yaml feed_preparation.press).

    ins: [0] fresh Sargassum. outs: [0] presscake, [1] press liquid (raw
    juice for biostimulant production).

    Each component stays in the cake in the fraction ``retention`` (default
    1); the cake water makes up ``1 - cake_solids_wt_frac`` of the cake, and
    the rest of the water leaves with the juice. Installed cost = anchor x
    (dry solids throughput / anchor throughput) ** exponent (single train);
    electricity = kWh per dry tonne of solids (ash included) fed.
    """

    _N_ins = 1
    _N_outs = 2
    _F_BM_default = {"Press system": 1.0}

    def _init(self, cake_solids_wt_frac, retention=None, power_kWh_per_dry_ton=5.0,
              capex_installed_ref_usd=3.1e6, ref_capacity_tph_dry=0.953, scale_exponent=0.6):
        self.cake_solids_wt_frac = float(cake_solids_wt_frac)
        self.retention = dict(retention or {})
        self.power_kWh_per_dry_ton = float(power_kWh_per_dry_ton)
        self.capex_installed_ref_usd = float(capex_installed_ref_usd)
        self.ref_capacity_tph_dry = float(ref_capacity_tph_dry)
        self.scale_exponent = float(scale_exponent)

    def _run(self):
        feed = self.ins[0]
        cake, juice = self.outs
        cake.empty()
        juice.empty()
        cake.phase = juice.phase = "l"
        for chemical in feed.chemicals:
            ID = chemical.ID
            if ID == "Water":
                continue
            mass = float(feed.imass[ID])
            r = min(max(self.retention.get(ID, 1.0), 0.0), 1.0)
            cake.imass[ID] = r * mass
            juice.imass[ID] = (1.0 - r) * mass
        solids = float(cake.F_mass)
        f = self.cake_solids_wt_frac
        water_feed = float(feed.imass["Water"])
        water_cake = min(solids * (1.0 - f) / f, water_feed)
        cake.imass["Water"] = water_cake
        juice.imass["Water"] = water_feed - water_cake
        cake.T = juice.T = feed.T
        cake.P = juice.P = feed.P

    def _design(self):
        feed = self.ins[0]
        dry_tph = (float(feed.F_mass) - float(feed.imass["Water"])) / 1e3
        self.design_results["Dry solids throughput (t/h)"] = dry_tph
        self.power_utility(self.power_kWh_per_dry_ton * dry_tph)

    def _cost(self):
        dry_tph = self.design_results["Dry solids throughput (t/h)"]
        capex = (self.capex_installed_ref_usd
                 * (dry_tph / self.ref_capacity_tph_dry) ** self.scale_exponent) if dry_tph > 0 else 0.0
        self.design_results["Installed CAPEX ($)"] = capex
        self.baseline_purchase_costs["Press system"] = capex


def close_att_u2_balance(method, feed_atoms, fixed_atoms, specified_gas_kmolph, species_atoms, char_atoms=None):
    """
    Specified-yield U2 closure: the gas yields are inputs. Carbon that is not
    in the specified gases or the carbonate leaves as extra CO2 (the model's
    closure product: no unreacted carbon residue is carried) and the product
    water closes the oxygen (and with it the mass) balance. Hydrogen is NOT
    solved: the hydrogen the identified products do not contain (outlet -
    inlet < 0) is left to the unidentified products (NH3, H2S, tars) and
    reported as a check; a carbon deficit is likewise left as an unresolved
    C residual instead of inventing carbon.

    Returns (gas kmol/h by species incl. the closure CO2, 0.0 [no residue],
    product water kmol/h, scale factor 1.0).
    """
    if method != "specified_yields":
        raise ValueError(f"Unsupported gas_closure_method '{method}'.")
    gas = dict(specified_gas_kmolph)
    fixed = dict(fixed_atoms)
    for ID, kmolph in gas.items():
        for element, n in species_atoms[ID].items():
            fixed[element] = fixed.get(element, 0.0) + n * kmolph
    remaining_C = feed_atoms.get("C", 0.0) - fixed.get("C", 0.0)
    if remaining_C > 0.0:
        gas["CO2"] = gas.get("CO2", 0.0) + remaining_C
        fixed["C"] = fixed.get("C", 0.0) + remaining_C
        fixed["O"] = fixed.get("O", 0.0) + 2.0 * remaining_C
    water_kmolph = feed_atoms.get("O", 0.0) - fixed.get("O", 0.0)
    if water_kmolph < 0.0:
        raise RuntimeError(
            f"The specified gas slate cannot be produced from this feed: the oxygen balance "
            f"gives product water {water_kmolph:.6g} kmol/h."
        )
    return gas, 0.0, water_kmolph, 1.0


class ATTReactor(bst.Unit):
    """
    Alkaline thermal treatment (ATT) reactor for Sargassum.

    The baseline case is Ni-CatATT. NaOH loading is defined on the actual
    SaBRe dry-ash-free feed basis; NaOH-to-Na2CO3 conversion follows
    att.yaml (workbook: complete).

    The gas yields are specified (att.yaml: the experimental team's slate).
    C, O and Na are closed: carbon beyond the specified gases and the
    carbonate leaves as extra CO2 and the product water closes oxygen and
    mass. Hydrogen is a check, not an unknown (what the identified products
    do not hold goes to unidentified products such as NH3). N and S are not
    followed (they stay in an inert N/S residue). ``balance_checks`` reports (i) whether
    the NaOH can absorb the CO2 generated and (ii) whether the products
    respect the electron, mass and energy balances of the feed.

    The process heat duty is Hnet(outlets) - Hnet(inlet) and therefore
    includes the reaction enthalpy. The organic feed's formation enthalpy is
    re-referenced to the HHV in att.yaml, and the dissolved NaOH in the
    feed is corrected to the NaOH(aq) electrolyte enthalpy
    (``aqueous_feed_enthalpy_correction_kJph``, set by the flowsheet).

    Notes
    -----
    The auxiliary HXutility represents heat supplied to the ATT reactor.
    This is a reduced-order, data-reconciled yield model, not a kinetic or
    mechanistic reaction model.
    """

    _N_ins = 2          # [0] feed, [1] PSA tail gas: fuel gas burned in the U2 furnace (empty without a PSA)
    _N_outs = 2

    # Official BioSTEAM auxiliary-unit pattern.
    auxiliary_unit_names = ("heat_exchanger",)

    def _init(
        self,
        target_temperature_K=_ATT["target_temperature_K"],
        heat_loss_fraction=_ATT["heat_loss_fraction"],
        case_name=None,
        gas_closure_method=None,
    ):
        self.target_temperature_K = float(
            target_temperature_K
        )
        self.heat_loss_fraction = float(
            heat_loss_fraction
        )

        if self.heat_loss_fraction < 0.0:
            raise ValueError(
                "heat_loss_fraction must be non-negative."
            )

        # A 5% heat-loss assumption is defined here as:
        #
        #     Q_utility = Q_process * (1 + heat_loss_fraction)
        #
        # HXutility uses heat-transfer efficiency, therefore:
        #
        #     efficiency = Q_process / Q_utility
        #                = 1 / (1 + heat_loss_fraction)
        self.heat_transfer_efficiency = (
            1.0 / (1.0 + self.heat_loss_fraction)
        )

        if case_name is None:
            case_name = _ATT["baseline_case"]

        cases = _ATT["cases"]
        if case_name not in cases:
            raise KeyError(
                f"Unknown ATT case '{case_name}'. "
                f"Available cases: {tuple(cases)}"
            )

        self.case_name = case_name
        self.case_data = cases[case_name]

        self.naoh_kg_per_kg_daf = float(
            self.case_data["naoh_kg_per_kg_daf"]
        )

        self.reported_gas_yield_mmol_per_g_daf = dict(
            self.case_data[
                "gas_yield_mmol_per_g_daf"
            ]
        )

        self.ignored_reported_gas_yields = dict(
            self.case_data.get(
                "ignored_reported_gas_yields_mmol_per_g_daf",
                {},
            )
        )

        balance = _ATT["material_balance"]

        self.naoh_to_na2co3_conversion = float(
            balance["naoh_to_na2co3_conversion"]
        )

        self.gas_closure_method = str(
            balance["gas_closure_method"] if gas_closure_method is None
            else gas_closure_method
        )
        if self.gas_closure_method != "specified_yields":
            raise ValueError(
                f"Unsupported gas_closure_method '{self.gas_closure_method}'."
            )
        self.char_ID = str(balance["char_species"])
        self.heteroatom_IDs = dict(balance["heteroatom_species"])

        self.enforce_full_elemental_balance = bool(
            balance["enforce_full_elemental_balance"]
        )

        self.feed_HHV_MJ_per_kg_daf = float(
            _ATT["energy_basis"]["feed_HHV_MJ_per_kg_daf"]
        )

        # Electrolyte enthalpy correction of the aqueous NaOH in the feed
        # [kJ/h]; set by the flowsheet (see aqueous_naoh_enthalpy_correction_kJph).
        self.aqueous_feed_enthalpy_correction_kJph = 0.0

        if not (
            0.0 <= self.naoh_to_na2co3_conversion <= 1.0
        ):
            raise ValueError(
                "naoh_to_na2co3_conversion must be between 0 and 1."
            )

        # Auxiliary HXutility.
        #
        # The detailed thermodynamic duty is calculated in _design().
        # The auxiliary exchanger then carries the utility and equipment-
        # cost bookkeeping for that calculated duty.
        self.auxiliary(
            "heat_exchanger",
            bst.HXutility,
            ins=self.ins[0],
            T=self.target_temperature_K,
            rigorous=False,
            heat_only=True,
            heat_transfer_efficiency=self.heat_transfer_efficiency,
        )

        # Reactor vessel (hold-up volume): costed with the pressure-vessel
        # correlation; its volume follows the feed in _design().
        cfg = _EQUIPMENT["U2_vessel"]
        vessel = self.auxiliary("vessel", ATTVesselCost, ins=bst.Stream(None),
                                length_to_diameter=cfg["length_to_diameter"], material=cfg["material"])
        self.register_auxiliary(vessel, "vessel")

    def _run(self):
        feed = self.ins[0]
        gas, residue = self.outs

        # ----------------------------------------------------------
        # Feed basis
        # ----------------------------------------------------------
        dry_sargassum_kgph = sum(
            float(feed.imass[ID])
            for ID in _SARGASSUM_DRY_IDS
        )

        ash_kgph = float(
            feed.imass["Ash"]
        )

        daf_sargassum_kgph = max(
            dry_sargassum_kgph - ash_kgph,
            0.0,
        )

        self._dry_sargassum_kgph = (
            dry_sargassum_kgph
        )
        self._daf_sargassum_kgph = (
            daf_sargassum_kgph
        )
        self._feed_water_kgph = float(
            feed.imass["Water"]
        )
        self._feed_naoh_kgph = float(
            feed.imass["NaOH"]
        )

        gas.empty()
        residue.empty()

        gas.phase = "g"
        residue.phase = "s"

        gas.T = self.target_temperature_K
        residue.T = self.target_temperature_K
        gas.P = feed.P
        residue.P = feed.P

        # ----------------------------------------------------------
        # 1. Fixed (non-gas) outlets: inert ash, Na2CO3/NaOH from the
        #    specified conversion, and feed N/S retained in the char.
        # ----------------------------------------------------------
        residue.imass["Ash"] = ash_kgph

        sodium_kmolph = float(feed.get_atomic_flow("Na"))
        na2co3_kmolph = (
            0.5 * sodium_kmolph * self.naoh_to_na2co3_conversion
        )
        residue.imol["Na2CO3"] = na2co3_kmolph
        residue.imol["NaOH"] = sodium_kmolph - 2.0 * na2co3_kmolph

        chemicals = feed.chemicals
        inorganic_IDs = ("Water", "NaOH", "Na2CO3", "Ash")
        organic_IDs = tuple(
            chemical.ID for chemical in chemicals
            if chemical.ID not in inorganic_IDs
            and float(feed.imol[chemical.ID]) > 0.0
        )
        for ID in organic_IDs:
            if "C" not in chemicals[ID].atoms:
                raise RuntimeError(
                    f"U2 feed species {ID!r} is not an organic feed "
                    "component; extend the U2 balance before using it."
                )

        def atoms_of(flows):
            totals = {}
            for ID, kmolph in flows.items():
                for element, n in chemicals[ID].atoms.items():
                    totals[element] = totals.get(element, 0.0) + n * kmolph
            return totals

        def flows_of(*streams):
            flows = {}
            for stream in streams:
                for chemical in chemicals:
                    kmolph = float(stream.imol[chemical.ID])
                    if kmolph != 0.0:
                        flows[chemical.ID] = flows.get(chemical.ID, 0.0) + kmolph
            return flows

        feed_atoms = atoms_of(flows_of(feed))
        for element, ID in self.heteroatom_IDs.items():
            residue.imol[ID] = feed_atoms.get(element, 0.0)

        # ----------------------------------------------------------
        # 2. Measured gas yields (mmol/g daf = mol/kg daf -> kmol/h).
        #    Gas 4 is ignored.
        # ----------------------------------------------------------
        measured_gas_kmolph = {
            ID: float(y) * daf_sargassum_kgph / 1000.0
            for ID, y in self.reported_gas_yield_mmol_per_g_daf.items()
        }

        # ----------------------------------------------------------
        # 3. Close C and H with the specified gases, char (C) and water (H);
        #    O is checked below, not solved.
        # ----------------------------------------------------------
        fixed_atoms = atoms_of(flows_of(residue))
        char_atoms = chemicals[self.char_ID].atoms
        species_atoms = {ID: chemicals[ID].atoms for ID in measured_gas_kmolph}
        model_gas_kmolph, char_kmolph, water_kmolph, scale = close_att_u2_balance(
            self.gas_closure_method, feed_atoms, fixed_atoms,
            measured_gas_kmolph, species_atoms, char_atoms,
        )
        gas_atoms = atoms_of(model_gas_kmolph)

        for ID, kmolph in model_gas_kmolph.items():
            gas.imol[ID] = kmolph
        gas.imol["Water"] = water_kmolph
        residue.imol[self.char_ID] = char_kmolph

        # ----------------------------------------------------------
        # 4. Verification and reporting.
        # ----------------------------------------------------------
        out_atoms = atoms_of(flows_of(gas, residue))
        atomic_balance_errors = {
            element: out_atoms.get(element, 0.0) - feed_atoms.get(element, 0.0)
            for element in set(feed_atoms) | set(out_atoms)
        }
        tolerance = 1e-9 * max(1.0, max(map(abs, feed_atoms.values())))
        # Unresolved elemental residuals (outlet - inlet, kmol/h): only oxygen
        # may remain, and only within 2 % of the organic oxygen of the feed
        # (otherwise the specified slate violates the electron/mass balance).
        self._unresolved_element_kmolph = {
            element: error for element, error in atomic_balance_errors.items()
            if abs(error) > tolerance
        }
        organic_atoms_feed = {
            e: sum(float(feed.imol[ID]) * chemicals[ID].atoms.get(e, 0.0) for ID in organic_IDs)
            for e in ("C", "O")
        }
        organic_O_kmolph = organic_atoms_feed["O"]
        o_residual = self._unresolved_element_kmolph.get("O", 0.0)
        organic_atoms_feed["H"] = sum(
            float(feed.imol[ID]) * chemicals[ID].atoms.get("H", 0.0) for ID in organic_IDs
        )
        # The identified products may hold LESS hydrogen/reducing power than the
        # feed (the rest is in unidentified products), never more.
        bad = {}
        for e, v in self._unresolved_element_kmolph.items():
            if e == "H":
                if v > 0.005 * organic_atoms_feed["H"]:
                    bad[e] = v
            elif e == "C":
                if abs(v) > 0.02 * organic_atoms_feed["C"]:
                    bad[e] = v
            else:
                bad[e] = v
        if bad:
            raise RuntimeError(
                "The specified gas slate violates the elemental/electron balance of the feed "
                "(identified products hold more hydrogen than the feed, a carbon mismatch beyond 2 %, "
                f"or another element): {bad}; all residuals {self._unresolved_element_kmolph}."
            )

        def available_electrons(atoms):
            # Reference states CO2, H2O and NH3; Na+ and Ca2+ are redox-inert.
            return (4.0 * atoms.get("C", 0.0) + atoms.get("H", 0.0)
                    - 2.0 * atoms.get("O", 0.0) - 3.0 * atoms.get("N", 0.0))

        organic_atoms = atoms_of(
            {ID: float(feed.imol[ID]) for ID in organic_IDs}
        )
        measured_gas_electrons = available_electrons(atoms_of(measured_gas_kmolph))
        char_solid_atoms = atoms_of(
            {ID: float(residue.imol[ID])
             for ID in (self.char_ID, *self.heteroatom_IDs.values())}
        )

        self._organic_atoms_kmolph = organic_atoms
        self._measured_gas_kmolph = measured_gas_kmolph
        self._gas_scale_factor = scale
        # Gas yields as specified (scale factor 1.0 kept for the reports).
        self._model_gas_kmolph = model_gas_kmolph
        self._model_gas_yield_mmol_per_g_daf = {
            ID: kmolph * 1000.0 / daf_sargassum_kgph
            for ID, kmolph in model_gas_kmolph.items()
        }
        self._redox_balance_kmol_e_per_h = {
            "feed_organics": available_electrons(organic_atoms),
            "measured_gases": measured_gas_electrons,
            "model_gases": available_electrons(gas_atoms),
            "char": available_electrons(char_solid_atoms),
        }
        self._char_kgph = sum(
            float(residue.imass[ID])
            for ID in (self.char_ID, *self.heteroatom_IDs.values())
        )
        self._char_carbon_fraction_of_feed_organic_C = (
            char_kmolph * char_atoms.get("C", 0.0) / organic_atoms["C"]
        )
        self._product_water_kgph = float(gas.imass["Water"])
        self._net_water_formation_kmolph = (
            water_kmolph - float(feed.imol["Water"])
        )

        self._mass_in_kgph = float(feed.F_mass)
        self._mass_out_kgph = float(gas.F_mass + residue.F_mass)
        self._mass_balance_error_kgph = self._mass_out_kgph - self._mass_in_kgph
        self._mass_balance_error_fraction = (
            self._mass_balance_error_kgph / self._mass_in_kgph
            if self._mass_in_kgph > 0.0 else 0.0
        )
        self._atomic_balance_errors_kmolph = atomic_balance_errors
        self._max_atomic_balance_error_kmolph = max(map(abs, atomic_balance_errors.values()), default=0.0)
        self._elemental_balance_enforced = not self._unresolved_element_kmolph
        c_residual = self._unresolved_element_kmolph.get("C", 0.0)
        h_residual = self._unresolved_element_kmolph.get("H", 0.0)
        status = (f"C/O/Na closed with the specified gas slate (extra closure CO2 "
                  f"{(model_gas_kmolph['CO2'] - measured_gas_kmolph['CO2']) * 1000.0 / daf_sargassum_kgph:.2f} mmol/g daf); "
                  f"residuals (outlet - inlet): C {c_residual * 1000.0 / daf_sargassum_kgph:+.3f}, "
                  f"H {h_residual * 1000.0 / daf_sargassum_kgph:+.3f} mmol/g daf (unidentified H products).")
        self._elemental_balance_status = status

        if dry_sargassum_kgph > 0.0:
            self._reported_product_mol_per_kg_dry = {
                ID: kmolph * 1000.0 / dry_sargassum_kgph
                for ID, kmolph in measured_gas_kmolph.items()
            }
            self._balanced_product_mol_per_kg_dry = {
                ID: float(gas.imol[ID]) * 1000.0 / dry_sargassum_kgph
                for ID in (*measured_gas_kmolph, "Water")
            }
            self._balanced_product_mol_per_kg_dry["Na2CO3"] = (
                na2co3_kmolph * 1000.0 / dry_sargassum_kgph
            )
        else:
            self._reported_product_mol_per_kg_dry = {}
            self._balanced_product_mol_per_kg_dry = {}

    def _make_thermal_state(
        self,
        feed,
        IDs,
        phase,
        T,
    ):
        """
        Build an unregistered ThermoSteam stream for enthalpy accounting.
        """
        stream = tmo.Stream(
            None,
            T=T,
            P=feed.P,
            phase=phase,
            thermo=feed.thermo,
        )

        for ID in IDs:
            amount = float(feed.imol[ID])
            if amount:
                stream.imol[ID] = amount

        return stream

    def _calculate_thermodynamic_heat_duty(
        self,
    ):
        """
        Calculate ATT feed-heating duty from ThermoSteam enthalpies.

        Feed water is heated from the actual mixer temperature, vaporized,
        and superheated to the ATT temperature. Dry Sargassum remains in
        the solid phase. NaOH is represented as a liquid sensible-heat
        load after evaporation of its associated solution water.
        """
        feed = self.ins[0]
        T_in = float(feed.T)
        T_out = self.target_temperature_K

        # ----------------------------------------------------------
        # Water: liquid feed -> superheated vapor at ATT temperature
        # ----------------------------------------------------------
        water_in = self._make_thermal_state(
            feed,
            ("Water",),
            "l",
            T_in,
        )
        water_out = self._make_thermal_state(
            feed,
            ("Water",),
            "g",
            T_out,
        )
        water_duty_kJph = float(
            water_out.H - water_in.H
        )

        # ----------------------------------------------------------
        # Dry Sargassum: sensible heating as solids
        # ----------------------------------------------------------
        dry_in = self._make_thermal_state(
            feed,
            _SARGASSUM_DRY_IDS,
            "s",
            T_in,
        )
        dry_out = self._make_thermal_state(
            feed,
            _SARGASSUM_DRY_IDS,
            "s",
            T_out,
        )
        dry_duty_kJph = float(
            dry_out.H - dry_in.H
        )

        # ----------------------------------------------------------
        # NaOH: sensible heating of the nonvolatile alkali.
        #
        # The NaOH enters as an aqueous solution; solution water is
        # already included in the water evaporation duty above.
        # ----------------------------------------------------------
        naoh_in = self._make_thermal_state(
            feed,
            ("NaOH",),
            "l",
            T_in,
        )
        naoh_out = self._make_thermal_state(
            feed,
            ("NaOH",),
            "l",
            T_out,
        )
        naoh_duty_kJph = float(
            naoh_out.H - naoh_in.H
        )

        # ----------------------------------------------------------
        # Any additional feed components not covered above.
        # These are not expected in the present M1 definition, but this
        # keeps the energy accounting robust to later model extensions.
        # ----------------------------------------------------------
        covered_IDs = set(
            _SARGASSUM_DRY_IDS
        )
        covered_IDs.update(
            ("Water", "NaOH")
        )

        other_IDs = tuple(
            chemical.ID
            for chemical in feed.chemicals
            if (
                chemical.ID not in covered_IDs
                and abs(float(feed.imol[chemical.ID]))
                > 1e-16
            )
        )

        other_duty_kJph = 0.0

        if other_IDs:
            feed_phase = feed.phase
            if len(feed_phase) != 1:
                feed_phase = "l"

            other_in = self._make_thermal_state(
                feed,
                other_IDs,
                feed_phase,
                T_in,
            )
            other_out = self._make_thermal_state(
                feed,
                other_IDs,
                feed_phase,
                T_out,
            )
            other_duty_kJph = float(
                other_out.H - other_in.H
            )

        total_duty_kJph = (
            water_duty_kJph
            + dry_duty_kJph
            + naoh_duty_kJph
            + other_duty_kJph
        )

        return {
            "water": water_duty_kJph,
            "dry_sargassum": dry_duty_kJph,
            "naoh": naoh_duty_kJph,
            "other": other_duty_kJph,
            "total": total_duty_kJph,
        }

    def _feed_organic_Hf_correction_kJph(self):
        """
        Re-reference the formation enthalpy of the organic feed to the HHV
        in att.yaml (Hess's law: Hf = sum Hf[CO2, H2O(l), SO2] + HHV*mass;
        N leaves as N2). Returns Hf(HHV basis) - sum of pseudo-component Hf.
        """
        feed = self.ins[0]
        chemicals = feed.chemicals
        Hf_products = {"C": -393474.0, "H": -285825.0 / 2.0, "S": -296810.0}
        organic_IDs = [
            chemical.ID for chemical in chemicals
            if chemical.ID not in ("Water", "NaOH", "Na2CO3", "Ash")
            and float(feed.imol[chemical.ID]) > 0.0
        ]
        native_Hf_kJph = 0.0
        products_Hf_kJph = 0.0
        organic_kgph = 0.0
        for ID in organic_IDs:
            kmolph = float(feed.imol[ID])
            native_Hf_kJph += kmolph * chemicals[ID].Hf
            organic_kgph += float(feed.imass[ID])
            for element, n in chemicals[ID].atoms.items():
                products_Hf_kJph += kmolph * n * Hf_products.get(element, 0.0)
        HHV_Hf_kJph = (
            products_Hf_kJph + self.feed_HHV_MJ_per_kg_daf * 1e3 * organic_kgph
        )
        return HHV_Hf_kJph - native_Hf_kJph

    def _design(self):
        feed = self.ins[0]
        gas, residue = self.outs

        # Feed sensible/latent heating to the reactor temperature (kept as a
        # breakdown term; the process duty below is the full Hnet balance).
        duties = (
            self._calculate_thermodynamic_heat_duty()
        )

        hf_correction_kJph = self._feed_organic_Hf_correction_kJph()
        aqueous_correction_kJph = float(self.aqueous_feed_enthalpy_correction_kJph)
        inlet_Hnet_kJph = (
            float(feed.Hnet) + hf_correction_kJph + aqueous_correction_kJph
        )
        outlet_Hnet_kJph = float(gas.Hnet + residue.Hnet)
        heat_duty_kJph = outlet_Hnet_kJph - inlet_Hnet_kJph
        reaction_and_product_state_kJph = heat_duty_kJph - duties["total"]

        self._inlet_Hnet_kJph = inlet_Hnet_kJph
        self._outlet_Hnet_kJph = outlet_Hnet_kJph
        self._feed_Hf_HHV_correction_kJph = hf_correction_kJph
        self._aqueous_feed_correction_kJph = aqueous_correction_kJph
        self._feed_heating_duty_kJph = float(duties["total"])
        self._reaction_and_product_state_kJph = reaction_and_product_state_kJph

        if heat_duty_kJph < 0:
            raise RuntimeError(
                "U2 Hnet balance gives a net exothermic reactor "
                f"({heat_duty_kJph:.6g} kJ/h); the heating-utility "
                "representation would be invalid."
            )

        # Populate the auxiliary HX outlet with a temperature endpoint
        # for exchanger design/costing. The detailed phase-change duty is
        # supplied explicitly from the ThermoSteam enthalpy calculation
        # above, so this auxiliary outlet is only a design representation.
        hx = self.heat_exchanger
        hx_out = hx.outs[0]
        hx_out.copy_like(feed)
        hx_out.T = self.target_temperature_K
        hx_out.P = feed.P

        # Design/cost the auxiliary exchanger at the calculated process
        # duty. BioSTEAM automatically rolls auxiliary utilities and costs
        # into the parent ATT reactor.
        hx.simulate(
            run=False,
            design_kwargs={
                "duty": heat_duty_kJph,
            },
        )
        cfg = _EQUIPMENT["U2_vessel"]
        vessel = self.vessel
        vessel.ins[0].copy_like(feed)
        vessel.volume_m3 = float(feed.F_mass) / cfg["density_kg_per_m3"] * cfg["tau_h"] / cfg["fill_fraction"]
        vessel.simulate(run=False)

        utility_heat_duty_kJph = sum(
            max(float(hu.duty), 0.0)
            for hu in hx.heat_utilities
        )

        # PSA tail gas (ins[1]) is fuel for the furnace: its LHV x the burner efficiency replaces natural gas heat,
        # up to the furnace duty. The natural gas utility above stays the gross furnace duty (heat demand); the
        # purchased natural gas is that duty minus the tail gas heat (``natural_gas_purchased_duty_kJph``).
        tail = self.ins[1]
        eta_burner = float(_ATT_DATA["energy_sources"]["natural_gas"]["burner_efficiency"])
        burn = _ATT_DATA["gas_treatment"]["tail_gas_combustion"] == "offset_u2_natural_gas"
        tail_LHV_kJph = float(tail.LHV) if tail.F_mol else 0.0
        gross_ng_kJph = sum(max(float(hu.duty), 0.0) for hu in hx.heat_utilities
                            if hu.agent is not None and hu.agent.ID == "natural_gas")
        self.tail_gas_LHV_kJph = tail_LHV_kJph
        self.tail_gas_heat_kJph = min(tail_LHV_kJph * eta_burner, gross_ng_kJph) if burn else 0.0
        self.natural_gas_gross_duty_kJph = gross_ng_kJph
        self.natural_gas_purchased_duty_kJph = gross_ng_kJph - self.tail_gas_heat_kJph

        heat_loss_kJph = max(
            utility_heat_duty_kJph - heat_duty_kJph,
            0.0,
        )

        self._water_heating_duty_kJph = (
            duties["water"]
        )
        self._dry_sargassum_heating_duty_kJph = (
            duties["dry_sargassum"]
        )
        self._naoh_heating_duty_kJph = (
            duties["naoh"]
        )
        self._other_heating_duty_kJph = (
            duties["other"]
        )

        # Keep this attribute name for compatibility with the existing
        # ATT energy-summary helper, but it is now thermodynamically
        # calculated rather than read from a fixed MJ/kg input.
        self._heat_duty_kJph = heat_duty_kJph
        self._thermal_power_kW = (
            heat_duty_kJph / 3600.0
        )

        self._heat_loss_kJph = (
            heat_loss_kJph
        )
        self._utility_heat_duty_kJph = (
            utility_heat_duty_kJph
        )
        self._utility_thermal_power_kW = (
            utility_heat_duty_kJph / 3600.0
        )

        self.design_results[
            "ATT water heating and evaporation duty"
        ] = duties["water"]

        self.design_results[
            "ATT dry Sargassum heating duty"
        ] = duties["dry_sargassum"]

        self.design_results[
            "ATT NaOH heating duty"
        ] = duties["naoh"]

        self.design_results[
            "ATT other-feed heating duty"
        ] = duties["other"]

        self.design_results[
            "ATT reaction and product-state enthalpy"
        ] = reaction_and_product_state_kJph

        self.design_results[
            "ATT feed Hf re-referenced to HHV"
        ] = hf_correction_kJph

        self.design_results[
            "ATT aqueous NaOH enthalpy correction"
        ] = aqueous_correction_kJph

        # Gas basis: specified yields and the oxygen check.
        self.design_results[
            "Hydrogen balance residual (unidentified products), outlet - inlet [mmol/g daf]"
        ] = self._unresolved_element_kmolph.get("H", 0.0) * 1000.0 / self._daf_sargassum_kgph
        self.design_results[
            "H2 yield, measured [mmol/g daf]"
        ] = float(self.reported_gas_yield_mmol_per_g_daf["H2"])
        self.design_results[
            "H2 yield, model [mmol/g daf]"
        ] = self._model_gas_yield_mmol_per_g_daf["H2"]

        self.design_results[
            "ATT thermodynamic process heat duty"
        ] = heat_duty_kJph

        self.design_results[
            "ATT thermodynamic thermal power"
        ] = self._thermal_power_kW

        self.design_results[
            "ATT heat loss"
        ] = heat_loss_kJph

        self.design_results[
            "ATT auxiliary utility heat duty"
        ] = utility_heat_duty_kJph

        self.design_results[
            "ATT auxiliary utility thermal power"
        ] = self._utility_thermal_power_kW



def _att_u2_balance_checks(self):
    """
    Checks of the specified slate (call after the system is simulated):

    (i) NaOH capacity for CO2: CO2 generated = gas CO2 + CO2 captured as
        Na2CO3; capturing it all needs 2 NaOH per CO2.
    (ii) electrons: available electrons of the feed organics against the
        gases and residue; overall mass; and energy: the chemical energy of
        the product gases (HHV) must not exceed the feed HHV plus the
        process heat.
    """
    daf = self._daf_sargassum_kgph
    gas, residue = self.outs
    feed = self.ins[0]
    chemicals = feed.chemicals
    co2_gas = float(gas.imol["CO2"])
    carbonate = float(residue.imol["Na2CO3"]) - float(feed.imol["Na2CO3"])   # formed in U2 (recycled carbonate excluded)
    co2_generated = co2_gas + carbonate
    naoh_available = float(feed.imol["NaOH"])
    naoh_required = 2.0 * co2_generated
    atoms = self._organic_atoms_kmolph
    e_feed = 4.0 * atoms.get("C", 0.0) + atoms.get("H", 0.0) - 2.0 * atoms.get("O", 0.0)   # C/H/O only
    e_out = sum(float(gas.imol[ID]) * v for ID, v in (("H2", 2.0), ("CH4", 8.0), ("CO", 2.0)))
    gas_HHV_kJph = sum(float(gas.imol[ID]) * chemicals[ID].HHV for ID in ("H2", "CH4", "CO"))
    feed_HHV_kJph = self.feed_HHV_MJ_per_kg_daf * 1e3 * daf
    heat_kJph = getattr(self, "_heat_duty_kJph", float("nan"))
    ratio = gas_HHV_kJph / (feed_HHV_kJph + max(heat_kJph, 0.0)) if feed_HHV_kJph > 0 else float("nan")
    rows = [
        dict(check="NaOH available for CO2 capture [mmol/g daf]", value=naoh_available * 1e3 / daf, unit="mmol/g daf"),
        dict(check="NaOH needed to capture all CO2 generated [mmol/g daf]", value=naoh_required * 1e3 / daf, unit="mmol/g daf"),
        dict(check="CO2 captured as Na2CO3 / CO2 generated", value=carbonate / co2_generated if co2_generated else float("nan"),
             unit="-", status="SUFFICIENT" if naoh_available >= naoh_required - 1e-12 else "INSUFFICIENT (CO2 remains in the gas)"),
        dict(check="Electrons: feed organics, C/H/O [mmol/g daf]", value=e_feed * 1e3 / daf, unit="mmol e-/g daf"),
        dict(check="Electrons: identified gases [mmol/g daf]", value=e_out * 1e3 / daf, unit="mmol e-/g daf",
             status="PASS" if e_out <= 1.01 * e_feed else "FAIL"),
        dict(check="Reducing power left to unidentified products / feed", value=(e_feed - e_out) / e_feed, unit="-"),
        dict(check="Mass balance error / inlet", value=self._mass_balance_error_fraction, unit="-",
             status="PASS" if abs(self._mass_balance_error_fraction) <= 5e-3 else "FAIL"),
        dict(check="Product gas HHV / (feed HHV + process heat)", value=ratio, unit="-",
             status="PASS" if ratio == ratio and ratio <= 1.0 else "FAIL"),
    ]
    return rows


ATTReactor.balance_checks = _att_u2_balance_checks


class CausticizationReactor(bst.Unit):
    """
    Causticization reactor for regenerating NaOH from sodium carbonate.

    Reaction
    --------
    Na2CO3 + Ca(OH)2 -> 2 NaOH + CaCO3

    Parameters
    ----------
    ins : tuple[stream, stream]
        Sodium-carbonate solution and Ca(OH)2 reagent.
    outs : stream
        Causticization slurry containing regenerated NaOH and CaCO3.
    conversion : float
        Fraction of Na2CO3 converted.
    lime_equiv : float
        Molar Ca(OH)2 supplied per stoichiometric requirement.
        1.0 corresponds to the stoichiometric amount.
    """

    _N_ins = 2
    _N_outs = 1

    def __init__(
        self,
        ID="",
        ins=None,
        outs=(),
        conversion=_ATT_DOWNSTREAM["causticization_conversion"],
        lime_equiv=_ATT_DOWNSTREAM["lime_equiv"],
        target_temperature_K=_ATT_DOWNSTREAM["causticization_temperature_K"],
        heat_loss_fraction=_ATT_DOWNSTREAM["heat_loss_fraction"],
        lime_supplied=False,
        **kwargs,
    ):
        super().__init__(ID, ins, outs, **kwargs)
        # lime_supplied: the lime inlet is the dosed (recycled + makeup) lime of the system, not set here.
        self.lime_supplied = bool(lime_supplied)

        self.conversion = float(conversion)
        self.lime_equiv = float(lime_equiv)
        self.target_temperature_K = float(target_temperature_K)
        self.heat_loss_fraction = float(heat_loss_fraction)
        _att_add_proxy_exchanger(self, "heater", 1.0 / (1.0 + self.heat_loss_fraction))
        # Agitated reaction tank (holding time tau): BioSTEAM MixTank with its agitator power.
        tank = self.auxiliary("tank", bst.MixTank, ins=bst.Stream(None), tau=_EQUIPMENT["C1"]["tau_h"])
        self.register_auxiliary(tank, "tank")

        self.reaction = tmo.Reaction(
            "Na2CO3 + CaOH2 -> 2 NaOH + CaCO3",
            reactant="Na2CO3",
            X=self.conversion,
        )

    def _run(self):
        carbonate_solution, lime = self.ins
        slurry = self.outs[0]

        # Determine the stoichiometric Ca(OH)2 requirement from Na2CO3 feed.
        na2co3_kmolph = float(carbonate_solution.imol["Na2CO3"])
        required_lime_kmolph = na2co3_kmolph * self.lime_equiv

        # Automatically dose Ca(OH)2 (unless the system supplies the lime, as with lime recycle).
        if not self.lime_supplied:
            lime.empty()
            lime.imol["CaOH2"] = required_lime_kmolph
            lime.phase = "s"
        slurry.T = self.target_temperature_K
        slurry.P = carbonate_solution.P

        # Combine carbonate solution and lime.
        slurry.mix_from((carbonate_solution, lime))

        # Apply causticization reaction.
        self.reaction.X = self.conversion
        self.reaction(slurry)

        slurry.T = self.target_temperature_K
        slurry.P = carbonate_solution.P

        self._required_lime_kmolph = required_lime_kmolph

    def _design(self):
        carbonate_solution, lime = self.ins
        slurry = self.outs[0]

        # C1_FORMATION_ENTHALPY_PATCH_20261009
        # ThermoSTEAM .H is sensible/phase enthalpy; .Hnet = H + Hf.
        # Reactants -> products changes chemical composition, so ignoring
        # formation enthalpy silently omits the reaction heat.
        # This assumes the chemical Hf reference and phase identities
        # in create_chemicals() are thermodynamically compatible.
        inlet_sensible_kJph = float(carbonate_solution.H + lime.H)
        outlet_sensible_kJph = float(slurry.H)
        inlet_formation_kJph = float(carbonate_solution.Hf + lime.Hf)
        outlet_formation_kJph = float(slurry.Hf)

        inlet_enthalpy_kJph = float(carbonate_solution.Hnet + lime.Hnet)
        outlet_enthalpy_kJph = float(slurry.Hnet)
        formation_term_kJph = outlet_formation_kJph - inlet_formation_kJph
        sensible_term_kJph = outlet_sensible_kJph - inlet_sensible_kJph

        # A missing Hf must NOT be interpreted as a zero reaction heat.
        # Check the four reaction species before using corrected duties.
        reaction_ids = ('Na2CO3', 'CaOH2', 'NaOH', 'CaCO3')
        import math
        missing_hf = tuple(
            ID for ID in reaction_ids
            if (slurry.chemicals[ID].Hf is None
                or not math.isfinite(float(slurry.chemicals[ID].Hf))
                or abs(float(slurry.chemicals[ID].Hf)) < 1.0)
        )
        if missing_hf:
            raise ValueError(
                f'C1 chemical Hf missing/zero/nonfinite: {missing_hf}. '
                'Supply consistent standard heats of formation first.'
            )
        if abs(formation_term_kJph) < 1e-9:
            raise ValueError(
                'C1 formation enthalpy change is zero; chemical Hf may be '
                'missing or inconsistent. Check create_chemicals() rather '
                'than returning a misleading sensible-only duty.'
            )

        # C1_AQUEOUS_REFERENCE_PATCH_20261009
        # True C1 inlet/outlet salts are dissolved in aqueous mother liquor.
        # Native Hf is keyed to isolated species, often pure solid phase.
        # Replace only the salt formation references by the CRC 298.15 K
        # infinite-dilution aqueous-ion standards, NOT by molten NaOH Hf.
        # Concentrated-solution enthalpy is NOT included; its effect is
        # bounded at about -40 to +300 kJ/h (att.yaml c1_energy_basis_status).
        from biorefineries.sabre.analyses.att.thermodynamics import from_reactor_streams
        aqueous_reference = from_reactor_streams(carbonate_solution, lime, slurry)
        heat_duty_kJph = aqueous_reference.phase_reference_corrected_delta_kJph
        # The recorded in/out enthalpies and formation term must use the
        # *same* new reference basis as the duty (no mixed-basis metadata).
        inlet_enthalpy_kJph += aqueous_reference.inlet_correction_kJph
        outlet_enthalpy_kJph += aqueous_reference.outlet_correction_kJph
        formation_term_kJph += aqueous_reference.delta_correction_kJph
        self.design_results['C1 reaction formation enthalpy contribution'] = formation_term_kJph
        self._native_Hnet_heat_kJph = aqueous_reference.uncorrected_Hnet_delta_kJph
        self._aqueous_reference_correction_kJph = aqueous_reference.delta_correction_kJph
        self._aqueous_reference_scope = aqueous_reference.provenance
        self._energy_basis = 'Hnet_with_298K_aqueous_ion_standard_reference__concentrated_solution_enthalpy_bounded_not_modelled'
        self.design_results['C1 aqueous phase-reference correction'] = aqueous_reference.delta_correction_kJph
        self.design_results['C1 native Hnet heat before aqueous correction'] = aqueous_reference.uncorrected_Hnet_delta_kJph
        self._formation_reaction_heat_kJph = formation_term_kJph
        self._sensible_phase_heat_kJph = sensible_term_kJph
        # Step 7.16 scope superseded by aqueous reference scope above
        self.design_results['C1 reaction formation enthalpy contribution'] = formation_term_kJph
        self.design_results['C1 sensible and phase enthalpy contribution'] = sensible_term_kJph

        # Additional utility demand caused by heat loss.
        if heat_duty_kJph > 0:
            heat_loss_kJph = (
                heat_duty_kJph
                * self.heat_loss_fraction
            )
        else:
            heat_loss_kJph = 0.0

        utility_heat_duty_kJph = (
            heat_duty_kJph
            + heat_loss_kJph
        )

        # Register C1's calculated duty with BioSTEAM through an auxiliary
        # heater (water-equivalent proxy for the liquor, T_in -> T_out) that
        # is costed and can be matched by BioSTEAM's HeatExchangerNetwork.
        # The duty passed is the PROCESS duty (hu.unit_duty); the heat-loss
        # allowance enters through the heat-transfer efficiency, so it is not
        # counted twice. The duty lumps sensible heating and the (small)
        # reaction enthalpy.
        self.tank.ins[0].copy_like(self.outs[0])
        self.tank.simulate()
        if abs(heat_duty_kJph) > 1e-12:
            efficiency = (
                1.0 / (1.0 + self.heat_loss_fraction)
                if heat_duty_kJph > 0.0 else 1.0
            )
            mixed = bst.Stream(None)
            mixed.mix_from(self.ins)
            T_out = float(self.target_temperature_K)
            T_in = float(mixed.T)
            if abs(T_out - T_in) < 1.0:
                T_in = T_out - 1.0
            hx = _att_proxy_exchanger(self, "heater", heat_duty_kJph, T_in, T_out, hxn_ok=True)
            utility_heat_duty_kJph = sum(float(hu.duty) for hu in hx.heat_utilities)
            heat_loss_kJph = (
                utility_heat_duty_kJph - heat_duty_kJph
                if heat_duty_kJph > 0.0 else 0.0
            )
        else:
            utility_heat_duty_kJph = 0.0
            heat_loss_kJph = 0.0

        self._inlet_enthalpy_kJph = (
            inlet_enthalpy_kJph
        )
        self._outlet_enthalpy_kJph = (
            outlet_enthalpy_kJph
        )

        self._heat_duty_kJph = (
            heat_duty_kJph
        )
        self._thermal_power_kW = (
            heat_duty_kJph / 3600.0
        )

        self._heat_loss_kJph = (
            heat_loss_kJph
        )
        self._utility_heat_duty_kJph = (
            utility_heat_duty_kJph
        )
        self._utility_thermal_power_kW = (
            utility_heat_duty_kJph / 3600.0
        )

        self.design_results[
            "C1 inlet enthalpy"
        ] = inlet_enthalpy_kJph

        self.design_results[
            "C1 outlet enthalpy"
        ] = outlet_enthalpy_kJph

        self.design_results[
            "C1 net process heat duty"
        ] = heat_duty_kJph

        self.design_results[
            "C1 thermal power"
        ] = self._thermal_power_kW

        self.design_results[
            "C1 heat loss"
        ] = heat_loss_kJph

        self.design_results[
            "C1 utility heat duty"
        ] = utility_heat_duty_kJph

        self.design_results[
            "C1 utility thermal power"
        ] = self._utility_thermal_power_kW

# ======================================================================
# NaOH-Na2CO3-H2O recycle liquor: EC1 evaporator
# ======================================================================
_MW_NAOH = 39.997      # g/mol
_MW_NA2CO3 = 105.988   # g/mol
_LIQUOR_IDS = ("Water", "NaOH", "Na2CO3")


def _liquor_masses(stream, unit_ID):
    other = {
        chemical.ID: float(stream.imass[chemical.ID])
        for chemical in stream.chemicals
        if chemical.ID not in _LIQUOR_IDS and float(stream.imass[chemical.ID]) != 0.0
    }
    if other:
        raise RuntimeError(
            f"{unit_ID}: the NaOH-Na2CO3-H2O liquor model cannot handle {other}."
        )
    return tuple(float(stream.imass[ID]) for ID in _LIQUOR_IDS)


def _solid_na2co3_kgph(stream):
    if stream.phases and "s" in stream.phases:
        return float(stream.imass["s", "Na2CO3"])
    return float(stream.imass["Na2CO3"]) if stream.phase == "s" else 0.0


def aqueous_naoh_enthalpy_correction_kJph(stream):
    """
    Enthalpy of the dissolved NaOH in ``stream`` as NaOH(aq) minus
    ThermoSTEAM's value [kJ/h].

    ThermoSTEAM represents dissolved NaOH as pure (subcooled molten) liquid
    NaOH. In reality dissolving solid NaOH releases the heat of solution
    (att.yaml downstream.naoh_heat_of_solution_kJ_per_kg, infinite dilution,
    the same reference as the C1 aqueous-ion basis), which has to be paid
    back when the NaOH leaves the solution in U2. A single constant is used,
    so the heat of concentration of the recycle liquor in EC1 is lumped into
    this term and is not charged to EC1 separately.
    """
    naoh = float(stream.imass["NaOH"])
    if naoh <= 0.0:
        return 0.0
    T = float(stream.T)
    NaOH = stream.chemicals["NaOH"]
    real = -naoh * _NAOH_HEAT_OF_SOLUTION_kJ_per_kg          # relative to solid NaOH
    native = naoh / _MW_NAOH * (NaOH.H("l", T) - NaOH.H("s", T))
    return real - native


class NaOHEvaporator(bst.Unit):
    """
    EC1: single-effect vacuum evaporator for the NaOH-Na2CO3-H2O recycle
    liquor, operated at a fixed boiling temperature, with Na2CO3 salting-out.

    Only water in excess of ``max_water_kgph`` is evaporated; that limit is
    set by the system so the liquor reaches the target NaOH/(NaOH + H2O)
    after the fresh solid-NaOH makeup added in M1. If the liquor already
    holds less water, nothing is evaporated.

    Simple model (no electrolyte property correlations):
    * the vapor condenses at the boiling temperature minus a constant
      boiling-point elevation; the operating pressure is the water vapor
      pressure at that temperature;
    * process duty = latent heat of the evaporated water at the boiling
      temperature + sensible heat of the liquor; the heat of concentration
      and of Na2CO3 crystallization (together about 6 % of the duty) are
      neglected (see ``aqueous_naoh_enthalpy_correction_kJph``);
    * all but a fixed fraction of the Na2CO3 crystallizes (Na2CO3 is almost
      insoluble in concentrated caustic) and stays in the slurry;
    * vapor is condensed at its saturation temperature (cooling utility).

    The concentrate is returned at 1 atm by its extraction pump, whose
    work (<0.1 W at 1 kg/h dry feed) is neglected. Vacuum-system power
    and equipment cost are not modeled.

    outs: [0] slurry concentrate (l + s), [1] condensate.
    """

    line = "NaOH evaporator"
    _N_ins = 1
    _N_outs = 2

    def _init(self, T, heat_loss_fraction, max_water_kgph=float("inf"),
              boiling_point_elevation_K=None, na2co3_dissolved_fraction=None):
        self.T = float(T)
        self.heat_loss_fraction = float(heat_loss_fraction)
        _att_add_proxy_exchanger(self, "evaporator", 1.0 / (1.0 + self.heat_loss_fraction))
        _att_add_proxy_exchanger(self, "condenser")
        self.max_water_kgph = float(max_water_kgph)
        self.boiling_point_elevation_K = float(
            _ATT_DOWNSTREAM["ec1_boiling_point_elevation_K"]
            if boiling_point_elevation_K is None else boiling_point_elevation_K
        )
        self.na2co3_dissolved_fraction = float(
            _ATT_DOWNSTREAM["ec1_na2co3_dissolved_fraction"]
            if na2co3_dissolved_fraction is None else na2co3_dissolved_fraction
        )
        if not 0.0 <= self.na2co3_dissolved_fraction <= 1.0:
            raise ValueError("na2co3_dissolved_fraction must be between 0 and 1.")

    def _run(self):
        feed = self.ins[0]
        concentrate, condensate = self.outs
        water_in, naoh, carbonate = _liquor_masses(feed, self.ID)
        if _solid_na2co3_kgph(feed) > 0.0:
            raise RuntimeError(f"{self.ID}: feed must be a clear liquor.")
        if water_in <= 0.0:
            raise RuntimeError(f"{self.ID}: feed contains no water.")

        water_out = min(water_in, self.max_water_kgph)
        evaporated = water_in - water_out
        T = self.T if evaporated > 0.0 else float(feed.T)
        x_out = naoh / (naoh + water_out)

        dissolved = carbonate * self.na2co3_dissolved_fraction
        crystals = carbonate - dissolved

        concentrate.empty()
        concentrate.phases = ("l", "s")
        concentrate.imass["l", "Water"] = water_out
        concentrate.imass["l", "NaOH"] = naoh
        concentrate.imass["l", "Na2CO3"] = dissolved
        concentrate.imass["s", "Na2CO3"] = crystals
        concentrate.T = T
        concentrate.P = 101325.0

        condensate.empty()
        if evaporated > 0.0:
            T_condensation = T - self.boiling_point_elevation_K
            P = float(feed.chemicals["Water"].Psat(T_condensation))
            condensate.imass["Water"] = evaporated
            condensate.phase = "l"
            condensate.T = T_condensation
        else:
            P = None
            T_condensation = None
        condensate.P = 101325.0

        self._operating_pressure_Pa = P
        self._condensation_temperature_K = T_condensation
        self._evaporated_water_kgph = evaporated
        self._outlet_naoh_wt_frac_naoh_water = x_out
        self._na2co3_crystals_kgph = crystals
        self._na2co3_dissolved_kgph = dissolved

    def _design(self):
        feed = self.ins[0]
        evaporated = self._evaporated_water_kgph
        T_in, T = float(feed.T), float(self.outs[0].T)
        Water = feed.chemicals["Water"]

        latent = evaporated * Water.Hvap(T) / Water.MW           # kJ/h
        sensible = float(feed.C) * (T - T_in)                    # kJ/h
        duty = latent + sensible

        condenser = 0.0
        if evaporated > 0.0:
            T_c = self._condensation_temperature_K
            condenser = -evaporated * (
                Water.Hvap(T) + Water.H("l", T) - Water.H("l", T_c)
            ) / Water.MW

        # Evaporator heating (water evaporating at the operating temperature)
        # and condenser (water condensing at the condensation temperature)
        # are carried by auxiliary exchangers that BioSTEAM's
        # HeatExchangerNetwork can match. The condenser exchanger is costed;
        # the evaporator's heating surface is inside the evaporator
        # correlation costed in _cost() (the exchanger itself has zero cost).
        evaporator_hx = condenser_hx = None
        if duty > 0.0:
            evaporator_hx = _att_proxy_exchanger(self, "evaporator", duty, T, latent=True, costed=False)
        if condenser < 0.0:
            condenser_hx = _att_proxy_exchanger(
                self, "condenser", condenser, self._condensation_temperature_K,
                latent=True,
            )

        self._heat_duty_kJph = duty
        self._condenser_duty_kJph = condenser
        self._utility_heat_duty_kJph = sum(
            hu.duty for hx in (evaporator_hx, condenser_hx) if hx is not None
            for hu in hx.heat_utilities if hu.duty > 0.0
        )
        self._heat_loss_kJph = self._utility_heat_duty_kJph - max(duty, 0.0)
        self._specific_heat_kJ_per_kg_water = (
            duty / evaporated if evaporated > 0.0 else 0.0
        )
        P = self._operating_pressure_Pa
        self.design_results.update({
            "Evaporated water": evaporated,
            "Operating temperature": T,
            "Operating pressure": P if P is not None else 0.0,
            "Boiling-point elevation": (
                self.boiling_point_elevation_K if P is not None else 0.0
            ),
            "Outlet NaOH/(NaOH+H2O)": self._outlet_naoh_wt_frac_naoh_water,
            "Na2CO3 crystals": self._na2co3_crystals_kgph,
            "Process heat duty": duty,
            "Condenser duty": condenser,
        })
        self._units = {
            "Evaporated water": "kg/hr", "Operating temperature": "K",
            "Operating pressure": "Pa", "Boiling-point elevation": "K",
            "Outlet NaOH/(NaOH+H2O)": "-", "Na2CO3 crystals": "kg/hr",
            "Process heat duty": "kJ/hr", "Condenser duty": "kJ/hr",
        }

    _F_BM_default = {"Forced-circulation evaporator": 2.45, "Vacuum system": 1.0}

    def _cost(self):
        """Forced-circulation evaporator (Seider et al.) and the vacuum system for air in-leakage."""
        e = _EQUIPMENT["EC1"]
        hx = self.hxn_evaporator
        steam = [hu for hu in hx.heat_utilities if hu.duty > 0.0]
        if steam:
            Q = sum(hu.unit_duty for hu in steam)                      # kJ/h
            dT = steam[0].agent.T - float(self.T)
            area_m2 = Q / (e["U_W_per_m2_K"] * 3.6 * dT)
            # Seider et al. forced-circulation evaporator, A in ft2 (150-8000 ft2 per unit), CE 500.
            area_ft2 = area_m2 * 10.7639
            n = max(1, ceil(area_ft2 / 8000.0))
            lnA = log(area_ft2 / n)
            self.baseline_purchase_costs["Forced-circulation evaporator"] = (
                n * bst.CE / 500.0 * exp(8.2986 + 0.5329 * lnA - 0.000196 * lnA * lnA))
            self.design_results["Evaporator area"] = area_m2
            self._units["Evaporator area"] = "m2"
            liquor_m3ph = float(self.ins[0].F_mass) / e["liquor_density_kg_per_m3"]
            vessel_m3 = liquor_m3ph * e["vessel_holdup_h"] / e["vessel_fill_fraction"]
            vacuum = compute_vacuum_system_power_and_cost(0.0, 0.0, self._operating_pressure_Pa, vessel_m3)
            self.baseline_purchase_costs["Vacuum system"] = vacuum["Cost"]
            self.add_power_utility(vacuum["Work"])
