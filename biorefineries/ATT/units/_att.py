# Bioindustrial-Park: BioSTEAM's Premier Biorefinery Models and Results
# Copyright (C) 2026-, Yu Zhou,
#                      Yalin Li <mailto.yalin.li@gmail.com>
#
# This module is under the UIUC open-source license. See
# github.com/BioSTEAMDevelopmentGroup/biosteam/blob/master/LICENSE.txt
# for license details.

from math import ceil, exp, log, pi

import biosteam as bst
import thermosteam as tmo
from biosteam.units.design_tools import PressureVessel
from biosteam.units.design_tools.specification_factors import pressure_vessel_material_factors
from biosteam.units.design_tools.vacuum import compute_vacuum_system_power_and_cost
from biosteam.units.heat_exchange import compute_furnace_purchase_cost

from biorefineries.ATT.utils import load_assumptions

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
    "ATTPSA",
    "ATTScrubber",
)

_ATT_DATA = load_assumptions("att.yaml")["att"]

_ATT = _ATT_DATA["reactor"]
_ATT_DOWNSTREAM = _ATT_DATA["downstream"]
_EQUIPMENT = _ATT_DATA["inventory"]["cost_estimates"]   # sizing of equipment BioSTEAM has no unit model for
_NAOH_HEAT_OF_SOLUTION_kJ_per_kg = float(_ATT_DOWNSTREAM["naoh_heat_of_solution_kJ_per_kg"])

_SARGASSUM_DRY_IDS = (
    "Ash",
    "NaCl",       # soluble ash salts (att.yaml feed_preparation.ash_split); with Ash they are the inorganic part of the dry feed
    "KCl",
    "REO",        # rare earth oxides of the seaweed (att.yaml downstream.ree_recovery)
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


def _set_lime_stream(stream, ca_oh2_kmolph):
    """
    Fill ``stream`` with the lime that carries ``ca_oh2_kmolph`` of Ca(OH)2: the waste carbide lime paste of
    att.yaml downstream.waste_lime (Ca(OH)2 with CaCO3 and inert mineral impurities and water) or, if that is
    disabled, pure Ca(OH)2.
    """
    stream.empty()
    cfg = _ATT_DOWNSTREAM.get("waste_lime", {})
    if not cfg.get("enabled", False):
        stream.phase = "s"
        stream.imol["CaOH2"] = ca_oh2_kmolph
        return
    frac = cfg["dry_basis_wt_frac"]
    dry_kgph = ca_oh2_kmolph * 74.09268 / float(frac["CaOH2"])
    stream.phase = "l"
    stream.imass["CaOH2"] = dry_kgph * float(frac["CaOH2"])
    stream.imass["CaCO3"] = dry_kgph * float(frac["CaCO3"])
    stream.imass["LimeInerts"] = dry_kgph * float(frac["LimeInerts"])
    moisture = float(cfg["moisture_wt_frac"])
    stream.imass["Water"] = dry_kgph * moisture / (1.0 - moisture)
    stream.T = 298.15


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
    outlet temperature). Its duty is matched in the heat exchanger network at the assumed interstage
    temperature (att.yaml heat_recovery.u3k_interstage_temperature_K).
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
                                 hxn_ok=True)


