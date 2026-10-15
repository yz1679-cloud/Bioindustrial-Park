"""ATT thermochemistry: U2 reaction energy and the C1 aqueous enthalpy reference.

U2 (ATT reactor) gas basis, reaction-energy breakdown and uncertainty are
read-only analyses of a converged ATT system. All evaluations hold the
converged U2 feed fixed (U2-local; the recycle is not re-converged).
Reference states: formation enthalpies at 298.15 K (ThermoSTEAM Hf of
each species' reference phase); organic feed Hf re-referenced to the HHV
in att.yaml; dissolved NaOH at its NaOH(aq) electrolyte enthalpy; product
water as liquid at 298.15 K in the reaction step.

C1 phase-consistent standard-state reference (used by
units/_att.CausticizationReactor): standard aqueous-ion formation enthalpy
values at 298.15 K (CRC, approximate rounded entries). Does NOT model
concentrated-solution excess/mixing enthalpy, temperature-dependent
activities, or validate chemical solubility.

Concentrated-solution limitation (bounded, not modelled; see att.yaml
``c1_energy_basis_status``): relative enthalpies of 25 wt% Na2CO3(aq) and
17.6 wt% NaOH(aq), the solution heat capacity and the reaction heat-capacity
change together shift the baseline C1 process duty (1700 kJ/h) by about
-40 to +300 kJ/h, i.e. -0.2 to +1.2 % of total plant heating. The molten-salt
phase offset BioSTEAM assigns to dissolved salts nets to ~1 kJ/h, so the
infinite-dilution Hf is not double-counted with a fusion enthalpy.

All C1 numbers and units explicitly in kJ/kmol, kmol/h and kJ/h.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from types import SimpleNamespace

import biosteam as bst
import thermosteam as tmo

from biorefineries.sabre._chemicals import char_Hf_from_HHV
from biorefineries.sabre.units._att import (
    _ATT, aqueous_naoh_enthalpy_correction_kJph, close_att_u2_balance,
)
from biorefineries.sabre.utils import load_assumptions

__all__ = (
    "get_att_u2_gas_basis",
    "evaluate_att_u2_variant",
    "get_att_u2_energy_breakdown",
    "get_att_u2_energy_uncertainty",
    "ReferenceCorrection",
    "correct_reaction_enthalpy",
    "from_reactor_streams",
)


# ==========================================================================
# U2 (ATT reactor) gas basis, reaction-energy breakdown and uncertainty
# ==========================================================================

T_REF = 298.15
_MW_H2 = 2.01588
_INORGANIC = ("Water", "NaOH", "Na2CO3", "Ash")
_GASES = ("H2", "CH4", "CO", "CO2")


def _units(sys):
    return SimpleNamespace(**{unit.ID: unit for unit in sys.units})


def get_att_u2_gas_basis(sys) -> dict:
    """Measured (experimental) vs model (closed) gas yields and H2."""
    U2 = _units(sys).U2
    psa = float(load_assumptions("att.yaml")["att"]["gas_treatment"]["psa_h2_recovery"])
    daf = float(U2._daf_sargassum_kgph)
    measured = {k: float(v) for k, v in U2.reported_gas_yield_mmol_per_g_daf.items()}
    model = dict(U2._model_gas_yield_mmol_per_g_daf)
    h2_measured_kgph = measured["H2"] * daf / 1000.0 * _MW_H2
    h2_model_kgph = float(U2.outs[0].imass["H2"])
    if U2.gas_closure_method == "h2_priority":
        status = (f"H2_PRIORITY: H2 = measured; {U2.closure_gas_ID} is an unmeasured closure "
                  "product; reported CH4/CO/CO2 not imposed")
    else:
        status = "RECONCILED_MODELING_BASIS: gas yields scaled by s; NOT experimental data"
    return dict(
        status=status,
        gas_closure_method=U2.gas_closure_method,
        scale_factor_s=float(U2._gas_scale_factor),
        daf_kgph=daf,
        measured_yield_mmol_per_g_daf=measured,
        model_yield_mmol_per_g_daf=model,
        H2_in_U2_gas_kgph={"measured": h2_measured_kgph,
                           "model": h2_model_kgph},
        H2_product_kgph={"measured": h2_measured_kgph * psa,
                         "model": h2_model_kgph * psa},
        psa_h2_recovery=psa,
    )


def _atoms(chemicals, flows):
    totals = {}
    for ID, kmol in flows.items():
        for e, n in chemicals[ID].atoms.items():
            totals[e] = totals.get(e, 0.0) + n * kmol
    return totals


def _feed_flows(feed):
    return {c.ID: float(feed.imol[c.ID]) for c in feed.chemicals if float(feed.imol[c.ID]) != 0.0}


def _ammonia():
    # Free-standing (unlocked) NH3 for gas-phase enthalpy; the flowsheet
    # Ammonia is locked to the liquid phase as an aqueous nutrient.
    return bst.Chemical("NH3_gas", search_ID="Ammonia")


def evaluate_att_u2_variant(sys, *, char_atoms=None, char_HHV_rel_error=0.0,
                            nh3_fraction_of_feed_N=0.0, feed_HHV_MJ_per_kg_daf=None,
                            naoh_correction_scale=1.0) -> dict:
    """
    Re-solve the U2 element balance and energy for one parameter set,
    holding the converged U2 feed fixed.

    char_atoms: char C/H/O formula per C (default: the 'Char' chemical).
    char_HHV_rel_error: relative error applied to the char HHV correlation.
    nh3_fraction_of_feed_N: UNVERIFIED sensitivity, feed N released as NH3(g)
        instead of retained in the char.
    feed_HHV_MJ_per_kg_daf: HHV used for the organic-feed Hf (default att.yaml).
    naoh_correction_scale: multiplier on the NaOH(aq) enthalpy correction.
    """
    U2 = _units(sys).U2
    feed = U2.ins[0]
    gas0, residue0 = U2.outs
    chemicals = feed.chemicals
    T = float(U2.target_temperature_K)
    default_char = char_atoms is None
    char_atoms = dict(chemicals[U2.char_ID].atoms) if default_char else dict(char_atoms)

    flows = _feed_flows(feed)
    feed_atoms = _atoms(chemicals, flows)
    N_feed = feed_atoms.get("N", 0.0)
    n_nh3 = nh3_fraction_of_feed_N * N_feed
    fixed = {ID: float(residue0.imol[ID]) for ID in ("Ash", "Na2CO3", "NaOH")
             if float(residue0.imol[ID]) != 0.0}
    fixed_atoms = _atoms(chemicals, fixed)
    fixed_atoms["N"] = fixed_atoms.get("N", 0.0) + N_feed     # retained or NH3
    fixed_atoms["S"] = fixed_atoms.get("S", 0.0) + feed_atoms.get("S", 0.0)
    fixed_atoms["H"] = fixed_atoms.get("H", 0.0) + 3.0 * n_nh3
    measured = {k: float(v) for k, v in U2._measured_gas_kmolph.items()}
    species_atoms = {ID: chemicals[ID].atoms for ID in (*measured, U2.closure_gas_ID)}
    gas_kmolph, n_char, w, s = close_att_u2_balance(
        U2.gas_closure_method, feed_atoms, fixed_atoms, measured, species_atoms,
        char_atoms, U2.closure_gas_ID)

    MW_char = sum(_atomic_mass(e) * n for e, n in char_atoms.items())
    HHV_char = (char_Hf_from_HHV(char_atoms) - _combustion_products_Hf(char_atoms)) / MW_char / 1e3
    Hf_char = (_combustion_products_Hf(char_atoms)
               + HHV_char * (1.0 + char_HHV_rel_error) * MW_char * 1e3)   # J/mol
    Cp_char = 1.0 * MW_char                                               # J/mol/K
    NH3 = _ammonia() if n_nh3 > 0.0 else None

    def products_Hnet(T_products, water_liquid):
        gas = tmo.Stream(None, thermo=feed.thermo)
        for k in _GASES:
            gas.imol[k] = gas_kmolph[k]
        if water_liquid:
            gas.phases = ("g", "l")
            for k in _GASES:
                gas.imol["g", k] = gas_kmolph[k]
            gas.imol["l", "Water"] = w
        else:
            gas.phase = "g"
            gas.imol["Water"] = w
        gas.T = T_products
        solids = tmo.Stream(None, thermo=feed.thermo, phase="s")
        for ID, kmol in fixed.items():
            solids.imol[ID] = kmol
        solids.imol["CharN"] = N_feed - n_nh3
        solids.imol["CharS"] = feed_atoms.get("S", 0.0)
        solids.T = T_products
        H = float(gas.Hnet + solids.Hnet)
        H += n_char * (Hf_char + Cp_char * (T_products - T_REF))           # kJ/h
        if NH3 is not None:
            H += n_nh3 * (NH3.Hf + NH3.H("g", T_products))
        return H

    base_HHV = float(U2.feed_HHV_MJ_per_kg_daf)
    HHV = base_HHV if feed_HHV_MJ_per_kg_daf is None else float(feed_HHV_MJ_per_kg_daf)
    organic_kgph = sum(float(feed.imass[ID]) for ID in flows if ID not in _INORGANIC)
    hhv_correction = U2._feed_Hf_HHV_correction_kJph + (HHV - base_HHV) * 1e3 * organic_kgph
    aq_correction = U2._aqueous_feed_correction_kJph * naoh_correction_scale
    inlet = float(feed.Hnet) + hhv_correction + aq_correction
    outlet = products_Hnet(T, water_liquid=False)
    duty = outlet - inlet
    efficiency = 1.0 / (1.0 + U2.heat_loss_fraction)
    return dict(
        scale_factor_s=s, char_kmolph=n_char, product_water_kmolph=w, nh3_kmolph=n_nh3,
        H2_kgph=gas_kmolph["H2"] * _MW_H2, gas_kmolph=gas_kmolph,
        inlet_Hnet_kJph=inlet, outlet_Hnet_kJph=outlet,
        process_duty_kJph=duty, external_heating_kJph=duty / efficiency,
        feed_HHV_MJ_per_kg_daf=HHV, char_Hf_J_per_mol=Hf_char,
        _products_Hnet=products_Hnet, _hhv_correction=hhv_correction,
        _aq_correction=aq_correction,
    )


_AW = {"C": 12.011, "H": 1.008, "O": 15.999, "N": 14.007, "S": 32.06}


def _atomic_mass(e):
    return _AW[e]


def _combustion_products_Hf(atoms):
    return (-393474.0 * atoms.get("C", 0.0) - 285825.0 * atoms.get("H", 0.0) / 2.0
            - 296810.0 * atoms.get("S", 0.0))


def get_att_u2_energy_breakdown(sys) -> dict:
    """
    Hess-path breakdown of the U2 process duty (baseline parameters):

      Q = [R(298 K) - R(T_in)]            feed brought to 25 C as NaOH(aq) slurry
        + [P(298 K, H2O(l)) - R(298 K)]   reaction enthalpy at 25 C
        + [P(T) - P(298 K, H2O(l))]       products heated to 500 C incl. water evaporation

    R = feed enthalpy (Hnet + HHV-based organic Hf + NaOH(aq) correction),
    P = product Hnet. The three terms sum exactly to Q.
    """
    U2 = _units(sys).U2
    feed = U2.ins[0]
    base = evaluate_att_u2_variant(sys)
    products = base["_products_Hnet"]
    T = float(U2.target_temperature_K)

    # 25 C reactant state: water and NaOH as NaOH(aq) (electrolyte
    # correction), recycled Na2CO3 as crystals (the M1 outlet lumps it into
    # the liquid phase, which ThermoSTEAM would evaluate as molten Na2CO3).
    chemicals = feed.chemicals
    feed_ref = tmo.Stream(None, thermo=feed.thermo)
    feed_ref.phases = ("l", "s")
    for c in chemicals:
        kmol = float(feed.imol[c.ID])
        if kmol == 0.0:
            continue
        solid = c.ID == "Na2CO3" or c.locked_state == "s"
        feed_ref.imol["s" if solid else "l", c.ID] = kmol
    feed_ref.T = T_REF
    aq_ref = aqueous_naoh_enthalpy_correction_kJph(feed_ref)
    R_in = base["inlet_Hnet_kJph"]
    R_ref = float(feed_ref.Hnet) + base["_hhv_correction"] + aq_ref
    P_ref = products(T_REF, water_liquid=True)
    P_T = products(T, water_liquid=False)
    reaction = P_ref - R_ref

    # Carbonation of the feed NaOH(aq), 2 NaOH(aq) + CO2(g) -> Na2CO3(s) +
    # H2O(l), per kmol of carbonate formed in U2, at 25 C.
    NaOH, Na2CO3, CO2, Water = (chemicals[i] for i in ("NaOH", "Na2CO3", "CO2", "Water"))
    n_naoh = float(feed.imol["NaOH"])
    h_naoh_aq = NaOH.Hf + NaOH.H("l", T_REF) + aq_ref / n_naoh          # kJ/kmol
    n_carbonate = float(U2.outs[1].imol["Na2CO3"]) - float(feed.imol["Na2CO3"])
    carbonation = n_carbonate * (Na2CO3.Hf + Water.Hf - CO2.Hf - 2.0 * h_naoh_aq)

    w = base["product_water_kmolph"]
    water_heating = w * (Water.H("g", T) - Water.H("l", T_REF))
    terms = {
        "feed_to_25C_kJph": R_ref - R_in,
        "reaction_enthalpy_25C_H2O_liquid_kJph": reaction,
        "  of_which_NaOH_carbonation_kJph": carbonation,
        "  of_which_organic_conversion_to_gases_CO2_char_kJph": reaction - carbonation,
        "products_25C_to_T_kJph": P_T - P_ref,
        "  of_which_product_water_evaporation_and_superheat_kJph": water_heating,
        "  of_which_gases_and_solids_sensible_kJph": (P_T - P_ref) - water_heating,
    }
    total = terms["feed_to_25C_kJph"] + terms["reaction_enthalpy_25C_H2O_liquid_kJph"] + terms["products_25C_to_T_kJph"]
    if abs(total - U2._heat_duty_kJph) > 1e-6 * max(1.0, abs(total)):
        raise RuntimeError(f"U2 breakdown {total} does not reproduce U2 duty {U2._heat_duty_kJph}.")
    dry = float(U2._dry_sargassum_kgph)
    return dict(
        terms_kJph=terms,
        process_duty_kJph=total,
        heat_loss_kJph=total * U2.heat_loss_fraction,
        external_heating_kJph=float(U2._utility_heat_duty_kJph),
        external_heating_MJ_per_kg_dry=float(U2._utility_heat_duty_kJph) / 1e3 / dry,
        reference_corrections_kJph={
            "organic_feed_Hf_to_HHV": base["_hhv_correction"],
            "NaOH_aq_vs_molten_at_feed_state": U2._aqueous_feed_correction_kJph,
            "NaOH_aq_vs_molten_at_25C": aq_ref,
        },
        product_water_kmolph=w,
        feed_water_kmolph=float(feed.imol["Water"]),
    )


def get_att_u2_energy_uncertainty(sys) -> dict:
    """
    Conditional engineering sensitivity of the U2 duty under the active
    gas closure (U2.gas_closure_method); NOT a statistical confidence interval. One-at-a-time
    sensitivities with the U2 feed held fixed. Ranges:

    - feed HHV: literature 15.7-19.5 MJ/kg daf (att.yaml) and a narrower
      composition-consistent 16.3-18.1 (Thornton's rule and the
      Channiwala-Parikh correlation applied to the model daf composition);
    - char formula: CH0.3O0.05 to CH0.8O0.2 per C (generic 500 C chars);
    - char HHV correlation: +/-5 % (assumed; conservative vs. the reported
      1.45 % mean absolute error, as ATT char is outside its data set);
    - NaOH(aq) enthalpy correction: +/-5 % (Olsson vs. OxyChem agreement);
    - dissolved recycle Na2CO3 counted as molten by ThermoSTEAM: bounded
      by its fusion plus solution enthalpies.

    NH3 release is an UNVERIFIED SENSITIVITY SCENARIO, reported separately
    and excluded from the interval.
    """
    U2 = _units(sys).U2
    base = evaluate_att_u2_variant(sys)
    Q0 = base["process_duty_kJph"]
    if abs(Q0 - U2._heat_duty_kJph) > 1e-6 * max(1.0, abs(Q0)):
        raise RuntimeError("U2 variant evaluator does not reproduce the U2 duty.")

    def run(label, **kw):
        r = evaluate_att_u2_variant(sys, **kw)
        return dict(case=label, scale_factor_s=r["scale_factor_s"], H2_kgph=r["H2_kgph"],
                    process_duty_kJph=r["process_duty_kJph"],
                    external_heating_kJph=r["external_heating_kJph"],
                    delta_process_duty_kJph=r["process_duty_kJph"] - Q0)

    groups = {
        "feed_HHV_literature": [run(f"HHV {h} MJ/kg daf", feed_HHV_MJ_per_kg_daf=h) for h in (15.7, 19.5)],
        "feed_HHV_composition_consistent": [run(f"HHV {h} MJ/kg daf", feed_HHV_MJ_per_kg_daf=h) for h in (16.3, 18.1)],
        "char_formula": [run(name, char_atoms=atoms) for name, atoms in
                         (("char CH0.3O0.05", {"C": 1, "H": 0.3, "O": 0.05}),
                          ("char CH0.8O0.2", {"C": 1, "H": 0.8, "O": 0.2}))],
        "char_HHV_correlation": [run(f"char HHV {e:+.0%}", char_HHV_rel_error=e) for e in (-0.05, 0.05)],
        "NaOH_aq_correction": [run(f"NaOH(aq) correction x{k}", naoh_correction_scale=k) for k in (0.95, 1.05)],
    }
    # Dissolved Na2CO3 in the recycle liquor is held as molten Na2CO3 by
    # ThermoSTEAM; true state is aqueous: bound by fusion + |solution| enthalpy.
    recycle = U2.ins[0]
    na2co3 = recycle.chemicals["Na2CO3"]
    u = _units(sys)
    dissolved = float(u.EC1.outs[0].imol["l", "Na2CO3"]) if "l" in u.EC1.outs[0].phases else 0.0
    na2co3_bound = dissolved * (na2co3.Hfus + 26.7e3)
    groups["dissolved_Na2CO3_state"] = [
        dict(case="dissolved Na2CO3 aqueous vs molten (bound)", scale_factor_s=base["scale_factor_s"],
             H2_kgph=base["H2_kgph"], process_duty_kJph=Q0 + na2co3_bound,
             external_heating_kJph=(Q0 + na2co3_bound) * (1 + U2.heat_loss_fraction),
             delta_process_duty_kJph=na2co3_bound)]

    def interval(keys):
        lo = sum(min(0.0, *(r["delta_process_duty_kJph"] for r in groups[k])) for k in keys)
        hi = sum(max(0.0, *(r["delta_process_duty_kJph"] for r in groups[k])) for k in keys)
        return Q0 + lo, Q0 + hi

    common = ["char_formula", "char_HHV_correlation", "NaOH_aq_correction", "dissolved_Na2CO3_state"]
    lo_lit, hi_lit = interval(["feed_HHV_literature"] + common)
    lo_cc, hi_cc = interval(["feed_HHV_composition_consistent"] + common)
    loss = 1.0 + U2.heat_loss_fraction
    nh3 = [run(f"NH3 release {f:.0%} of feed N (UNVERIFIED)", nh3_fraction_of_feed_N=f) for f in (0.5, 1.0)]
    return dict(
        baseline=dict(process_duty_kJph=Q0, external_heating_kJph=Q0 * loss,
                      scale_factor_s=base["scale_factor_s"], H2_kgph=base["H2_kgph"]),
        sensitivities=groups,
        range_status=(
            "CONDITIONAL ENGINEERING SENSITIVITY RANGE under the "
            + (f"reconciled gas-yield scenario (s = {base['scale_factor_s']:.4f})"
               if U2.gas_closure_method == "uniform_redox_scaling"
               else f"H2-priority closure (measured H2, closure {U2.closure_gas_ID})")
            + "; not a statistical confidence interval and not an experimentally "
            "validated uncertainty."),
        # Primary basis (user decision 2026-10-09): feed HHV 16.3-18.1 MJ/kg daf.
        primary_sensitivity_range_kJph=dict(
            feed_HHV_MJ_per_kg_daf=(16.3, 18.1),
            process_duty=(lo_cc, hi_cc), external_heating=(lo_cc * loss, hi_cc * loss)),
        secondary_sensitivity_range_literature_HHV_kJph=dict(
            feed_HHV_MJ_per_kg_daf=(15.7, 19.5),
            process_duty=(lo_lit, hi_lit), external_heating=(lo_lit * loss, hi_lit * loss)),
        range_method="sum of one-at-a-time extremes (conservative)",
        excluded_from_range=(
            "U2 inlet held fixed (recycle and upstream units not re-converged)",
            "uncertainty of the gas closure itself (measured H2 / closure gas or s)",
            "NaOH-to-Na2CO3 conversion (fixed at 100 %)",
            "heat-loss fraction (fixed at 5 %)",
            "NH3 release (separate unverified scenario)",
        ),
        nh3_unverified_scenario=nh3,
    )


# ==========================================================================
# C1 causticization: standard aqueous-ion enthalpy reference
# ==========================================================================

# Rounded conventional standard formation enthalpies (kJ/kmol, 298.15 K):
# Na+(aq) -240.1 kJ/mol, OH-(aq) -230.0 kJ/mol, CO3--(aq) -677.1 kJ/mol.
# CRC Handbook of Chemistry and Physics, aqueous ions table (2015).
ION_HF_KJ_PER_KMOL = {'Na+': -240100.0, 'OH-': -230000.0, 'CO3--': -677100.0}
AQUEOUS_SALT_HF_KJ_PER_KMOL = {
    'NaOH': ION_HF_KJ_PER_KMOL['Na+'] + ION_HF_KJ_PER_KMOL['OH-'],
    'Na2CO3': 2 * ION_HF_KJ_PER_KMOL['Na+'] + ION_HF_KJ_PER_KMOL['CO3--'],
}
REFERENCE_SCOPE = '298.15_K_INFINITE_DILUTION_AQUEOUS_IONS__CONCENTRATED_SOLUTION_ENTHALPY_BOUNDED_NOT_MODELLED'

@dataclass(frozen=True)
class ReferenceCorrection:
    inlet_correction_kJph: float
    outlet_correction_kJph: float
    delta_correction_kJph: float
    uncorrected_Hnet_delta_kJph: float
    phase_reference_corrected_delta_kJph: float
    reaction_formation_delta_kJph: float
    provenance: str = REFERENCE_SCOPE


def correct_reaction_enthalpy(*, inlet_Hnet_kJph: float, outlet_Hnet_kJph: float,
                              inlet_kmolph: dict, outlet_kmolph: dict,
                              chemical_Hf_kJ_per_kmol: dict) -> ReferenceCorrection:
    """Replace native NaOH and Na2CO3 Hf by standard aqueous reference Hf.

    The two salt components must represent dissolved liquor; Ca(OH)2 and
    CaCO3 remain solid. Physical concentrations/heat-of-mixing are NOT solved.
    """
    for v in (inlet_Hnet_kJph, outlet_Hnet_kJph):
        if not isfinite(float(v)):
            raise ValueError('Non-finite Hnet')
    def correction(mols):
        result=0.
        for chem, target_hf in AQUEOUS_SALT_HF_KJ_PER_KMOL.items():
            n=float(mols.get(chem,0.))
            source_hf=float(chemical_Hf_kJ_per_kmol[chem])
            if n < -1e-12 or not all(map(isfinite,(n,source_hf))):
                raise ValueError(f'Invalid {chem} amount/reference')
            result+=n*(target_hf-source_hf)
        return result
    ins=correction(inlet_kmolph)
    outs=correction(outlet_kmolph)
    uncorrected=float(outlet_Hnet_kJph)-float(inlet_Hnet_kJph)
    delta=outs-ins
    n2delta=(float(outlet_kmolph.get('NaOH',0))-float(inlet_kmolph.get('NaOH',0)))
    cdelta=(float(outlet_kmolph.get('Na2CO3',0))-float(inlet_kmolph.get('Na2CO3',0)))
    # Only change in aqueous-standard formation term, not sensible or solid lime/calcite reference.
    return ReferenceCorrection(ins,outs,delta,uncorrected,uncorrected+delta,
                               n2delta*AQUEOUS_SALT_HF_KJ_PER_KMOL['NaOH']+cdelta*AQUEOUS_SALT_HF_KJ_PER_KMOL['Na2CO3'])


def from_reactor_streams(carbonate_solution, lime, slurry):
    """Read actual native BioSTEAM streams, no change to material compositions."""
    if float(carbonate_solution.imass['Water']) <= 0 or float(slurry.imass['Water']) <= 0:
        raise ValueError('C1 aqueous reference requires liquid water at inlet and outlet')
    species=('NaOH','Na2CO3')
    inlet={k:float(carbonate_solution.imol[k])+float(lime.imol[k]) for k in species}
    outlet={k:float(slurry.imol[k]) for k in species}
    hf={k:float(slurry.chemicals[k].Hf) for k in species}
    return correct_reaction_enthalpy(inlet_Hnet_kJph=float(carbonate_solution.Hnet + lime.Hnet),
                                    outlet_Hnet_kJph=float(slurry.Hnet),
                                    inlet_kmolph=inlet,outlet_kmolph=outlet,chemical_Hf_kJ_per_kmol=hf)
