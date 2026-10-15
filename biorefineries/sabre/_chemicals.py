# Bioindustrial-Park: BioSTEAM's Premier Biorefinery Models and Results
# Copyright (C) 2026-, Azhar Razin,
#                      Yalin Li <mailto.yalin.li@gmail.com>
#
# This module is under the UIUC open-source license. See
# github.com/BioSTEAMDevelopmentGroup/biosteam/blob/master/LICENSE.txt
# for license details.
"""""
Creating the chemical list used for the SaBRe systems
"""""
import biosteam as bst
import thermosteam as tmo

__all__ = ('create_chemicals',)


# Structural-carbohydrate constants reused from biorefineries.cellulosic.chemicals,
# which sources Hf from the Humbird et al. 2011 NREL report
# (https://www.nrel.gov/docs/fy11osti/47764.pdf) and Cp from
# https://doi.org/10.1007/s10853-013-7815-6 (lignin/cellulose/hemicellulose
# heat capacities are approximately equal near 350 K).
_cal2joule = 4.184
_Cp_structural = 1.364  # J/g/K
_rho_solids = 1540  # kg/m3, same value used in cellulosic/cane/microalgae


def _structural_solid(ID: str, formula: str, Hf_cal: float,
                       Cp: float = _Cp_structural, rho: float = _rho_solids):
    chemical = bst.Chemical(ID, search_db=False, default=True, phase="s",
                             formula=formula, Hf=Hf_cal * _cal2joule)
    chemical.Cn.add_model(Cp * chemical.MW, top_priority=True)
    chemical.V.add_model(tmo.functional.rho_to_V(rho, chemical.MW), top_priority=True)
    return chemical


_ATOMIC_MASS = {"C": 12.011, "H": 1.008, "O": 15.999, "N": 14.007, "S": 32.06}


def char_Hf_from_HHV(atoms: dict) -> float:
    """Hf [J/mol] of a C/H/O char via Hess's law and the Channiwala & Parikh
    (2002, Fuel 81, 1051-1063) HHV correlation; combustion products are
    CO2(g), H2O(l) and SO2(g) with ThermoSTEAM's Hf values."""
    MW = sum(_ATOMIC_MASS[e] * n for e, n in atoms.items())
    wt = {e: 100.0 * _ATOMIC_MASS[e] * atoms.get(e, 0.0) / MW for e in _ATOMIC_MASS}
    HHV_MJ_per_kg = (0.3491 * wt["C"] + 1.1783 * wt["H"] + 0.1005 * wt["S"]
                     - 0.1034 * wt["O"] - 0.0151 * wt["N"])
    Hf_products = (-393474.0 * atoms.get("C", 0.0)
                   - 285825.0 * atoms.get("H", 0.0) / 2.0
                   - 296810.0 * atoms.get("S", 0.0))
    return Hf_products + HHV_MJ_per_kg * MW * 1e3


