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


def create_chemicals(set_thermo: bool = True, include_att: bool = False):
    """
    Parameters
    ----------
    include_att : bool
        If True, also include the chemicals used only by the alkaline
        thermal treatment (ATT) pathway (Char, CharN, CharS, CO, C2H4, C2H6,
        H2, Na2CO3, CaOH2, CaCO3). Kept behind its own flag so the chemical
        sets (and hence the results) of the other SaBRe pathways are unchanged.
    """
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
    # Rare earth oxides of the seaweed (att.yaml downstream.ree_recovery): a lumped inert oxide, Nd2O3 molar mass, no atoms.
    REO = bst.Chemical("REO", search_db=False, default=True, phase="s", MW=336.48, HHV=0, LHV=0, Hf=0.0)
    REO.copy_models_from(CaO, ["Cn", "V", "mu"])

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
    if include_att:
        # ATT feed composition from the NLR Sargassum preprint (Wiatrowski et
        # al., Research Square 2026, Tables 1, S-5, S-6): the unidentified
        # remainder (29.6 % of dry solids in the 15 psi pressed solids, incl.
        # 1 % FAME) is given the C/H/O/N formula that makes the identified
        # pseudo-components plus this remainder reproduce the measured CHN of
        # the sample (C 31.36, H 3.88, N 1.16 wt % of dry solids; O by
        # difference): OtherSolids = 48.9 wt % C, 5.7 H, 45.1 O, 0.5 N.
        # Hf per gram borrows Glucan's value (the ATT model re-references the
        # feed Hf to the HHV in att.yaml, so it does not enter the U2 duty).
        OtherSolids = _structural_solid("OtherSolids", "CH1.39O0.69N0.009", -1438.3 * 24.62)

    # Gases
    CH4 = bst.Chemical("Methane", phase="g")
    CO2 = bst.Chemical("CarbonDioxide", phase="g")
    Oxygen = bst.Chemical("Oxygen", phase="g")
    Nitrogen = bst.Chemical("Nitrogen", phase="g")

    # NaOH is dosed as a dilute solute, so its own volume is treated as negligible (rho = 1e5 kg/m3 proxy),
    # as biorefineries.cane does for HCl/NaOH.
    NaOH = bst.Chemical("NaOH")
    NaOH.V.l.add_model(tmo.functional.rho_to_V(1e5, NaOH.MW), top_priority=True)

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
        # ATT Scenario 1 lumped residual product of U2: a stoichiometric surrogate CH0.5O_b for the
        # uncharacterized carbon-containing residue (NOT measured char). U2 solves b from its C/H/O balance at
        # run time, so the product is carried as two basis pseudo-components with the same H/C (end members
        # b = 0 and b = 2); their sum is ONE lumped product. Hf by the same Channiwala-Parikh HHV route as the
        # char; the correlation is linear in the element mass fractions, so the sum equals the correlation at
        # the lumped composition (O-rich compositions lie outside its validation range). Cp 1 J/g/K, solid.
        ResidueCH = _structural_solid("ResidueCH", "CH0.5",
                                      char_Hf_from_HHV({"C": 1, "H": 0.5}) / _cal2joule, Cp=1.0, rho=1500)
        ResidueCHO = _structural_solid("ResidueCHO", "CH0.5O2",
                                       char_Hf_from_HHV({"C": 1, "H": 0.5, "O": 2}) / _cal2joule, Cp=1.0, rho=1500)
        CO = bst.Chemical("CO", search_ID="CarbonMonoxide", phase="g")
        H2 = bst.Chemical("H2", search_ID="Hydrogen", phase="g")
        Na2CO3 = bst.Chemical("Na2CO3", search_ID="SodiumCarbonate")
        CaOH2 = bst.Chemical("CaOH2", search_ID="CalciumHydroxide", phase="s")
        CaCO3 = bst.Chemical("CaCO3", search_ID="CalciumCarbonate", phase="s")
        # Inert mineral impurities of the waste carbide lime (SiO2, Al2O3, Fe2O3, MgO, sulfate; lumped, with the
        # properties of SiO2): they pass through the process as insoluble solids.
        LimeInerts = bst.Chemical("LimeInerts", search_ID="SiO2", phase="s")
        # Soluble salts of the seaweed ash (K, Na chlorides; user decision 2026-11-03): they dissolve with the Na2CO3 and are
        # removed from the NaOH loop by the salt crystallizer XL1.
        NaCl = bst.Chemical("NaCl", search_ID="SodiumChloride")
        KCl = bst.Chemical("KCl", search_ID="PotassiumChloride")
        # Dissolved salt in the recycle liquor: same volume treatment as NaOH above.
        # Reagents of the REE leach and oxalate precipitation (att.yaml downstream.ree_recovery).
        HCl = bst.Chemical("HCl", search_ID="HCl")
        OxalicAcid = bst.Chemical("OxalicAcid", search_ID="OxalicAcid", phase="s")
        for _salt in (Na2CO3, NaCl, KCl, HCl):
            _salt.V.l.add_model(tmo.functional.rho_to_V(1e5, _salt.MW), top_priority=True)
        att_char, att_gases, att_hydrogen = (Char, CharN, CharS, ResidueCH, ResidueCHO), (CO,), (H2,)
        att_salts = (Na2CO3, CaOH2, CaCO3, LimeInerts, NaCl, KCl, REO, HCl, OxalicAcid)

    chems = bst.Chemicals([
        Water,
        Ash, Protein, Lignin, Glucan, Xylan, Mannan, Galactan, Arabinan,
        Alginate, Fucoidan, Mannitol, OtherSolids,
        *att_char,
        CH4, CO2, *att_gases, *att_hydrogen, Oxygen, Nitrogen,
        NaOH, *att_salts,
    ])
    chems.compile()

    # "solids" group derived directly from which chemicals are actually
    # locked to phase='s' above, determines which
    # chemicals count as solids in unit simulations.
    solid_IDs = [c.ID for c in chems if c.locked_state == "s"]
    if solid_IDs:
        chems.define_group("solids", solid_IDs)

    if set_thermo:
        thermo = tmo.Thermo(chems)
        bst.settings.set_thermo(thermo)
    return chems