class ATTMolecularSieve(bst.MolecularSieve):
    """
    MolecularSieve whose regeneration heating and cooling duties are carried
    by costed auxiliary exchangers (water proxy at ``regeneration_T_K``).
    Both duties are matched in the heat exchanger network (BioSTEAM's duties, at the assumed regeneration
    temperature of att.yaml heat_recovery.u3d_regeneration_temperature_K).
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
                                     hxn_ok=True)
            else:
                _att_proxy_exchanger(self, "regeneration_cooler", hu.unit_duty, self.regeneration_T_K, T_in,
                                     hxn_ok=True)



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


class ATTScrubber(bst.Unit):
    """
    Lime-slurry gas scrubber: the cooled gas (after the condensate separator U3C) bubbles through a Ca(OH)2 slurry,
    Ca(OH)2 + CO2 -> CaCO3 + H2O (carbonation). Only the CO2 is modeled; the slurry would also take other acid gases
    (H2S, HCl, SO2), which the model does not carry. ``co2_capture`` of the CO2 is fixed; the lime fed is
    ``lime_excess`` x the CO2 captured (set here); the slurry water is the recycled filtrate (ins[2]) plus a
    makeup (ins[3], set here) so that the slurry leaves at ``slurry_solids_wt_frac`` solids. The reaction heat is
    removed by a costed auxiliary cooler (water proxy) to ``T``. PRELIMINARY costing: a stirred slurry tank with
    ``tau_h`` residence time; the gas-liquid contactor internals, blower and pressure drop are not costed.
    ins: [0] cooled gas, [1] lime (waste Ca(OH)2), [2] recycled filtrate, [3] makeup water.
    outs: [0] scrubbed gas, [1] CaCO3 slurry (to the dewatering filter).
    """
    _N_ins = 4
    _N_outs = 2

    def _init(self, T=313.15, co2_capture=0.99, lime_excess=1.1, slurry_solids_wt_frac=0.25, tau_h=0.5):
        self.T = float(T)
        self.co2_capture = float(co2_capture)
        self.lime_excess = float(lime_excess)
        self.slurry_solids_wt_frac = float(slurry_solids_wt_frac)
        _att_add_proxy_exchanger(self, "cooler")
        tank = self.auxiliary("tank", bst.MixTank, ins=bst.Stream(None), tau=float(tau_h))
        self.register_auxiliary(tank, "tank")

    def _run(self):
        gas, lime, filtrate, makeup = self.ins
        scrubbed, slurry = self.outs
        n_co2 = float(gas.imol["CO2"])
        captured = self.co2_capture * n_co2
        unreacted = (self.lime_excess - 1.0) * captured
        _set_lime_stream(lime, self.lime_excess * captured)
        lime_caco3, lime_inerts = float(lime.imol["CaCO3"]), float(lime.imol["LimeInerts"])
        lime_water = float(lime.imol["Water"])
        solids_kg = (captured + lime_caco3) * 100.0869 + unreacted * 74.09268 + float(lime.imass["LimeInerts"])
        water_target_kmol = solids_kg * (1.0 - self.slurry_solids_wt_frac) / self.slurry_solids_wt_frac / 18.01528
        makeup.empty()
        makeup.phase, makeup.T = "l", 298.15
        # Filtrate water the slurry needs besides the lime water and the reaction water (the system returns only this much
        # of the F3 filtrate to the scrubber; the rest of it is process water).
        self.filtrate_demand_kgph = max(water_target_kmol - captured - lime_water, 0.0) * 18.01528
        makeup.imol["Water"] = max(water_target_kmol - captured - lime_water - float(filtrate.imol["Water"]), 0.0)
        scrubbed.copy_like(gas)
        scrubbed.imol["CO2"] = n_co2 - captured
        scrubbed.T = self.T
        slurry.empty()
        slurry.phase = "l"
        slurry.imol["CaCO3"] = captured + lime_caco3
        slurry.imol["CaOH2"] = unreacted
        slurry.imol["LimeInerts"] = lime_inerts
        slurry.imol["Water"] = float(filtrate.imol["Water"]) + float(makeup.imol["Water"]) + lime_water + captured
        slurry.T, slurry.P = self.T, gas.P

    def _design(self):
        slurry = self.outs[1]
        duty = float(sum(s.Hnet for s in self.outs) - sum(s.Hnet for s in self.ins))     # kJ/h, negative: heat released
        self.tank.ins[0].copy_like(slurry)
        self.tank.simulate()
        if duty < 0.0:
            _att_proxy_exchanger(self, "cooler", duty, self.T + 20.0, self.T, hxn_ok=True)


class ATTResidueSplit(bst.Unit):
    """
    RS1: partition of the cooled ATT residue into the insoluble CHAR that goes to the dissolver and the part of the lumped residual
    carbon that is not tracked (att.yaml downstream.char, user decision 2026-11-03).

    The insoluble solids leaving the water dissolution are ``char_yield`` g per g of dry feed (the collaborator's ATT mass balance,
    10-20 wt %): the insoluble seaweed minerals (Ash), the N and S char and an organic char (``char_species``, CH0.5O0.1) that
    takes the rest of that mass. The remaining lumped residue (U2's elemental-closure surrogate, same H/C) leaves as
    ``untracked_organics``: its carbon has no measured sink, is neither credited nor treated, and no element is created
    (the split conserves C, H and O exactly). U2 itself, and so its heat duty, is not changed.
    ins: [0] cooled residue. outs: [0] char residue (to D1), [1] untracked organics.
    """
    _N_ins = 1
    _N_outs = 2

    def _init(self, char_yield, dry_feed_kgph, char_species="Char", lumped_species=("ResidueCH", "ResidueCHO")):
        self.char_yield = float(char_yield)
        self.dry_feed_kgph = dry_feed_kgph                       # callable: dry feed [kg/h]
        self.char_species = char_species
        self.lumped_species = tuple(lumped_species)

    def _run(self):
        res = self.ins[0]
        char, lost = self.outs
        char.copy_like(res)
        lost.empty()
        lost.phase = "s"
        lost.T, lost.P = res.T, res.P
        ch, cho = self.lumped_species
        c_res = float(res.imol[ch] + res.imol[cho])
        o_res = 2.0 * float(res.imol[cho])
        char.imol[ch] = 0.0
        char.imol[cho] = 0.0
        mineral_kgph = float(res.imass["Ash"] + res.imass["CharN"] + res.imass["CharS"])
        organic_kgph = self.char_yield * float(self.dry_feed_kgph()) - mineral_kgph
        if organic_kgph < 0.0:
            raise ValueError(f"RS1: the char yield {self.char_yield} g/g is below the mineral and N, S char of the residue "
                             f"({mineral_kgph:.1f} kg/h of {self.char_yield * float(self.dry_feed_kgph()):.1f} kg/h)")
        spec = res.chemicals[self.char_species]
        n_char = organic_kgph / spec.MW                          # kmol/h of CH_aO_b = kmol C/h
        o_char = n_char * spec.atoms.get("O", 0.0) / spec.atoms["C"]
        if n_char > c_res * (1.0 + 1e-9) or o_char > o_res * (1.0 + 1e-9):
            raise ValueError("RS1: the organic char would hold more C or O than the lumped residue of U2")
        char.imol[self.char_species] = n_char
        c_left, o_left = c_res - n_char, o_res - o_char
        lost.imol[cho] = o_left / 2.0
        lost.imol[ch] = c_left - o_left / 2.0


class ATTSaltCrystallizer(bst.Unit):
    """
    XL1: removes the soluble ash salts (NaCl, KCl) from the NaOH recycle liquor (the EC1 concentrate, 50 wt % NaOH, in which they
    are nearly insoluble): a crystallizer vessel and a solids centrifuge. ``removal`` of each salt leaves in the salt cake, which
    holds ``cake_liquor_wt_frac`` of entrained liquor (its NaOH is lost). Costing: BioSTEAM MixTank (``tau_h``) and SolidsCentrifuge
    sized on the EC1 concentrate with the crystals as the solids; PRELIMINARY (carbon-steel/stainless defaults, no nickel
    alloy, no cooling or evaporation duty, no solubility data: the removal fraction is an input).
    ins: [0] EC1 concentrate. outs: [0] clarified liquor (the NaOH recycle), [1] salt cake.
    """
    _N_ins = 1
    _N_outs = 2

    def _init(self, salts=("NaCl", "KCl"), removal=0.99, cake_liquor_wt_frac=0.10, tau_h=2.0):
        self.salts = tuple(salts)
        self.removal = float(removal)
        self.cake_liquor_wt_frac = float(cake_liquor_wt_frac)
        vessel = self.auxiliary("vessel", bst.MixTank, ins=bst.Stream(None), tau=float(tau_h))
        self.register_auxiliary(vessel, "vessel")
        separator = self.auxiliary("separator", bst.SolidsCentrifuge, ins=bst.Stream(None),
                                   outs=(bst.Stream(None), bst.Stream(None)), split={"Ash": 0.99}, moisture_content=self.cake_liquor_wt_frac)
        self.register_auxiliary(separator, "separator")

    def _run(self):
        feed = self.ins[0]
        liquor, cake = self.outs
        liquor.copy_like(feed)
        cake.empty()
        cake.phases = liquor.phases                     # the cake keeps the phase of every species (energy is conserved)
        cake.T, cake.P = feed.T, feed.P
        for ID in self.salts:
            n = self.removal * float(feed.imol[ID])
            liquor.imol["l", ID] -= n
            cake.imol["l", ID] += n
        salt_kgph = float(cake.F_mass)
        entrained = salt_kgph * self.cake_liquor_wt_frac / (1.0 - self.cake_liquor_wt_frac)      # kg/h of liquor in the cake
        share = min(entrained / float(liquor.F_mass), 1.0) if float(liquor.F_mass) > 0.0 else 0.0
        for phase in liquor.phases:
            for chemical in liquor.chemicals:
                ID = chemical.ID
                moved = share * float(liquor.imass[phase, ID])
                liquor.imass[phase, ID] -= moved
                cake.imass[phase, ID] += moved

    def _design(self):
        feed = self.ins[0]
        self.vessel.ins[0].copy_like(feed)
        self.vessel.simulate()
        sep_in = self.separator.ins[0]
        sep_in.empty()
        sep_in.phase = "l"
        sep_in.T, sep_in.P = feed.T, feed.P
        for chemical in feed.chemicals:
            if chemical.ID not in self.salts:
                sep_in.imass[chemical.ID] = float(feed.imass[chemical.ID])
        sep_in.imass["Ash"] = self.removal * sum(float(feed.imass[ID]) for ID in self.salts)     # the crystals as the solids of the separator
        self.separator.simulate()


class ATTReeLeach(bst.Unit):
    """
    LC1: HCl leach of the washed ATT char cake and oxalate precipitation of the rare earths (att.yaml downstream.ree_recovery).
    PERFORMANCE-SPECIFIED. The reagent doses are the lab's per g of char (5 mL of 0.1 M HCl, 0.42 mL of 0.1 M oxalic acid). Only the
    oxalate precipitate is roasted: its REO is ``overall_recovery`` of the REE of the initial wastewater (the wastewater TREE per g
    of seaweed, ``wastewater_TREE_mg_per_L`` / ``seaweed_dose_g_per_L``), capped by the oxalate stoichiometry (``oxalate_per_REE`` mol of
    oxalate per mol of REE, REE molar mass ``REE_molar_mass``); the oxalate carries ``product_REO_wt_frac`` of REO after the roast,
    the rest being mineral filler taken from the char's Ash (the Ca and Mg balance is not tracked: user decision 2026-11-03). The
    leached char (with the REO that was not recovered) leaves as ``ash_residue_cake``. The HCl is neutralized by the Na2CO3 and
    NaOH of the cake liquor (CO2 leaves as ``leach_co2``), with fresh NaOH for any acid left. Both cakes keep
    ``cake_moisture_wt_frac`` of liquor; the rest is the spent leachate (water, NaCl, KCl, Na2CO3), recycled to the dissolver D1.
    Equipment (BioSTEAM MixTank and PressureFilter) is only for costing.
    ins: [0] char cake, [1] 31 wt % HCl, [2] oxalic acid, [3] fresh leach water (makeup, set here), [4] NaOH for the acid left,
    [5] condensate for the leach liquor (from the system; used first).
    outs: [0] roaster feed (oxalate precipitate), [1] spent leachate, [2] leached char (the residue product), [3] leach CO2.
    """
    _N_ins = 6
    _N_outs = 4
    _DISSOLVED = ("Water", "Na2CO3", "NaOH", "NaCl", "KCl")

    def _init(self, dry_feed_kgph, hcl_mol_per_kg_char=0.5, leach_liquor_kg_per_kg_char=5.0, oxalic_mol_per_kg_char=0.042,
              oxalate_solution_kg_per_kg_char=0.42, cake_moisture_wt_frac=0.30, leach_tau_h=1.0, oxalate_tau_h=0.5,
              wastewater_TREE_mg_per_L=1.4, seaweed_dose_g_per_L=2.5, overall_recovery=0.6, product_REO_wt_frac=0.0131,
              REO_per_TREE=1.169, REE_molar_mass=149.1, oxalate_per_REE=1.5, scale_reagents_with_REE=False, hcl_mol_per_mol_REE=3.0,
              reagent_excess=1.2, precipitate_wash_efficiency=0.0):
        self.dry_feed_kgph = dry_feed_kgph                       # callable: dry seaweed feed [kg/h]
        self.hcl_mol_per_kg_char = float(hcl_mol_per_kg_char)
        self.leach_liquor_kg_per_kg_char = float(leach_liquor_kg_per_kg_char)
        self.oxalic_mol_per_kg_char = float(oxalic_mol_per_kg_char)
        self.oxalate_solution_kg_per_kg_char = float(oxalate_solution_kg_per_kg_char)
        self.cake_moisture_wt_frac = float(cake_moisture_wt_frac)
        self.wastewater_TREE_mg_per_L = float(wastewater_TREE_mg_per_L)
        self.seaweed_dose_g_per_L = float(seaweed_dose_g_per_L)
        self.overall_recovery = float(overall_recovery)
        self.product_REO_wt_frac = float(product_REO_wt_frac)
        self.REO_per_TREE = float(REO_per_TREE)
        self.REE_molar_mass = float(REE_molar_mass)
        self.oxalate_per_REE = float(oxalate_per_REE)
        self.scale_reagents_with_REE = bool(scale_reagents_with_REE)
        self.hcl_mol_per_mol_REE = float(hcl_mol_per_mol_REE)
        self.reagent_excess = float(reagent_excess)
        self.precipitate_wash_efficiency = float(precipitate_wash_efficiency)   # share of the entrained salts washed out of the oxalate cake
        self._hcl_mol_per_kg_eff = self.hcl_mol_per_kg_char               # doses actually used (per kg of char solids), set in _run
        self._oxalic_mol_per_kg_eff = self.oxalic_mol_per_kg_char
        _att_add_proxy_exchanger(self, "cooler")
        _att_add_proxy_exchanger(self, "heater")
        for name, cls, kw in (("leach_tank", bst.MixTank, dict(tau=float(leach_tau_h))), ("oxalate_tank", bst.MixTank, dict(tau=float(oxalate_tau_h)))):
            aux = self.auxiliary(name, cls, ins=bst.Stream(None), **kw)
            self.register_auxiliary(aux, name)
        for name in ("leach_filter", "oxalate_filter"):
            aux = self.auxiliary(name, bst.PressureFilter, ins=bst.Stream(None), outs=(bst.Stream(None), bst.Stream(None)),
                                 split={"Ash": 1.0}, moisture_content=self.cake_moisture_wt_frac)
            self.register_auxiliary(aux, name)

    def water_demand_kgph(self, solids_kgph):
        """Water of the leach liquor and of the oxalic acid solution [kg/h] (the HCl solution brings its own)."""
        hcl_solution = self._hcl_mol_per_kg_eff * solids_kgph / 1e3 * 36.46094 / 0.31
        return max(self.leach_liquor_kg_per_kg_char * solids_kgph - hcl_solution, 0.0) + self.oxalate_solution_kg_per_kg_char * solids_kgph

    def _run(self):
        cake, hcl, ox, water, fresh_naoh, condensate = self.ins
        roast, leachate, residue, co2 = self.outs
        chem = cake.chemicals
        solid_IDs = [c.ID for c in chem if c.ID not in self._DISSOLVED and float(cake.imass[c.ID]) > 0.0]
        solids_kgph = sum(float(cake.imass[ID]) for ID in solid_IDs)
        # reagents: the lab doses per kg of char; with scale_reagents_with_REE the stoichiometry of the REE of the char (3 mol HCl per mol REE,
        # oxalate_per_REE mol oxalate per mol REE, times reagent_excess) is used when it needs more (a char with far more REE than the lab's)
        n_ree_char = float(cake.imass["REO"]) / self.REO_per_TREE / self.REE_molar_mass         # kmol REE/h in the char
        hcl_kmol = self.hcl_mol_per_kg_char * solids_kgph / 1e3
        oxalic_kmol = self.oxalic_mol_per_kg_char * solids_kgph / 1e3
        if self.scale_reagents_with_REE:
            hcl_kmol = max(hcl_kmol, self.hcl_mol_per_mol_REE * n_ree_char * self.reagent_excess)
            oxalic_kmol = max(oxalic_kmol, self.oxalate_per_REE * n_ree_char * self.reagent_excess)
        self._hcl_mol_per_kg_eff = hcl_kmol * 1e3 / solids_kgph if solids_kgph > 0.0 else self.hcl_mol_per_kg_char
        self._oxalic_mol_per_kg_eff = oxalic_kmol * 1e3 / solids_kgph if solids_kgph > 0.0 else self.oxalic_mol_per_kg_char
        hcl.empty()
        hcl.phase = "l"
        hcl.imol["HCl"] = hcl_kmol
        hcl.imass["Water"] = float(hcl.imass["HCl"]) * (1.0 / 0.31 - 1.0)
        ox.empty()
        ox.phase = "s"
        ox.imol["OxalicAcid"] = oxalic_kmol
        water.empty()
        water.phase = "l"
        makeup = self.water_demand_kgph(solids_kgph) - float(condensate.imass["Water"])
        water.imass["Water"] = makeup if makeup > 1e-6 else 0.0                       # fresh makeup only, no roundoff dust
        # dissolved pool of the leach slurry (cake liquor + reagent water)
        pool = {ID: float(cake.imass[ID]) for ID in self._DISSOLVED}
        pool["Water"] += float(hcl.imass["Water"]) + float(water.imass["Water"]) + float(condensate.imass["Water"])
        # neutralization of the HCl: Na2CO3 + 2 HCl -> 2 NaCl + H2O + CO2, NaOH + HCl -> NaCl + H2O, then fresh NaOH
        mw = {ID: chem[ID].MW for ID in ("Na2CO3", "NaOH", "NaCl", "Water")}
        n_na2co3, n_naoh = pool["Na2CO3"] / mw["Na2CO3"], pool["NaOH"] / mw["NaOH"]
        by_carbonate = min(n_na2co3, hcl_kmol / 2.0)
        left = hcl_kmol - 2.0 * by_carbonate
        by_naoh = min(n_naoh, left)
        left -= by_naoh
        fresh_naoh.empty()
        fresh_naoh.phase = "s"
        fresh_naoh.imol["NaOH"] = left
        nacl_kmol = 2.0 * by_carbonate + by_naoh + left
        pool["Na2CO3"] -= by_carbonate * mw["Na2CO3"]
        pool["NaOH"] -= by_naoh * mw["NaOH"]
        pool["NaCl"] += nacl_kmol * mw["NaCl"]
        pool["Water"] += (by_carbonate + by_naoh + left) * mw["Water"]
        co2.empty()
        co2.phase = "g"
        co2.imol["CO2"] = by_carbonate
        co2.T, co2.P = cake.T, cake.P
        # REE: the product REO is overall_recovery of the REO of the initial wastewater, within the oxalate stoichiometry
        reo_char = float(cake.imass["REO"])
        reo_water = self.wastewater_TREE_mg_per_L / self.seaweed_dose_g_per_L * 1e-3 * float(self.dry_feed_kgph()) * self.REO_per_TREE
        n_ree_char = reo_char / self.REO_per_TREE / self.REE_molar_mass                       # kmol REE/h in the char
        self._stoich_ceiling = min(1.0, float(ox.imol["OxalicAcid"]) / (self.oxalate_per_REE * n_ree_char)) if n_ree_char > 0.0 else 1.0
        reo_product = min(self.overall_recovery * reo_water, self._stoich_ceiling * reo_char)
        self._reo_wastewater, self._reo_product = reo_water, reo_product
        # the oxalate precipitate (REO + oxalic acid + mineral filler from the char's Ash) and its liquor
        target_kgph = reo_product / self.product_REO_wt_frac                                   # roasted product [kg/h]
        w = self.cake_moisture_wt_frac
        salts = 0.0
        for _ in range(2):                                                                     # the entrained salts stay in the product
            filler = max(target_kgph - reo_product - salts, 0.0)
            solids_p = reo_product + filler + float(ox.imass["OxalicAcid"])
            share_p = min(solids_p * w / (1.0 - w) / pool["Water"], 1.0)
            salts = share_p * sum(pool[ID] for ID in ("NaCl", "KCl", "Na2CO3", "NaOH")) * (1.0 - self.precipitate_wash_efficiency)
        ash_char = float(cake.imass["Ash"])
        if filler > ash_char:
            raise ValueError(f"LC1: the mineral filler of the product ({filler:.1f} kg/h) exceeds the Ash of the char ({ash_char:.1f} kg/h)")
        residue_solids = {ID: float(cake.imass[ID]) for ID in solid_IDs}
        residue_solids["Ash"] = ash_char - filler
        residue_solids["REO"] = reo_char - reo_product
        solids_r = sum(residue_solids.values())
        share_r = min(solids_r * w / (1.0 - w) / pool["Water"], 1.0 - share_p)
        roast.empty()
        residue.empty()
        leachate.empty()
        roast.phase = residue.phase = leachate.phase = "l"
        roast.imass["REO"], roast.imass["Ash"] = reo_product, filler
        roast.imol["OxalicAcid"] = float(ox.imol["OxalicAcid"])
        for ID, kgph in residue_solids.items():
            residue.imass[ID] = kgph
        for ID, kgph in pool.items():       # the washed-out salts of the oxalate cake go to the spent leachate (wash water is not modeled)
            roast.imass[ID] = share_p * kgph * ((1.0 - self.precipitate_wash_efficiency) if ID in ("NaCl", "KCl", "Na2CO3", "NaOH") else 1.0)
            residue.imass[ID] = share_r * kgph
            leachate.imass[ID] = kgph - float(roast.imass[ID]) - float(residue.imass[ID])
        for s in (roast, leachate, residue):
            s.T, s.P = cake.T, cake.P

    def _design(self):
        cake, hcl, ox, water, fresh_naoh, condensate = self.ins
        roast, leachate, residue, co2 = self.outs
        # heat of neutralization and dissolution (the unit is isothermal): a heater or cooler of the water proxy
        duty = float(sum(s.Hnet for s in self.outs) - sum(s.Hnet for s in self.ins))
        if duty < 0.0:
            _att_proxy_exchanger(self, "cooler", duty, float(cake.T) + 10.0, float(cake.T), hxn_ok=True)
        elif duty > 0.0:
            _att_proxy_exchanger(self, "heater", duty, float(cake.T), float(cake.T) + 10.0, hxn_ok=True)
        total = self.leach_tank.ins[0]
        total.mix_from([cake, hcl, ox, water, fresh_naoh, condensate])
        self.leach_tank.simulate()
        solids = sum(float(cake.imass[c.ID]) for c in cake.chemicals if c.ID not in self._DISSOLVED)
        precipitate = float(roast.F_mass - roast.imass["Water"] - sum(roast.imass[ID] for ID in ("NaCl", "KCl", "Na2CO3", "NaOH")))
        for aux, kgph_solids, liquid in ((self.leach_filter, solids, total), (self.oxalate_filter, precipitate, leachate)):
            fin = aux.ins[0]
            fin.empty()
            fin.phase = "l"
            fin.T, fin.P = cake.T, cake.P
            for c in liquid.chemicals:
                if c.ID in self._DISSOLVED:
                    fin.imass[c.ID] = float(liquid.imass[c.ID])
            fin.imass["Ash"] = kgph_solids
            aux.simulate()
        ot = self.oxalate_tank.ins[0]
        ot.copy_like(leachate)
        ot.imass["Water"] = float(leachate.imass["Water"]) + float(self.oxalate_solution_kg_per_kg_char) * solids
        self.oxalate_tank.simulate()


class ATTReeRoaster(bst.Unit):
    """
    RO1: roaster (rotary kiln, 900 C) of the REE oxalate precipitate of LC1 (att.yaml downstream.ree_recovery). The oxalic acid burns
    in the air (C -> CO2, H -> H2O), the cake water evaporates, the REO, the mineral filler and the salts stay as the roasted
    ``ree_product`` (``product_REO_wt_frac`` of REO), which is sold on its REO content. The solids leave cooled to
    363 K and the exhaust at 473 K (the heat of the hot streams is recovered inside the kiln); the net
    heat duty is natural gas through an auxiliary furnace with ``heat_loss_fraction`` on it, or a cooler if the char burns
    hotter than the kiln needs. The Ca/Mg minerals are inert in this model (no calcination heat or CO2). Shell cost: BioSTEAM
    drum-dryer correlation on a shell area per t/d of feed solids, times a refractory factor (PRELIMINARY).
    ins: [0] roaster feed, [1] air (set here). outs: [0] roasted product, [1] exhaust.
    """
    _N_ins = 2
    _N_outs = 2
    auxiliary_unit_names = ("heat_exchanger",)
    _F_BM_default = {"Rotary kiln": 2.06}
    _units = {"Feed solids": "t/d", "Kiln shell area": "m2"}

    def _init(self, temperature_K=1173.15, excess_air=0.2, heat_loss_fraction=0.45, area_m2_per_t_per_day=3.14,
              refractory_factor=2.0, solids_outlet_K=363.15, exhaust_K=473.15):
        self.excess_air = float(excess_air)
        self.heat_loss_fraction = float(heat_loss_fraction)
        self.area_m2_per_t_per_day = float(area_m2_per_t_per_day)
        self.refractory_factor = float(refractory_factor)
        self.solids_outlet_K = float(solids_outlet_K)
        self.exhaust_K = float(exhaust_K)
        _att_add_proxy_exchanger(self, "cooler")
        self.auxiliary("heat_exchanger", bst.HXutility, ins=bst.Stream(None), T=float(temperature_K), rigorous=False, heat_only=True,
                       heat_transfer_efficiency=1.0 / (1.0 + self.heat_loss_fraction))

    def _run(self):
        feed, air = self.ins
        prod, exhaust = self.outs
        chem = feed.chemicals
        prod.copy_like(feed)
        exhaust.empty()
        exhaust.phase = "g"
        c = h = o = 0.0
        for ID in ("Char", "OxalicAcid"):
            n = float(feed.imol[ID])
            atoms = chem[ID].atoms
            c, h, o = c + n * atoms.get("C", 0.0), h + n * atoms.get("H", 0.0), o + n * atoms.get("O", 0.0)
            prod.imol[ID] = 0.0
        n_o2 = c + h / 4.0 - o / 2.0
        n_nitrogen = float(feed.imol["CharN"])
        prod.imol["CharN"] = 0.0
        o2_air = n_o2 * (1.0 + self.excess_air)
        air.empty()
        air.phase = "g"
        air.imol["Oxygen"] = o2_air
        air.imol["Nitrogen"] = o2_air * 79.0 / 21.0
        air.T, air.P = 298.15, 101325.0
        exhaust.imol["CO2"] = c
        exhaust.imol["Water"] = float(feed.imol["Water"]) + h / 2.0
        exhaust.imol["Nitrogen"] = float(air.imol["Nitrogen"]) + n_nitrogen / 2.0
        exhaust.imol["Oxygen"] = o2_air - n_o2
        prod.imol["Water"] = 0.0
        prod.phase = "l"
        prod.T, exhaust.T = self.solids_outlet_K, self.exhaust_K
        prod.P = exhaust.P = feed.P

    def _design(self):
        feed, air = self.ins
        prod, exhaust = self.outs
        duty = float(prod.Hnet + exhaust.Hnet - feed.Hnet - air.Hnet)       # kJ/h, net of the internal heat recovery
        hx = self.heat_exchanger
        if duty > 0.0:
            hx.ins[0].copy_like(feed)
            hx.outs[0].copy_like(feed)
            hx.outs[0].T = hx.T
            hx.simulate(run=False, design_kwargs={"duty": duty})
        else:
            hx.baseline_purchase_costs.clear()
            if duty < 0.0:
                _att_proxy_exchanger(self, "cooler", duty, self.exhaust_K + 20.0, self.exhaust_K, hxn_ok=False)
        solids_tpd = float(feed.F_mass - feed.imass["Water"]) * 24.0 / 1e3
        self.design_results["Feed solids"] = solids_tpd
        self.design_results["Kiln shell area"] = self.area_m2_per_t_per_day * solids_tpd
        self.design_results["Net heat duty"] = duty
        self._units["Net heat duty"] = "kJ/hr"

    def _cost(self):
        area = self.design_results["Kiln shell area"]
        if area > 0.0:
            ratio = area / 1235.35
            self.baseline_purchase_costs["Rotary kiln"] = 0.52 * 2268000.0 * bst.CE / 525.4 * ratio ** 0.6 * self.refractory_factor
            self.add_power_utility(938.866 * ratio ** 0.6)


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


def close_att_u2_balance(feed_atoms, fixed_atoms, specified_gas_kmolph, species_atoms, lumped_atoms):
    """
    Specified-yield U2 closure: the gas yields are inputs and are never
    changed. Carbon that is not in the specified gases or the carbonate (the
    residual carbon) leaves as the lumped residual product CH_aO_b, a
    stoichiometric surrogate (not measured char). a is the H/C of the two
    basis species in ``lumped_atoms`` ({ID: atoms}, end members b = 0 and
    b = 2); the product water closes H and b closes O, so C, H and O (and with
    them mass and electrons) all balance. Requires water >= 0 and 0 <= b <= 2,
    otherwise it raises (nothing is forced). A carbon deficit (the specified
    gases and carbonate hold more C than the feed) leaves no residue and the
    water closes O.

    Returns (gas kmol/h by species, residual product kmol/h by species, product
    water kmol/h, scale factor 1.0).
    """
    gas = dict(specified_gas_kmolph)
    fixed = dict(fixed_atoms)
    for ID, kmolph in gas.items():
        for element, n in species_atoms[ID].items():
            fixed[element] = fixed.get(element, 0.0) + n * kmolph
    remaining_C = feed_atoms.get("C", 0.0) - fixed.get("C", 0.0)
    if remaining_C > 0.0:
        (ID0, atoms0), (ID2, atoms2) = sorted(lumped_atoms.items(), key=lambda kv: kv[1].get("O", 0.0))
        a = atoms0.get("H", 0.0) / atoms0["C"]
        if abs(atoms2.get("H", 0.0) / atoms2["C"] - a) > 1e-12 or atoms0.get("O", 0.0) != 0.0:
            raise ValueError("lumped_atoms must be two CH_a end members with b = 0 and b > 0 at the same H/C.")
        b_max = atoms2["O"] / atoms2["C"]
        water_kmolph = (feed_atoms.get("H", 0.0) - fixed.get("H", 0.0) - a * remaining_C) / 2.0
        b = (feed_atoms.get("O", 0.0) - fixed.get("O", 0.0) - water_kmolph) / remaining_C
        if water_kmolph < 0.0 or not 0.0 <= b <= b_max:
            raise RuntimeError(
                f"Lumped residual closure infeasible: product water {water_kmolph:.6g} kmol/h, "
                f"O/C of the residue {b:.6g} (allowed 0-{b_max:g}); nothing is forced."
            )
        x2 = b / b_max * remaining_C / atoms2["C"]
        x0 = (remaining_C - x2 * atoms2["C"]) / atoms0["C"]
        return gas, {ID0: x0, ID2: x2}, water_kmolph, 1.0
    water_kmolph = feed_atoms.get("O", 0.0) - fixed.get("O", 0.0)
    if water_kmolph < 0.0:
        raise RuntimeError(
            f"The specified gas slate cannot be produced from this feed: the oxygen balance "
            f"gives product water {water_kmolph:.6g} kmol/h."
        )
    return gas, {}, water_kmolph, 1.0


class ATTReactor(bst.Unit, PressureVessel):
    """
    Alkaline thermal treatment (ATT) reactor for Sargassum.

    The baseline case is Ni-CatATT_1to1 (ATT Scenario 1). The NaOH loading
    is set by the flowsheet (kg NaOH per kg DRY Sargassum, M1); the gas
    yields are per g DAF of this reactor's own feed. NaOH-to-Na2CO3
    conversion follows att.yaml (workbook: complete).

    The gas yields are specified (att.yaml: measured Ni-CatATT 1:1 slate) and
    never changed. C, O and Na are closed: carbon beyond the specified gases
    and the carbonate leaves as the lumped residual product CH_aO_b (an
    assumed surrogate), and the product water closes hydrogen. Hydrogen is
    a check, not an unknown; an excess of H in the identified products
    (unresolved balance) is warned about and reported as FAIL. N and S are
    not followed (they stay in an inert N/S residue). ``balance_checks`` reports (i) whether the
    NaOH can absorb the CO2 generated and (ii) whether the products respect
    the electron, mass and energy balances of the feed.

    The process heat duty is Hnet(outlets) - Hnet(inlet) and therefore
    includes the reaction enthalpy. The organic feed's formation enthalpy is
    re-referenced to the HHV in att.yaml, and the dissolved NaOH in the
    feed is corrected to the NaOH(aq) electrolyte enthalpy
    (``aqueous_feed_enthalpy_correction_kJph``, set by the flowsheet).

    Notes
    -----
    The heat supplied to the reactor is a natural-gas furnace (a heat utility of this unit, costed in ``_cost`` with
    the Seider et al. fired-heater correlation that ``bst.HXutility`` uses) and the hold-up vessel is a vertical
    pressure vessel (``_design``). Material: Inconel-600 (cost factor), assumed for the hot, high-salt caustic feed
    (user decision 2026-11-04); stainless steel may not be sufficient. BioSTEAM has no density for Inconel, so the
    wall weight is computed with stainless steel 316. The vertical vessel is a placeholder reactor type.
    This is a reduced-order, data-reconciled yield model, not a kinetic or
    mechanistic reaction model.
    """

    gas_closure_method = "specified_yields"     # the gas yields are inputs and are never changed
    residual_carbon_fate = "lumped"             # residual carbon leaves as the lumped residual product CH_aO_b

    _N_ins = 2          # [0] feed, [1] PSA tail gas: fuel gas burned in the U2 furnace (empty without a PSA)
    _N_outs = 2

    _F_BM_default = {"Furnace": 2.19, "Vertical pressure vessel": 4.16, "Platform and ladders": 1.0}
    _units = {"Pressure": "psi", "Diameter": "ft", "Length": "ft", "Wall thickness": "in", "Weight": "lb"}

    def _init(
        self,
        target_temperature_K=_ATT["target_temperature_K"],
        heat_loss_fraction=_ATT["heat_loss_fraction"],
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

        self.case_name = _ATT["baseline_case"]
        self.case_data = _ATT["cases"][self.case_name]

        # Dose of the case [kg NaOH/kg dry Sargassum]; applied by the
        # flowsheet (M1), kept here for reporting.
        self.naoh_kg_per_kg_dry = float(
            self.case_data["naoh_kg_per_kg_dry"]
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

        # Basis species of the lumped residual product.
        self.lumped_residue_IDs = tuple(balance["lumped_residue"]["species"])
        self.lumped_residue_H_per_C = float(balance["lumped_residue"]["H_per_C"])
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

        # Reactor vessel (hold-up volume): costed with the pressure-vessel correlation in _design(); its volume
        # follows the feed. BioSTEAM has no density for most alloys: the wall is sized with SS316 and the material
        # factor of the specified alloy is applied.
        cfg = _EQUIPMENT["U2_vessel"]
        self.vessel_length_to_diameter = float(cfg["length_to_diameter"])
        self.vessel_type = "Vertical"
        self.vessel_material = "Stainless steel 316"
        self.F_M["Vertical pressure vessel"] = pressure_vessel_material_factors[cfg["material"]]

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
            feed.imass["Ash"] + feed.imass["NaCl"] + feed.imass["KCl"] + feed.imass["REO"]
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
        for ID in ("Ash", "NaCl", "KCl", "REO"):        # the inorganic part of the seaweed passes through unchanged
            residue.imass[ID] = float(feed.imass[ID])

        sodium_kmolph = float(feed.imol["NaOH"] + 2.0 * feed.imol["Na2CO3"])    # NaCl is not a NaOH source
        na2co3_kmolph = (
            0.5 * sodium_kmolph * self.naoh_to_na2co3_conversion
        )
        residue.imol["Na2CO3"] = na2co3_kmolph
        residue.imol["NaOH"] = sodium_kmolph - 2.0 * na2co3_kmolph

        chemicals = feed.chemicals
        inorganic_IDs = ("Water", "NaOH", "Na2CO3", "Ash", "NaCl", "KCl", "REO")
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
        # 3. Close C with the specified gases, the carbonate and the
        #    lumped residual product CH_aO_b: b closes O while water
        #    closes H. The specified gases are never changed.
        # ----------------------------------------------------------
        fixed_atoms = atoms_of(flows_of(residue))
        species_atoms = {ID: chemicals[ID].atoms for ID in measured_gas_kmolph}
        lumped_atoms = {ID: chemicals[ID].atoms for ID in self.lumped_residue_IDs}
        for ID, a in lumped_atoms.items():
            if abs(a.get("H", 0.0) / a["C"] - self.lumped_residue_H_per_C) > 1e-12:
                raise ValueError(f"{ID} has H/C {a.get('H', 0.0) / a['C']}, not lumped_residue.H_per_C "
                                 f"{self.lumped_residue_H_per_C} (att.yaml).")
        model_gas_kmolph, residue_kmolph, water_kmolph, scale = close_att_u2_balance(
            feed_atoms, fixed_atoms, measured_gas_kmolph, species_atoms, lumped_atoms,
        )
        gas_atoms = atoms_of(model_gas_kmolph)

        for ID, kmolph in model_gas_kmolph.items():
            gas.imol[ID] = kmolph
        gas.imol["Water"] = water_kmolph
        for ID, kmolph in residue_kmolph.items():
            residue.imol[ID] = kmolph
        self._residual_product_IDs = tuple(residue_kmolph)
        residual_C = sum(kmolph * chemicals[ID].atoms["C"] for ID, kmolph in residue_kmolph.items())
        residual_O = sum(kmolph * chemicals[ID].atoms.get("O", 0.0) for ID, kmolph in residue_kmolph.items())
        residual_H = sum(kmolph * chemicals[ID].atoms.get("H", 0.0) for ID, kmolph in residue_kmolph.items())
        self._residual_carbon_kmolph = residual_C
        # Lumped formula CH_aO_b of the residual product (per C), as solved.
        self._residual_product_formula = ({"C": 1.0, "H": residual_H / residual_C, "O": residual_O / residual_C}
                                          if residual_C > 0.0 else {})

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
        organic_atoms_feed["H"] = sum(
            float(feed.imol[ID]) * chemicals[ID].atoms.get("H", 0.0) for ID in organic_IDs
        )
        # The identified products may hold LESS hydrogen/reducing power than the
        # feed (the rest is in unidentified products), never more. An excess
        # is kept as an explicit, unresolved residual (warning + FAIL in
        # balance_checks); no product is added or removed to hide it.
        bad = {}
        self._hydrogen_excess_kmolph = 0.0
        for e, v in self._unresolved_element_kmolph.items():
            if e == "H":
                if v > 0.005 * organic_atoms_feed["H"]:
                    self._hydrogen_excess_kmolph = v
            elif e == "C":
                if abs(v) > 0.02 * organic_atoms_feed["C"]:
                    bad[e] = v
            else:
                bad[e] = v
        if self._hydrogen_excess_kmolph:
            from warnings import warn
            warn(f"U2: UNRESOLVED balance: the identified products (measured gases, residual product, water) hold "
                 f"{self._hydrogen_excess_kmolph * 1e3 / daf_sargassum_kgph:.2f} mmol H/g daf more hydrogen "
                 f"than the feed; reported in balance_checks(), not corrected.", RuntimeWarning, stacklevel=2)
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
             for ID in (*self._residual_product_IDs, *self.heteroatom_IDs.values())}
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
        # Residual product (lumped residue or char) plus the N/S residue.
        self._char_kgph = sum(
            float(residue.imass[ID])
            for ID in (*self._residual_product_IDs, *self.heteroatom_IDs.values())
        )
        self._char_carbon_fraction_of_feed_organic_C = (
            residual_C / organic_atoms["C"]
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
            if chemical.ID not in ("Water", "NaOH", "Na2CO3", "Ash", "NaCl", "KCl", "REO")
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

        # Heat supply: the natural-gas furnace of this unit. The detailed phase-change duty is the full Hnet
        # balance above; the heat-loss allowance enters through the heat-transfer efficiency.
        T_in = float(feed.T)
        self.add_heat_utility(heat_duty_kJph, T_in, max(self.target_temperature_K, T_in),
                              heat_transfer_efficiency=self.heat_transfer_efficiency, hxn_ok=True)

        cfg = _EQUIPMENT["U2_vessel"]
        volume_m3 = float(feed.F_mass) / cfg["density_kg_per_m3"] * cfg["tau_h"] / cfg["fill_fraction"]
        D_m = (4.0 * volume_m3 / (pi * self.vessel_length_to_diameter)) ** (1.0 / 3.0)
        self._design_and_cost_pressure_vessel(
            101325.0, D_m, self.vessel_length_to_diameter * D_m, pressure_units="Pa", length_units="m")

        utility_heat_duty_kJph = sum(
            max(float(hu.duty), 0.0)
            for hu in self.heat_utilities
        )

        # PSA tail gas (ins[1]) is fuel for the furnace: its LHV x the burner efficiency replaces natural gas heat,
        # up to the furnace duty. The natural gas utility above stays the gross furnace duty (heat demand); the
        # purchased natural gas is that duty minus the tail gas heat (``natural_gas_purchased_duty_kJph``).
        tail = self.ins[1]
        eta_burner = float(_ATT_DATA["energy_sources"]["natural_gas"]["burner_efficiency"])
        burn = _ATT_DATA["gas_treatment"]["tail_gas_combustion"] == "offset_u2_natural_gas"
        tail_LHV_kJph = float(tail.LHV) if tail.F_mol else 0.0
        gross_ng_kJph = sum(max(float(hu.duty), 0.0) for hu in self.heat_utilities
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


    def _cost(self):
        # Natural-gas furnace, as bst.HXutility costs a fuel-heated exchanger: Seider et al. fired-heater purchase
        # cost on the heat absorbed (Btu/h), bare-module factor 2.19 (_F_BM_default).
        duty = abs(self.net_duty)
        if duty <= 1e-12:
            return
        if not self.heat_utilities[0].agent.isfuel:
            raise RuntimeError("U2 heat must be supplied by a fuel-fired furnace.")
        self.baseline_purchase_costs["Furnace"] = compute_furnace_purchase_cost(duty * 0.947817, bst.CE)



def _att_u2_balance_checks(self):
    """
    Checks of the specified slate (call after the system is simulated):

    (i) NaOH capacity for CO2: CO2 generated = gas CO2 + CO2 captured as
        Na2CO3; capturing it all needs 2 NaOH per CO2.
    (ii) electrons: available electrons of the feed organics against the
        gases and residue; overall mass; and energy: the chemical energy of
        the product gases (HHV) must not exceed the feed HHV plus the
        process heat.
    (iii) diagnostics: C/H/O residuals, the electrons per residual-carbon
        atom that would close the balance, and the U2 duty, labeled
        PROVISIONAL while the elemental balance is unresolved.
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
    # Residual product: the lumped CH_aO_b surrogate (its basis species) or the char.
    res_IDs = getattr(self, "_residual_product_IDs", ())

    def e_of(a):
        return 4.0 * a.get("C", 0.0) + a.get("H", 0.0) - 2.0 * a.get("O", 0.0)

    e_char = sum(float(residue.imol[ID]) * e_of(chemicals[ID].atoms) for ID in res_IDs)
    res_kg = sum(float(residue.imass[ID]) for ID in res_IDs)
    formula = getattr(self, "_residual_product_formula", {})
    formula_txt = (f"CH{formula['H']:.4g}O{formula['O']:.4g}" if formula else "none")
    h_residual = self._unresolved_element_kmolph.get("H", 0.0)   # outlet - inlet [kmol H/h]
    h2 = chemicals["H2"]
    gas_HHV_kJph = sum(float(gas.imol[ID]) * chemicals[ID].HHV for ID in ("H2", "CH4", "CO"))
    feed_HHV_kJph = self.feed_HHV_MJ_per_kg_daf * 1e3 * daf
    heat_kJph = getattr(self, "_heat_duty_kJph", float("nan"))
    ratio = gas_HHV_kJph / (feed_HHV_kJph + max(heat_kJph, 0.0)) if feed_HHV_kJph > 0 else float("nan")
    # Diagnostics (ATT Scenario 1): elemental residuals with the standards _run applies (C within 2 % of the
    # organic C; O closed by the product water to round-off; H: no excess beyond 0.5 % of the organic H), the
    # available electrons per residual-carbon atom that would close the balance against those the residual
    # product carries, and the chemical energy of all fuel-like products (gases + residual product).
    errors = self._atomic_balance_errors_kmolph
    tolerance = 1e-9 * max(1.0, max(map(abs, self._organic_atoms_kmolph.values())))
    c_res, o_res = errors.get("C", 0.0), errors.get("O", 0.0)
    n_char_C = sum(float(residue.imol[ID]) * chemicals[ID].atoms["C"] for ID in res_IDs)
    e_per_C_needed = (e_feed - e_out) / n_char_C if n_char_C > 0.0 else float("nan")
    e_per_C_char = e_char / n_char_C if n_char_C > 0.0 else float("nan")
    char_HHV_kJph = sum(float(residue.imol[ID]) * chemicals[ID].HHV for ID in res_IDs)
    surrogate = True
    ratio_all = ((gas_HHV_kJph + char_HHV_kJph) / (feed_HHV_kJph + max(heat_kJph, 0.0))
                 if feed_HHV_kJph > 0 else float("nan"))
    unresolved = bool(getattr(self, "_hydrogen_excess_kmolph", 0.0))
    rows = [
        dict(check="NaOH available for CO2 capture [mmol/g daf]", value=naoh_available * 1e3 / daf, unit="mmol/g daf"),
        dict(check="NaOH needed to capture all CO2 generated [mmol/g daf]", value=naoh_required * 1e3 / daf, unit="mmol/g daf"),
        dict(check="CO2 captured as Na2CO3 / CO2 generated", value=carbonate / co2_generated if co2_generated else float("nan"),
             unit="-", status="SUFFICIENT" if naoh_available >= naoh_required - 1e-12 else "INSUFFICIENT (CO2 remains in the gas)"),
        dict(check="Electrons: feed organics, C/H/O [mmol/g daf]", value=e_feed * 1e3 / daf, unit="mmol e-/g daf"),
        dict(check="Electrons: identified gases [mmol/g daf]", value=e_out * 1e3 / daf, unit="mmol e-/g daf",
             status="PASS" if e_out <= 1.01 * e_feed else "FAIL"),
        dict(check="Reducing power left to unidentified products / feed", value=(e_feed - e_out) / e_feed, unit="-"),
        dict(check="Residual carbon fate (closure)", value=float("nan"), unit=self.residual_carbon_fate,
             status="PROVISIONAL" if surrogate else None),
        dict(check="Residual product formula per C (assumed surrogate, not measured)", value=formula.get("O", float("nan")),
             unit=formula_txt, status="ASSUMED" if surrogate else None),
        dict(check="Residual product [g/g daf]", value=res_kg / daf, unit="g/g daf"),
        dict(check="Residual product carbon / feed organic carbon", value=n_char_C / atoms["C"] if atoms.get("C") else float("nan"),
             unit="-"),
        dict(check="Electrons: identified gases + residual product [mmol/g daf]", value=(e_out + e_char) * 1e3 / daf,
             unit="mmol e-/g daf", status="PASS" if e_out + e_char <= 1.01 * e_feed else "FAIL"),
        dict(check="H residual, identified products - feed (+ = excess, unresolved) [mmol H/g daf]",
             value=h_residual * 1e3 / daf, unit="mmol H/g daf",
             status="FAIL (unresolved H excess)" if getattr(self, "_hydrogen_excess_kmolph", 0.0) else "PASS"),
        dict(check="H residual as H2 HHV (energy not backed by the feed) [kJ/g daf]",
             value=0.5 * h_residual * h2.HHV / daf / 1e3, unit="kJ/g daf"),
        dict(check="H residual as H2 LHV (energy not backed by the feed) [kJ/g daf]",
             value=0.5 * h_residual * h2.LHV / daf / 1e3, unit="kJ/g daf"),
        dict(check="Elemental residual C, products - feed [mmol C/g daf]", value=c_res * 1e3 / daf, unit="mmol C/g daf",
             status="PASS" if abs(c_res) <= 0.02 * atoms.get("C", 0.0) else "FAIL"),
        dict(check="Elemental residual O, products - feed [mmol O/g daf]", value=o_res * 1e3 / daf, unit="mmol O/g daf",
             status="PASS" if abs(o_res) <= tolerance else "FAIL"),
        dict(check="Electron residual, gases + residual product - feed organics [mmol e-/g daf]",
             value=(e_out + e_char - e_feed) * 1e3 / daf, unit="mmol e-/g daf",
             status="PASS" if e_out + e_char <= 1.01 * e_feed else "FAIL"),
        dict(check="Available electrons per residual-C atom needed for closure (residual product value in unit)",
             value=e_per_C_needed, unit=f"e-/C (residual product {e_per_C_char:.4g})",
             status="PASS" if n_char_C == 0.0 or e_per_C_needed >= e_per_C_char - 1e-9 else "FAIL (residual C must be more oxidized than the residual product)"),
        dict(check="Mass balance error / inlet", value=self._mass_balance_error_fraction, unit="-",
             status="PASS" if abs(self._mass_balance_error_fraction) <= 5e-3 else "FAIL"),
        dict(check="Product gas HHV / (feed HHV + process heat)", value=ratio, unit="-",
             status="PASS" if ratio == ratio and ratio <= 1.0 else "FAIL"),
        dict(check="Product gas + residual product HHV / (feed HHV + process heat)", value=ratio_all, unit="-",
             status="PASS" if ratio_all == ratio_all and ratio_all <= 1.0 else "FAIL"),
        dict(check="U2 process heat duty [MJ/kg dry]", value=heat_kJph / 1e3 / self._dry_sargassum_kgph, unit="MJ/kg dry",
             status=("PROVISIONAL (elemental balance unresolved)" if unresolved else
                     "PROVISIONAL (assumed residual-product composition and thermo)" if surrogate else "PASS")),
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
        **kwargs,
    ):
        super().__init__(ID, ins, outs, **kwargs)

        self.conversion = float(conversion)
        self.lime_equiv = float(lime_equiv)
        if not 0.0 <= self.conversion <= self.lime_equiv:
            # The conversion applies to the Na2CO3 regardless of the lime, so a
            # lime dose below it would consume more Ca(OH)2 than is fed.
            raise ValueError(f"C1 conversion ({self.conversion}) must be within [0, lime_equiv={self.lime_equiv}].")
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

        # Automatically dose Ca(OH)2.
        _set_lime_stream(lime, required_lime_kmolph)
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
        from biorefineries.ATT.analyses.thermodynamics import from_reactor_streams
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
        # Superseded by the aqueous reference scope above
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
_PASSIVE_SALTS = ("NaCl", "KCl")      # soluble ash salts: carried through EC1 unchanged, removed in the crystallizer XL1


def _liquor_masses(stream, unit_ID):
    other = {
        chemical.ID: float(stream.imass[chemical.ID])
        for chemical in stream.chemicals
        if chemical.ID not in _LIQUOR_IDS and chemical.ID not in _PASSIVE_SALTS and float(stream.imass[chemical.ID]) != 0.0
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
        for ID in _PASSIVE_SALTS:                      # dissolved ash salts (the model carries them in the liquid phase)
            concentrate.imass["l", ID] = float(feed.imass[ID])
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