def create_chemicals(set_thermo: bool = True, include_hp3: bool = False,
                     include_dilute_acid: bool = False, include_att: bool = False):
    """
    Parameters
    ----------
    include_att : bool
        If True, also include the chemicals used only by the alkaline
        thermal treatment (ATT) pathway (Char, CharN, CharS, CO, C2H4, C2H6,
        H2, Na2CO3, CaOH2, CaCO3). Kept behind its own flag so the chemical
        sets (and hence the results) of the other SaBRe pathways are unchanged.
    include_hp3 : bool
        If True, also construct and include the chemicals used only by
        the EnzymaticPress/3-HP-from-Sargassum pathway (Glucose,
        AlginateMonomer, Enzyme, ...).
    include_dilute_acid : bool
        If True (requires `include_hp3`), also include the chemicals used
        only by the 3-HP cake-saccharification configurations' dilute-acid
        pretreatment (H2SO4, AmmoniumSulfate), and lock Glucose to the
        liquid phase (needed by the pretreatment flash). Kept behind its own flag,
        separate from `include_hp3`, so the `enzymatic_press` 3-HP
        configuration's chemical set (and hence its simulated results)
        stays exactly as it was.
    """
    if include_dilute_acid and not include_hp3:
        raise ValueError("include_dilute_acid=True requires include_hp3=True.")

    Water = bst.Chemical("Water")

    # Sargassum components
    # Ash modeled as CaO (following biorefineries.lactic's precedent for
    # generic biomass ash). CaO's database liquid-viscosity correlation
    # ('NEGLECT_P') is invalid at process T/P, the same issue this file
    # already works around for KH2PO4/MagnesiumSulfate below,
    # approximated with Water's viscosity for the same reason.
    CaO = bst.Chemical("CaO", phase="s")
    CaO.Hf = 0.0
    CaO.copy_models_from(Water, ["mu"])
    Ash = bst.Chemical("Ash", search_db=False, default=True, phase="s",
                        MW=CaO.MW, HHV=0, LHV=0, Hf=0.0)
    Ash.copy_models_from(CaO, ["Cn", "V", "mu"])

    # Hf/Cp from biorefineries.cellulosic.chemicals (Humbird et al. 2011 NREL report)
    Glucan = _structural_solid("Glucan", "C6H10O5", -233200)
    Xylan = _structural_solid("Xylan", "C5H8O4", -182100)
    Mannan = Glucan.copy("Mannan")
    Galactan = Glucan.copy("Galactan")
    Arabinan = Xylan.copy("Arabinan")
    Lignin = _structural_solid("Lignin", "C8H8O3", -108248)  # vanillin used as a structural proxy, per biorefineries.cane
    # Same elemental formula/Hf as biorefineries.cellulosic.chemicals; Cp from
    # Leow et al., Green Chem. 2015, 17, 3584-3599 (as in biorefineries.microalgae)
    Protein = _structural_solid("Protein", "CH1.57O0.31N0.29S0.007", -17618, Cp=1.25)

    # Alginic acid uronic-acid repeat unit, dehydrated (C6H10O7 - H2O); MW is
    # computed from the formula. No database entry or literature Hf found for
    # alginic acid or its mannuronic/guluronic acid monomers,
    # so Hf borrows Glucan's structural-carbohydrate value;
    # Cn/V likewise reuse Glucan's Cp/density basis.
    Alginate = _structural_solid("Alginate", "C6H8O6", -233200)
    # Fucose repeat unit, dehydrated (C6H12O5 - H2O); ignores fucoidan's sulfate
    # substitution. No literature Hf found for fucoidan or its L-fucose
    # monomer either, so Hf and Cn/V all borrow Glucan's basis for the same
    # reason as Alginate.
    Fucoidan = _structural_solid("Fucoidan", "C6H10O4", -233200)
    Mannitol = bst.Chemical("Mannitol")
    # No known formula/composition for this lumped catch-all; treated as
    # generically Glucan-like (same MW/Cn/V/Hf).
    OtherSolids = Glucan.copy("OtherSolids")

    # EnzymaticPress/3-HP-only chemicals.
    hp3_chemicals = []
    if include_hp3:
        Glucose = bst.Chemical("Glucose")

        # Free monomer form of Alginate (mannuronic/guluronic acid, hydrated:
        # Alginate's C6H8O6 repeat unit + H2O -> C6H10O7), formed by
        # enzymatic hydrolysis in EnzymaticPress. Liquid density is a rough
        # concentrated-sugar-acid-solution proxy (1200 kg/m3, vs. Glucan's
        # solid-phase 1540 kg/m3), and viscosity borrows Water's model for
        # the same NEGLECT_P-workaround reason as the nutrient salts below.
        AlginateMonomer = bst.Chemical("AlginateMonomer", search_db=False, default=True,
                                        phase="l", formula="C6H10O7", Hf=-233200 * _cal2joule)
        AlginateMonomer.Cn.add_model(_Cp_structural * AlginateMonomer.MW, top_priority=True)
        AlginateMonomer.V.add_model(tmo.functional.rho_to_V(1200, AlginateMonomer.MW), top_priority=True)
        AlginateMonomer.copy_models_from(Water, ["mu"])

        # Generic-protein proxy for the hydrolysis enzyme cocktail (cellulase +
        # alginate lyase, dosed in EnzymaticPress) -- same formula/Hf
        # convention biorefineries.cellulosic uses for its own 'Enzyme'
        # chemical (CH1.59O0.42N0.24S0.01, Hf shared with Protein-like
        # chemicals). Modeled as phase="l" (dosed as a dilute
        # aqueous enzyme prep), with Water-like density/
        # viscosity as a dilute-solute proxy (same technique used for
        # KH2PO4/MagnesiumSulfate below).
        Enzyme = bst.Chemical("Enzyme", search_db=False, default=True, phase="l",
                               formula="CH1.59O0.42N0.24S0.01", Hf=-17618 * _cal2joule)
        Enzyme.Cn.add_model(1.25 * Enzyme.MW, top_priority=True)
        Enzyme.V.add_model(tmo.functional.rho_to_V(1000, Enzyme.MW), top_priority=True)
        Enzyme.copy_models_from(Water, ["mu"])

        # Real database chemical: 3-hydroxypropionic acid, the fermentation
        # product (HPFermentation, sabre/units/_3hp.py).
        HP = bst.Chemical("HP", search_ID="3-Hydroxypropionic acid")

        # Fermentation neutralization base, forming
        # Ca3HP2 in situ (HPFermentation). Dosed into a liquid-phase
        # broth, but its database liquid-volume/viscosity correlations
        # ('NEGLECT_P') are invalid at process T/P, fixed with a dilute-solute density/viscosity proxy.
        CalciumDihydroxide = bst.Chemical("CalciumDihydroxide", search_ID="Calcium hydroxide")
        CalciumDihydroxide.V.l.add_model(
            tmo.functional.rho_to_V(1e5, CalciumDihydroxide.MW), top_priority=True
        )
        CalciumDihydroxide.copy_models_from(Water, ["mu"])

        # Calcium 3-hydroxypropionate, the crystallized final product. 3-HP and lactic acid are
        # structural isomers (both C3H6O3), properties borrowed
        # from database's real "Calcium lactate" entry as the best
        # available proxy.
        # The database entry has no Hf, so one is estimated assuming the
        # neutralization reaction (2 HP + Ca(OH)2 -> Ca3HP2 + 2 H2O) is
        # thermoneutral (no literature heat of reaction found):
        # Hf(Ca3HP2) = 2*Hf(HP) + Hf(Ca(OH)2) - 2*Hf(Water). The database
        # entry also has no solid-phase molar volume model, so density
        # borrows the same generic structural-solid proxy (_rho_solids)
        # used for Glucan/Alginate/etc. above. Its database liquid-
        # viscosity correlation ('NEGLECT_P') is invalid outside
        # atmospheric pressure, fixed assuming water.
        Ca3HP2 = bst.Chemical("Ca3HP2", search_ID="Calcium lactate", phase="s")
        Ca3HP2.Hf = 2 * HP.Hf + CalciumDihydroxide.Hf - 2 * Water.Hf
        Ca3HP2.V.add_model(tmo.functional.rho_to_V(_rho_solids, Ca3HP2.MW), top_priority=True)
        Ca3HP2.copy_models_from(Water, ["mu"])

        # Combustion product of the sulfur atoms.
        SO2 = bst.Chemical("SO2", phase="g")

        # Combustion product of phosphorus atoms. The database's real
        # entry is missing Psat/Tb/Hvap, since
        # the exact values are irrelevant for a chemical that never flows,
        # Water's own models are borrowed as a placeholder rather than
        # sourcing real P4O10 property data.
        P4O10 = bst.Chemical("P4O10", phase="s")
        P4O10.copy_models_from(Water, ["Psat", "Hvap", "V", "mu"])
        P4O10.Tb = Water.Tb

        # BT's flue-gas desulfurization reaction
        # (SO2 + Ca(OH)2 + 0.5 O2 -> CaSO4 + H2O) needs gypsum (CaSO4) as
        # a product chemical too; same missing-property gaps as P4O10,
        # fixed the same way (never flows in bulk, so the borrowed values
        # are inconsequential).
        CaSO4 = bst.Chemical("CaSO4", phase="s")
        CaSO4.copy_models_from(Water, ["Psat", "Hvap", "mu"])
        CaSO4.Tb = Water.Tb

        hp3_chemicals = [
            Glucose, AlginateMonomer, Enzyme, HP, CalciumDihydroxide, Ca3HP2,
            SO2, P4O10, CaSO4,
        ]

    # Dilute-acid pretreatment chemicals (3-HP cake configurations only).
    # Same choices biorefineries.cellulosic makes for its own corn stover
    # dilute-acid pretreatment: H2SO4 as a liquid, and ammonium sulfate as a
    # single-phase chemical locked to its database phase (solid) that
    # nonetheless behaves as a dissolved salt downstream.
    acid_chemicals = []
    if include_dilute_acid:
        # Glucose is formed upstream of the pretreatment flash here (it never
        # enters a flash in the enzymatic_press configuration), and its
        # database entry has no vapor-phase enthalpy data (missing Hvap at
        # Tb), so the flash's VLE fails on it. Lock it to the liquid phase,
        # as biorefineries.cellulosic does for its own Glucose. Only in this
        # set, so the baseline's Glucose is untouched.
        Glucose.at_state("l")

        H2SO4 = bst.Chemical("H2SO4")
        H2SO4.at_state("l")

        AmmoniumSulfate = bst.Chemical("AmmoniumSulfate")
        AmmoniumSulfate.at_state("s")
        # Its database liquid-viscosity correlation ('NEGLECT_P') is invalid
        # at process T/P, same issue and fix as the nutrient salts below.
        AmmoniumSulfate.copy_models_from(Water, ["mu"])

        acid_chemicals = [H2SO4, AmmoniumSulfate]

    # Gases
    CH4 = bst.Chemical("Methane", phase="g")
    CO2 = bst.Chemical("CarbonDioxide", phase="g")
    H2S = bst.Chemical("HydrogenSulfide", phase="g")
    Oxygen = bst.Chemical("Oxygen", phase="g")
    Nitrogen = bst.Chemical("Nitrogen", phase="g")

    # VFAs
    AceticAcid = bst.Chemical("AceticAcid", phase="l")
    PropionicAcid = bst.Chemical("PropionicAcid", phase="l")
    ButyricAcid = bst.Chemical("ButyricAcid", phase="l")
    ValericAcid = bst.Chemical("ValericAcid", phase="l")
    HexanoicAcid = bst.Chemical("HexanoicAcid", phase="l")

    # VFA fermentation / microbial oil pathway.
    # MicrobialOil: real properties of triolein (TAG), the standard
    # microbial/single-cell-oil proxy used across biorefineries.cane,
    # biorefineries.HP, and biorefineries.OHFA (oleaginous-yeast fermentation
    # yields are tracked directly as TAG in those biorefineries).
    MicrobialOil = bst.Chemical("MicrobialOil", search_ID="Triolein")
    MicrobialOil.Hf = -1776e3

    # CellMass: matches biorefineries.actag's 'Cells' chemical (chemicals.yaml).
    # Its formula is the generic-yeast composition also used for
    # biorefineries.cane's 'Yeast' chemical, while its Hf is the same
    # Humbird et al. 2011 value used for Z_mobilis (-31169.39 cal/mol).
    CellMass = bst.Chemical("CellMass", search_db=False, default=True, phase="s",
                             formula="CH1.61O0.56N0.16", Hf=-31169.39 * _cal2joule)
    CellMass.V.add_model(tmo.functional.rho_to_V(_rho_solids, CellMass.MW), top_priority=True)

    # Conditioner / nutrient additions. Ammonia's
    # natural phase_ref is gas; forced to liquid since it's dosed as an
    # aqueous nutrient stream (matches the NH3 handling in
    # biorefineries.cornstover/cellulosic).
    Ammonia = bst.Chemical("Ammonia")
    Ammonia.at_state("l")
    KH2PO4 = bst.Chemical("KH2PO4")
    NaOH = bst.Chemical("NaOH")
    MagnesiumSulfate = bst.Chemical("MagnesiumSulfate")

    # These are dosed as dilute solutes in aqueous nutrient streams, so their
    # own volume is treated as negligible (rho=1e5 kg/m3 proxy), matching
    # biorefineries.cane's treatment of HCl/NaOH. This also works around
    # KH2PO4 and MagnesiumSulfate's database liquid-volume correlations
    # ('NEGLECT_P') raising at ambient T/P.
    for _nutrient in (NaOH, KH2PO4, MagnesiumSulfate):
        _nutrient.V.l.add_model(tmo.functional.rho_to_V(1e5, _nutrient.MW), top_priority=True)

    # KH2PO4 and MagnesiumSulfate's database liquid-viscosity correlations
    # ('NEGLECT_P') are likewise invalid at process T/P.
    # As dilute solutes, approximate their
    # solution viscosity contribution with Water's (NaOH's own liquid mu
    # model is valid, so it's left alone).
    for _nutrient in (KH2PO4, MagnesiumSulfate):
        _nutrient.copy_models_from(Water, ["mu"])

    # ATT-only chemicals (include_att), listed below at the same positions
    # as in the ATT model.
    att_char = att_gases = att_hydrogen = att_salts = ()
    if include_att:
        # ATT (U2) char residue. No ultimate analysis of ATT char is available,
        # so the carbonaceous part uses a generic ~500 C char formula; U2 results
        # are insensitive to it because any plausible char carries ~4.2-4.4
        # available electrons per C. Cp ~1 J/g/K is a typical biochar value.
        # Feed N and S are retained in the char as element-basis species
        # (Hf = 0) because no N- or S-containing ATT products were measured.
        Char = _structural_solid("Char", "CH0.5O0.1",
                                 char_Hf_from_HHV({"C": 1, "H": 0.5, "O": 0.1}) / _cal2joule,
                                 Cp=1.0, rho=1500)
        CharN = _structural_solid("CharN", "N", 0.0, Cp=1.0, rho=1500)
        CharS = _structural_solid("CharS", "S", 0.0, Cp=1.0, rho=1500)
        CO = bst.Chemical("CO", search_ID="CarbonMonoxide", phase="g")
        C2H4 = bst.Chemical("C2H4", search_ID="Ethylene", phase="g")
        C2H6 = bst.Chemical("C2H6", search_ID="Ethane", phase="g")
        H2 = bst.Chemical("H2", search_ID="Hydrogen", phase="g")
        Na2CO3 = bst.Chemical("Na2CO3", search_ID="SodiumCarbonate")
        CaOH2 = bst.Chemical("CaOH2", search_ID="CalciumHydroxide", phase="s")
        CaCO3 = bst.Chemical("CaCO3", search_ID="CalciumCarbonate", phase="s")
        # Dissolved salt in the recycle liquor: same volume treatment as NaOH above.
        Na2CO3.V.l.add_model(tmo.functional.rho_to_V(1e5, Na2CO3.MW), top_priority=True)
        att_char, att_gases, att_hydrogen = (Char, CharN, CharS), (CO, C2H4, C2H6), (H2,)
        att_salts = (Na2CO3, CaOH2, CaCO3)

    chems = bst.Chemicals([
        Water,
        Ash, Protein, Lignin, Glucan, Xylan, Mannan, Galactan, Arabinan,
        Alginate, Fucoidan, Mannitol, OtherSolids,
        *att_char,
        CH4, CO2, *att_gases, H2S, *att_hydrogen, Oxygen, Nitrogen,
        AceticAcid, PropionicAcid, ButyricAcid, ValericAcid, HexanoicAcid,
        MicrobialOil, CellMass,
        Ammonia, KH2PO4, NaOH, *att_salts, MagnesiumSulfate,
        *hp3_chemicals,
        *acid_chemicals,
    ])
    chems.compile()

    # "solids" group derived directly from which chemicals are actually
    # locked to phase='s' above, determines which
    # chemicals count as solids in unit simulations (Press,
    # VFAMicrofilter, DigestateDecanterCentrifuge via
    # utils.get_solids_group_IDs()).
    solid_IDs = [c.ID for c in chems if c.locked_state == "s"]
    if solid_IDs:
        chems.define_group("solids", solid_IDs)

    if set_thermo:
        thermo = tmo.Thermo(chems)
        bst.settings.set_thermo(thermo)
    return chems