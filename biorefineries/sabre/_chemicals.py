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


def create_chemicals(set_thermo: bool = True):
    Water = bst.Chemical("Water")

    # Sargassum components
    # Ash modeled as CaO (following biorefineries.lactic's precedent for
    # generic biomass ash). CaO's database liquid-viscosity correlation
    # ('NEGLECT_P') is invalid at process T/P, the same issue this file
    # already works around for KH2PO4/MagnesiumSulfate below,
    # approximated with Water's viscosity for the same reason.
    CaO = bst.Chemical("CaO", phase="s", HHV=0, LHV=0)
    CaO.copy_models_from(Water, ["mu"])
    Ash = CaO.copy(ID="Ash")

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
    # alginic acid or its mannuronic/guluronic acid monomers (checked NIST
    # WebBook and general literature), so Hf borrows Glucan's structural-
    # carbohydrate value as the least-bad available proxy; Cn/V likewise
    # reuse Glucan's Cp/density basis rather than bst.Chemical's generic
    # (and here badly wrong -- implied density ~1e6 kg/m3) default estimates.
    Alginate = _structural_solid("Alginate", "C6H8O6", -233200)
    # Fucose repeat unit, dehydrated (C6H12O5 - H2O); ignores fucoidan's sulfate
    # substitution. No literature Hf found for fucoidan or its L-fucose
    # monomer either, so Hf and Cn/V all borrow Glucan's basis for the same
    # reason as Alginate.
    Fucoidan = _structural_solid("Fucoidan", "C6H10O4", -233200)
    Mannitol = bst.Chemical("Mannitol")
    # No known formula/composition for this lumped catch-all; treated as
    # generically Glucan-like (same MW/Cn/V/Hf), consistent with how
    # Mannan/Galactan already borrow Glucan's properties above.
    OtherSolids = Glucan.copy("OtherSolids")

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

    # Gases
    CH4 = bst.Chemical("Methane", phase="g")
    CO2 = bst.Chemical("CarbonDioxide", phase="g")
    CO = bst.Chemical("CO", search_ID="CarbonMonoxide", phase="g")
    C2H4 = bst.Chemical("C2H4", search_ID="Ethylene", phase="g")
    C2H6 = bst.Chemical("C2H6", search_ID="Ethane", phase="g")
    H2S = bst.Chemical("HydrogenSulfide", phase="g")
    H2 = bst.Chemical("H2", search_ID="Hydrogen", phase="g")
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
    # yields are tracked directly as TAG in those biorefineries). The
    # database entry for triolein itself has no Hf (confirmed by testing
    # bst.Chemical('Triolein').Hf is None), so biorefineries.cane doesn't
    # rely on a lookup either -- it hardcodes the same literature value
    # (Hf_triolein) used here, in create_acyl_olein().
    MicrobialOil = bst.Chemical("MicrobialOil", search_ID="Triolein")
    MicrobialOil.Hf = -1776e3

    # CellMass: matches biorefineries.actag's 'Cells' chemical (chemicals.yaml),
    # which is explicitly a Yarrowia lipolytica stand-in (synonym
    # 'YarrowiaLipolytica') -- same organism as sabre's fermentation step.
    # Its formula is the generic-yeast composition also used for
    # biorefineries.cane's 'Yeast' chemical, while its Hf is the same
    # Humbird et al. 2011 value used for Z_mobilis (-31169.39 cal/mol);
    # actag pairs that Hf with the yeast formula rather than Z_mobilis's
    # own bacterial formula, which is a better match for Yarrowia than the
    # bacterium-based placeholder used here previously.
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
    Na2CO3 = bst.Chemical("Na2CO3", search_ID="SodiumCarbonate")
    CaOH2 = bst.Chemical("CaOH2", search_ID="CalciumHydroxide", phase="s")
    CaCO3 = bst.Chemical("CaCO3", search_ID="CalciumCarbonate", phase="s")
    MagnesiumSulfate = bst.Chemical("MagnesiumSulfate")

    # These are dosed as dilute solutes in aqueous nutrient streams, so their
    # own volume is treated as negligible (rho=1e5 kg/m3 proxy), matching
    # biorefineries.cane's treatment of HCl/NaOH. This also works around
    # KH2PO4 and MagnesiumSulfate's database liquid-volume correlations
    # ('NEGLECT_P') raising at ambient T/P.
    for _nutrient in (NaOH, Na2CO3, KH2PO4, MagnesiumSulfate):
        _nutrient.V.l.add_model(tmo.functional.rho_to_V(1e5, _nutrient.MW), top_priority=True)

    # KH2PO4 and MagnesiumSulfate's database liquid-viscosity correlations
    # ('NEGLECT_P') are likewise invalid at process T/P.
    # As dilute solutes, approximate their
    # solution viscosity contribution with Water's (NaOH's own liquid mu
    # model is valid, so it's left alone).
    for _nutrient in (KH2PO4, MagnesiumSulfate):
        _nutrient.copy_models_from(Water, ["mu"])

    chems = bst.Chemicals([
        Water,
        Ash, Protein, Lignin, Glucan, Xylan, Mannan, Galactan, Arabinan,
        Alginate, Fucoidan, Mannitol, OtherSolids,
        Char, CharN, CharS,
        CH4, CO2, CO, C2H4, C2H6, H2S, H2, Oxygen, Nitrogen,
        AceticAcid, PropionicAcid, ButyricAcid, ValericAcid, HexanoicAcid,
        MicrobialOil, CellMass,
        Ammonia, KH2PO4, NaOH, Na2CO3, CaOH2, CaCO3, MagnesiumSulfate,
    ])
    chems.compile()

    # "solids" group derived directly from which chemicals are actually
    # locked to phase='s' above -- the single source of truth for which
    # chemicals count as solids in unit simulations (Press,
    # VFAMicrofilter, DigestateDecanterCentrifuge via
    # utils.get_solids_group_IDs()) is the chemical models themselves, not
    # a separately-maintained ID list that could drift out of sync with them.
    solid_IDs = [c.ID for c in chems if c.locked_state == "s"]
    if solid_IDs:
        chems.define_group("solids", solid_IDs)

    if set_thermo:
        thermo = tmo.Thermo(chems)
        bst.settings.set_thermo(thermo)
    return chems