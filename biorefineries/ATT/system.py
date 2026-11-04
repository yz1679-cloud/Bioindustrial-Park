# Bioindustrial-Park: BioSTEAM's Premier Biorefinery Models and Results
# Copyright (C) 2026-, Yu Zhou,
#                      Yalin Li <mailto.yalin.li@gmail.com>
#
# This module is under the UIUC open-source license. See
# github.com/BioSTEAMDevelopmentGroup/biosteam/blob/master/LICENSE.txt
# for license details.


import biosteam as bst

from biorefineries.ATT._chemicals import create_chemicals
from biorefineries.ATT.utils import (
    make_sargassum_feed,
    load_assumptions,
    get_feedstock_type_params,
)
from biorefineries.ATT.units._att import (
    ATTReactor,
    CausticizationReactor,
    NaOHEvaporator,
    ATTDrumDryer,
    ATTCompressor,
    ATTMolecularSieve,
    ATTPSA,
    ATTScrubber,
    ATTResidueSplit,
    ATTSaltCrystallizer,
    ATTReeLeach,
    ATTReeRoaster,
    aqueous_naoh_enthalpy_correction_kJph,
    _SARGASSUM_DRY_IDS,
)

__all__ = ("create_att_system", "get_att_press_retention", "get_att_reference_dry_feed_kgph")

_ATT_DATA = load_assumptions("att.yaml")["att"]
_FEEDSTOCK_DATA = load_assumptions("feedstock.yaml")

_ATT_FEED_PREP = _ATT_DATA["feed_preparation"]
_ATT = _ATT_DATA["reactor"]
_ATT_U3 = _ATT_DATA["gas_treatment"]
_ATT_DOWNSTREAM = _ATT_DATA["downstream"]
if "heat_recovery" not in _ATT_DATA:
    raise KeyError(
        "Missing 'att.heat_recovery' in biorefineries/ATT/data/att.yaml. "
        "Install the data file as data/att.yaml (not under a versioned filename)."
    )
_ATT_HEAT_RECOVERY = _ATT_DATA["heat_recovery"]
_COST_YEAR = load_assumptions("tea.yaml")["cost_year"]


def get_att_press_retention():
    """
    Fraction of each pseudo-component that stays in the presscake: the share
    of dry solids kept by the press (preprint Table 2) times the ratio of the
    pressed to the fresh composition, capped at 1.
    """
    types = _FEEDSTOCK_DATA["feedstock_type"]
    fresh = types[_ATT_FEED_PREP["feedstock_type"]]["dry_composition"]
    pressed = types[_ATT_FEED_PREP["presscake_feedstock_type"]]["dry_composition"]
    recovery = float(_ATT_FEED_PREP["press"]["solids_recovery"])
    return {ID: min(1.0, recovery * pressed[ID] / fresh[ID]) for ID in fresh}


def get_att_reference_dry_feed_kgph():
    """
    Dry presscake fed to the ATT plant at the NLR preprint scale (3 million wet
    t/yr of fresh Sargassum, att.yaml feed_preparation.scale): the dry
    presscake that the same Sargassum leaves at a biostimulant plant.
    """
    from biorefineries.ATT.utils import OPERATING_DAYS_PER_YEAR
    fresh = _FEEDSTOCK_DATA["feedstock_type"][_ATT_FEED_PREP["feedstock_type"]]
    wet_kgph = float(_ATT_FEED_PREP["scale"]["wet_feed_tonnes_per_year"]) * 1e3 / (OPERATING_DAYS_PER_YEAR * 24.0)
    dry = wet_kgph * (1.0 - float(fresh["moisture_frac"]))
    retention = get_att_press_retention()
    return dry * sum(retention[ID] * x for ID, x in fresh["dry_composition"].items())


def create_att_system(
    dry_sargassum_kgph=1.0,
    ree_recovery=None,
    ree_grade=None,
    ree_params=None,
    psa=None,
    co2_scrubber=None,
):
    """
    Build the alkaline thermal treatment (ATT) process.

    Parameters
    ----------
    dry_sargassum_kgph : float
        Dry-presscake scaling basis [kg dry solids/h]: the ATT plant receives the
        presscake of a biostimulant plant (normally a waste). The actual inlet
        stream is constructed from the feedstock.yaml wet-feed composition
        and therefore has a larger wet mass flow. The gross NaOH is
        naoh_kg_per_kg_dry x the dry Sargassum reaching M1.
    ree_recovery : bool or None
        REE recovery from the char (att.yaml downstream.ree_recovery): the washed char cake is leached with HCl (LC1), the REE
        are precipitated with oxalic acid, the leached char and the oxalate are roasted (RO1) into the REE product (sold on its
        REO content) and the spent leachate is recycled to the dissolver D1. The seaweed is assumed to carry the REE already
        (att.yaml seaweed_TREE_ppm); the AMD capture section (soak, screen, press) is NOT modeled. Needs the char yield.
        None uses att.yaml downstream.ree_recovery.enabled (default true).
    ree_grade : float or None
        REO weight fraction of the roasted REE product (0 < x <= 1); None uses att.yaml downstream.ree_recovery.product_REO_wt_frac.
        The REO mass of the product does not change, only the mineral filler that dilutes it (sensitivity: analyses/ree_sensitivity.py).
    ree_params : dict or None
        Overrides of other att.yaml downstream.ree_recovery keys (e.g. a seaweed soaked in a concentrated REE solution:
        ``analyses.ree_sensitivity.concentrated_soak_params``). Unknown keys raise.
    co2_scrubber : bool or None
        Scrub the CO2 out of the cooled gas (after U3C, before U3D) with a Ca(OH)2 slurry (SCRUB) and dewater the
        CaCO3 slurry in the filter F3 (cake at the F2 moisture, filtrate recycled to the scrubber). The scrubber lime
        is the feed stream ``scrubber_lime`` (priced like ``lime``). None uses att.yaml
        downstream.co2_scrubber.enabled (ATT Scenario 1: True).
    psa : bool or None
        Purify the compressed gas in a PSA (U3P, 90 % H2 recovery, tail gas burned) or not. None uses
        att.yaml gas_treatment.psa_enabled (ATT Scenario 1: False; the scrubbed, dried and
        compressed gas leaves as h2_product).

    Returns
    -------
    sys : bst.System
        ATT process system.
    """

    # --------------------------------------------------------------
    # Thermodynamic property package
    # --------------------------------------------------------------
    # Reuse an ATT thermo already set; otherwise (none, or another SaBRe
    # pathway's chemicals without the ATT species) create the ATT one.
    try:
        chemicals = bst.settings.get_chemicals()
    except Exception:
        chemicals = None
    if chemicals is None or "ResidueCH" not in chemicals:
        create_chemicals(include_att=True)
    # All equipment is costed at the cost-year CEPCI of tea.yaml (2020 USD).
    bst.CE = float(_COST_YEAR["reference_CE"])

    # --------------------------------------------------------------
    # ATT case selection
    # --------------------------------------------------------------
    att_case_data = _ATT["cases"][_ATT["baseline_case"]]

    # --------------------------------------------------------------
    # Raw Sargassum feed - use the default SaBRe composition.
    #
    # Do not override moisture or ash with ATT-specific values here.
    # dry_sargassum_kgph is retained only as a convenient dry-solids
    # scaling basis.
    # --------------------------------------------------------------
    feed_params = get_feedstock_type_params(
        _FEEDSTOCK_DATA,
        _ATT_FEED_PREP["presscake_feedstock_type"],
    )

    raw_moisture_frac = float(
        feed_params["moisture_frac"]
    )

    fresh_feed_kgph = (
        dry_sargassum_kgph
        / (1.0 - raw_moisture_frac)
    )

    raw_feed = make_sargassum_feed(
        fresh_feed_kgph=fresh_feed_kgph,
        moisture_frac=raw_moisture_frac,
        dry_composition=feed_params["dry_composition"],
    )

    raw_feed.ID = "att_sargassum_feed"

    # Seaweed ash split (user decision 2026-11-03, collaborator's metal contents): part of the ash is insoluble minerals (Ca, Mg;
    # they stay in the char), the rest is soluble K and Na salts, here all as KCl and NaCl.
    ash_cfg = _ATT_FEED_PREP["ash_split"]
    ash_kgph0 = float(raw_feed.imass["Ash"])
    shares = {"Ash": float(ash_cfg["insoluble_share_of_ash"]), "NaCl": float(ash_cfg["NaCl_share_of_ash"]), "KCl": float(ash_cfg["KCl_share_of_ash"])}
    if abs(sum(shares.values()) - 1.0) > 1e-6:
        raise ValueError("att.yaml feed_preparation.ash_split: the shares of the ash must add up to 1")
    for ID, share in shares.items():
        raw_feed.imass[ID] = share * ash_kgph0
    salt_cfg = _ATT_DOWNSTREAM["salt_crystallizer"]
    char_cfg = _ATT_DOWNSTREAM["char"]
    ree_cfg = dict(_ATT_DOWNSTREAM.get("ree_recovery", {}))
    if ree_grade is not None:
        if not 0.0 < float(ree_grade) <= 1.0:
            raise ValueError("ree_grade must be in (0, 1]")
        ree_cfg["product_REO_wt_frac"] = float(ree_grade)
    for k, v in (ree_params or {}).items():
        if k not in ree_cfg:
            raise KeyError(f"unknown ree_recovery parameter {k!r}")
        ree_cfg[k] = v
    use_ree = (bool(ree_cfg.get("enabled", False)) if ree_recovery is None else bool(ree_recovery))
    if use_ree:       # the REE of the seaweed, carved out of its insoluble minerals
        reo_kgph = float(ree_cfg["seaweed_TREE_ppm"]) * 1e-6 * float(ree_cfg["REO_per_TREE"]) * dry_sargassum_kgph
        raw_feed.imass["REO"] = reo_kgph
        raw_feed.imass["Ash"] = float(raw_feed.imass["Ash"]) - reo_kgph

    # --------------------------------------------------------------
    # D0 - Thermal drying before ATT.
    #
    # Mechanical pressing is used only to reach the 75 wt% moisture
    # press-cake baseline. A native BioSTEAM DrumDryer then removes
    # additional water until the Sargassum reaches the ATT-process
    # assumption of 50 wt% moisture.
    #
    # Steam is used here as a provisional utility representation so
    # BioSTEAM calculates the thermodynamic heat demand without
    # hard-coding a heat duty. Any later heat-integration credit will
    # be added only after the relevant hot/cold streams are defined.
    # --------------------------------------------------------------
    dryer_air = bst.Stream("dryer_air")
    dryer_backup_fuel = bst.Stream("dryer_backup_fuel")

    # Drying-air flow: sized so the exhaust leaves at the target relative
    # humidity at the dryer temperature. The installed BioSTEAM (2.53) takes
    # the exhaust RH directly (DrumDryer RH: y_water = RH * Psat(T) / P,
    # air = water * (1 - y) / y); the SaBRe copy passed the equivalent
    # kg-air/kg-water ratio R, which this DrumDryer does not accept.
    _dryer_cfg = _ATT_FEED_PREP["dryer"]

    D0 = ATTDrumDryer(
        "D0",
        ins=(
            raw_feed,
            dryer_air,
            dryer_backup_fuel,
        ),
        outs=(
            "att_moisture_adjusted_sargassum",
            "dryer_exhaust",
            "dryer_emissions",
        ),
        split={"Water": 1.0},
        moisture_content=_ATT_FEED_PREP[
            "att_sargassum_moisture_wt_frac"
        ],
        T=_ATT_FEED_PREP[
            "dryer_temperature_K"
        ],
        P=101325.0,
        utility_agent="Steam",
        RH=float(_dryer_cfg["exhaust_relative_humidity"]),
        length_to_diameter=float(_dryer_cfg["drum_length_to_diameter"]),
        max_drum_diameter_m=float(_dryer_cfg["max_drum_diameter_m"]),
    )

    # --------------------------------------------------------------
    # ATT NaOH requirement (ATT Scenario 1)
    #
    #     gross NaOH = naoh_kg_per_kg_dry (1.0) x dry Sargassum reaching M1
    #
    # "Dry Sargassum" is every feedstock solid leaving D0 (ash included,
    # water excluded); the recycle liquor and the fresh NaOH join later in
    # M1 and are not part of it. Gross NaOH is recycled + fresh NaOH. The
    # gas yields stay on the daf basis in U2 and are not rescaled by it.
    # --------------------------------------------------------------
    naoh_kg_per_kg_dry = float(
        att_case_data[
            "naoh_kg_per_kg_dry"
        ]
    )

    naoh_recycle = bst.Stream("naoh_recycle")
    fresh_naoh_solid = bst.Stream(
        "fresh_naoh_solid",
        phase="s",
        T=_ATT_FEED_PREP["fresh_naoh_temperature_K"],
        P=101325.0,
    )

    # --------------------------------------------------------------
    # Initial recycle guess for sequential-modular convergence
    #
    # With the NaOH recovered downstream of U2, an exactly empty
    # recycle stream would send zero NaOH to the first U2 pass. That would
    # generate zero Na2CO3, D1 would add zero dissolution water, and F1
    # could not satisfy a 30 wt% water cake while retaining representative
    # mother liquor. This is only a startup/tear-stream issue, not a
    # steady-state process infeasibility.
    #
    # Seed the recycle with the gross NaOH requirement and enough water to
    # make the initial NaOH-only liquor meet the total-liquor concentration
    # target. Na2CO3 is initialized at zero and is determined by recycle
    # convergence.
    # --------------------------------------------------------------
    initial_naoh_kgph = (
        naoh_kg_per_kg_dry
        * dry_sargassum_kgph
    )
    initial_target_naoh_wt_frac = float(
        _ATT_DOWNSTREAM["recycle_naoh_wt_frac"]
    )
    initial_water_kgph = (
        initial_naoh_kgph
        * (1.0 - initial_target_naoh_wt_frac)
        / initial_target_naoh_wt_frac
    )

    naoh_recycle.imass["NaOH"] = initial_naoh_kgph
    naoh_recycle.imass["Water"] = initial_water_kgph
    naoh_recycle.imass["Na2CO3"] = 0.0
    naoh_recycle.phase = "l"
    naoh_recycle.T = _ATT_DOWNSTREAM["concentration_temperature_K"]
    naoh_recycle.P = 101325.0

    # --------------------------------------------------------------
    # M1 - ATT feed preparation
    #
    # M1 combines the conditioned Sargassum with the recycle liquor (EC1
    # concentrate) and the fresh SOLID NaOH makeup, which dissolves in the
    # water of the wet feed. Fresh NaOH = gross requirement minus the NaOH
    # recovered in the recycle liquor; no water is added.
    # --------------------------------------------------------------
    M1 = bst.Mixer(
        "M1",
        ins=(
            D0 - 0,
            naoh_recycle,
            fresh_naoh_solid,
        ),
        outs=("att_feed",),
    )

    @M1.add_specification(run=True)
    def adjust_solid_naoh_makeup():
        required_naoh_kgph = required_gross_naoh_kgph()
        recovered_naoh_kgph = float(naoh_recycle.imass["NaOH"])
        fresh_naoh_kgph = max(required_naoh_kgph - recovered_naoh_kgph, 0.0)

        fresh_naoh_solid.empty()
        fresh_naoh_solid.imass["NaOH"] = fresh_naoh_kgph
        fresh_naoh_solid.phase = "s"
        fresh_naoh_solid.T = _ATT_FEED_PREP["fresh_naoh_temperature_K"]
        fresh_naoh_solid.P = 101325.0

        M1._required_gross_naoh_kgph = required_naoh_kgph
        M1._recovered_naoh_kgph = recovered_naoh_kgph
        M1._fresh_naoh_makeup_kgph = fresh_naoh_kgph

        # M1 is adiabatic, so the true U2 feed enthalpy is ThermoSTEAM's
        # value plus the heat-of-solution correction of the NaOH(aq) recycle
        # liquor (ThermoSTEAM treats dissolved NaOH as subcooled molten
        # NaOH). The fresh NaOH enters as a solid, whose enthalpy is the
        # same in ThermoSTEAM and in reality; its heat of solution only
        # raises the true feed temperature, not the feed enthalpy, so it
        # needs no correction.
        U2.aqueous_feed_enthalpy_correction_kJph = (
            aqueous_naoh_enthalpy_correction_kJph(naoh_recycle)
        )

    # --------------------------------------------------------------
    # U2 - ATT reactor
    # --------------------------------------------------------------
    # PSA tail gas is the fuel input of the U2 furnace; its stream is created here because the PSA (U3P)
    # that makes it comes later in the flowsheet (a thermal-only loop: the gas does not enter the reaction).
    tail_gas_fuel = bst.Stream("u3_tail_gas", phase="g")
    U2 = ATTReactor(
        "U2",
        ins=(M1 - 0, tail_gas_fuel),
        outs=(
            "att_gas",
            "att_residue",
        ),
    )

    # --------------------------------------------------------------
    # U3 - ATT gas treatment train
    #
    # Current sequence:
    #
    #   U2 hot gas/steam
    #       -> U3HX cooling / partial condensation
    #       -> U3C equilibrium gas/liquid separation
    #       -> U3D native molecular-sieve dehydration
    #       -> U3P idealized PSA surrogate
    #           -> raw H2 product -> U3K compressor -> H2 product
    #           -> PSA tail gas (future combustion / heat recovery)
    #
    # Native BioSTEAM units are used wherever possible:
    #   * HXutility for U2-to-U3 cooling / partial condensation
    #   * Flash for equilibrium gas/liquid separation
    #   * MolecularSieve for reduced-order gas dehydration
    #   * Splitter for the current idealized PSA material balance
    #   * IsothermalCompressor for H2 product compression
    #
    # The dryer and PSA are deliberately reduced-order placeholders
    # because adsorbent, PSA cycle, recovery/purity, and regeneration
    # specifications have not yet been provided by collaborators.
    # --------------------------------------------------------------

    # U3HX - Cool the hot U2 gas/steam before gas-liquid separation.
    #
    # This is the explicit heat exchanger between U2 and U3 requested in
    # the process diagram. It uses BioSTEAM's native HXutility so the
    # process-stream enthalpy drop is calculated thermodynamically and can
    # later be connected to heat integration. No heat-recovery credit is
    # applied yet.
    U3HX = bst.HXutility(
        "U3HX",
        ins=U2 - 0,
        outs=("u3_cooled_multiphase",),
        T=float(
            _ATT_U3["condenser_temperature_K"]
        ),
        rigorous=True,
        cool_only=True,
        estimate_pressure_drop=False,
        U=float(_ATT_HEAT_RECOVERY["U3HX_heat_transfer_coefficient_kW_per_m2_per_K"]),
        material=_ATT_HEAT_RECOVERY["cooler_material"],
    )

    # U3C - Native equilibrium flash / gas-liquid separator.
    #
    # U3HX provides the cooling duty. U3C then separates the cooled
    # multiphase stream into wet gas and condensate at the same target
    # temperature and pressure.
    U3C = bst.Flash(
        "U3C",
        ins=U3HX - 0,
        outs=(
            "u3_wet_gas",
            "u3_condensate",
        ),
        T=float(
            _ATT_U3["condenser_temperature_K"]
        ),
        P=float(
            _ATT_U3["condenser_pressure_Pa"]
        ),
    )

    # U3D - Native BioSTEAM molecular-sieve gas dryer.
    #
    # We keep the same reduced-order material specification used in the U3 train:
    # all non-water gases pass to the dry-gas outlet and Water is removed
    # according to the YAML split. The improvement here is that U3D is now
    # represented by BioSTEAM's native MolecularSieve equipment rather than a
    # generic Splitter, so utility/design/cost bookkeeping is available.
    #
    # IMPORTANT: BioSTEAM's built-in MolecularSieve cost correlation was
    # developed for ethanol/water dehydration. Material separation is useful
    # here, but equipment cost/utility results remain provisional for ATT gas
    # service until a gas-dryer specification is available.
    dryer_split = {
        ID: 1.0
        for ID in U2.outs[0].chemicals.IDs
    }
    dryer_split["Water"] = float(
        _ATT_U3[
            "dryer_water_to_dry_gas_fraction"
        ]
    )

    # SCRUB - optional CO2 scrubber on the cooled gas (Ca(OH)2 slurry, carbonation to CaCO3); its slurry is dewatered in
    # F3 (defined with the other filters) and the filtrate returns to the scrubber.
    scrub_cfg = _ATT_DOWNSTREAM["co2_scrubber"]
    co2_scrubber = bool(scrub_cfg["enabled"] if co2_scrubber is None else co2_scrubber)
    SCRUB = scrubber_filtrate = None
    if co2_scrubber:
        scrubber_filtrate = bst.Stream("scrubber_filtrate", Water=1.0, units="kg/hr")
        SCRUB = ATTScrubber(
            "SCRUB",
            ins=(U3C - 0, bst.Stream("scrubber_lime"), scrubber_filtrate, bst.Stream("scrubber_makeup_water")),
            outs=("u3_scrubbed_gas", "scrubber_slurry"),
            T=float(scrub_cfg["temperature_K"]),
            co2_capture=float(scrub_cfg["co2_capture"]),
            lime_excess=float(scrub_cfg["lime_excess"]),
            slurry_solids_wt_frac=float(scrub_cfg["slurry_solids_wt_frac"]),
            tau_h=float(scrub_cfg["tank_tau_h"]),
        )

    U3D = ATTMolecularSieve(
        "U3D",
        ins=(SCRUB - 0) if SCRUB is not None else (U3C - 0),
        outs=(
            "u3_dry_gas",
            "u3_dryer_removed_water",
        ),
        split=dryer_split,
        regeneration_T_K=float(_ATT_HEAT_RECOVERY["u3d_regeneration_temperature_K"]),
    )

    # U3P - Idealized PSA surrogate using a native component Splitter.
    # H2 recovery is specified explicitly; all non-H2 gases report to
    # the tail-gas branch in the baseline.
    psa_split = {
        ID: float(
            _ATT_U3[
                "psa_non_h2_to_product_fraction"
            ]
        )
        for ID in U2.outs[0].chemicals.IDs
    }
    psa_split["H2"] = float(
        _ATT_U3["psa_h2_recovery"]
    )

    psa = bool(_ATT_U3["psa_enabled"] if psa is None else psa)

    # U3K - Native BioSTEAM compressor of the dried gas to the H2 delivery
    # pressure (= PSA feed pressure when there is a PSA). Pressure/efficiency
    # are provisional and live in att.yaml. Without a PSA its outlet is the product.
    U3K = ATTCompressor(
        "U3K",
        ins=U3D - 0,
        outs=("u3_compressed_gas" if psa else "h2_product",),
        P=float(
            _ATT_U3["h2_product_pressure_Pa"]
        ),
        eta=float(
            _ATT_U3[
                "h2_compressor_efficiency"
            ]
        ),
        vle=False,
        compressor_type=_ATT_U3["h2_compressor_type"],
        intercooler_T_K=float(_ATT_HEAT_RECOVERY["u3k_interstage_temperature_K"]),
    )

    # U3P - PSA surrogate at the PSA feed pressure; the H2 product leaves at
    # that pressure and the tail gas is let down to the burner pressure (U3V).
    U3P = U3V = None
    if psa:
        U3P = ATTPSA(
            "U3P",
            ins=U3K - 0,
            outs=(
                "h2_product",
                "u3_tail_gas_high_pressure",
            ),
            split=psa_split,
            anchor_installed_cost_usd=float(_ATT_U3["psa_cost"]["anchor_installed_cost_usd"]),
            anchor_capacity_t_H2_per_day=float(_ATT_U3["psa_cost"]["anchor_capacity_t_H2_per_day"]),
            exponent=float(_ATT_U3["psa_cost"]["exponent"]),
            cost_factor=float(_ATT_U3["psa_cost"]["cost_factor"]),
        )

        U3V = bst.IsenthalpicValve(
            "U3V",
            ins=U3P - 1,
            outs=tail_gas_fuel,
            P=float(_ATT_U3["tail_gas_pressure_Pa"]),
        )

    # --------------------------------------------------------------
    # RC1 - Post-ATT RESIDUE cooling to 90 degC
    #
    # Current resolved process interpretation:
    # - The hot U2 gas/steam stream is handled by the U3 gas-treatment
    #   train above and is NOT cooled in RC1.
    # - Only the solid ATT residue is cooled from 500 degC to 90 degC
    #   before dissolution / filtration / causticization.
    #
    # RC1 uses native BioSTEAM HXutility for thermodynamic duty/state
    # calculation. Its generic shell-and-tube costing should NOT be
    # treated as the final solid-cooler equipment cost.
    #
    # The rejected residue heat is reported only as PHYSICAL HEAT
    # AVAILABLE. It is not yet credited as usable process heat.
    # --------------------------------------------------------------
    residue_cooling_target_K = float(
        _ATT_HEAT_RECOVERY[
            "residue_cooling_target_temperature_K"
        ]
    )

    RC1 = bst.HXutility(
        "RC1",
        ins=U2 - 1,
        outs=("cooled_att_residue",),
        T=residue_cooling_target_K,
        rigorous=bool(
            _ATT_HEAT_RECOVERY[
                "residue_cooler_rigorous_vle"
            ]
        ),
        cool_only=True,
        estimate_pressure_drop=bool(
            _ATT_HEAT_RECOVERY[
                "solid_cooler_estimate_pressure_drop"
            ]
        ),
        U=float(_ATT_HEAT_RECOVERY["RC1_heat_transfer_coefficient_kW_per_m2_per_K"]),
        material=_ATT_HEAT_RECOVERY["cooler_material"],
    )

    # RS1 - the insoluble char of the water dissolution is att.yaml downstream.char.yield_g_per_g_dry_feed g/g of the dry feed; the rest of the lumped residual carbon of U2
    # is not tracked (att.yaml downstream.char).
    RS1 = ATTResidueSplit(
        "RS1", ins=RC1 - 0, outs=("att_residue_to_D1", "untracked_organics"),
        char_yield=float(char_cfg["yield_g_per_g_dry_feed"]),
        dry_feed_kgph=lambda: sum(float(D0.outs[0].imass[ID]) for ID in _SARGASSUM_DRY_IDS),
        char_species=char_cfg["species"])

    # --------------------------------------------------------------
    # D1 - Dissolution
    #
    # Dissolve Na2CO3 in the ATT residue before filtration.
    #
    # NOTE:
    # The current dissolution-water ratio is taken from the collaborator
    # process assumptions. Its source/basis should still be retained and
    # verified before final publication.
    # --------------------------------------------------------------
    # Dissolution water is first taken from the process condensates (EC1
    # evaporator condensate, recycled from the previous iteration, and the
    # U3C gas condensate); fresh water only makes up the rest and any
    # condensate in excess of the demand leaves as wastewater.
    dissolution_water = bst.Stream(
        "dissolution_water",
        Water=0.0,
        units="kg/hr",
    )
    ec1_condensate = bst.Stream("ec1_condensate", Water=0.0, units="kg/hr")
    dissolution_water_kg_per_kg_Na2CO3 = float(
        _ATT_DOWNSTREAM["dissolution_water_kg_per_kg_Na2CO3"]
    )

    wash_settings = _ATT_DOWNSTREAM["f2_washing"]
    ratio = float(wash_settings["wash_ratio_kg_per_kg_dry_cake"])
    # The F2 wash liquor (dilute NaOH / Na2CO3) is recycled to the dissolver, where it replaces condensate / fresh
    # dissolution water. The condensate in excess of the dissolver demand (clean water: no solutes) is the wash water.
    wash_liquor = bst.Stream("f2_wash_liquor", Water=0.0, units="kg/hr")
    condensate_to_wash = bst.Stream("condensate_to_wash", Water=0.0, units="kg/hr")
    # F1 (ash/residue cake) wash: the same ideas, settings in downstream.f1_washing.
    f1_cfg = _ATT_DOWNSTREAM["f1_washing"]
    f1_ratio = float(f1_cfg["wash_ratio_kg_per_kg_dry_cake"])
    condensate_to_f1_wash = bst.Stream("condensate_to_f1_wash", Water=0.0, units="kg/hr")

    # Clear F3 filtrate that the scrubber does not need (the waste lime paste brings its own water) joins the condensates.
    scrubber_excess = bst.Stream("scrubber_excess_water", Water=0.0, units="kg/hr")
    W3 = bst.Mixer(
        "W3",
        ins=(U3C - 1, ec1_condensate, scrubber_excess),
        outs=("condensate_pool",),
    )

    SW = bst.Splitter(
        "SW",
        ins=W3 - 0,
        outs=("condensate_to_D1", "condensate_surplus"),
        split=1.0,
    )

    @SW.add_specification(run=True)
    def send_condensate_to_dissolution():
        demand_kgph = dissolution_water_kg_per_kg_Na2CO3 * max(
            float(RC1.outs[0].imass["Na2CO3"]), 0.0
        )
        demand_kgph = max(demand_kgph - float(wash_liquor.imass["Water"]), 0.0)
        if spent_leachate is not None:
            demand_kgph = max(demand_kgph - float(spent_leachate.imass["Water"]), 0.0)
        pool_kgph = float(SW.ins[0].F_mass)
        SW.split = min(1.0, demand_kgph / pool_kgph) if pool_kgph > 0.0 else 1.0

    SX = bst.Splitter("SX", ins=SW - 1, outs=(condensate_to_wash, "condensate_surplus_f1"), split=0.0)

    @SX.add_specification(run=True)
    def send_surplus_to_wash():
        original = F2.outs[0]          # the cake of the previous iteration (F2 is defined below)
        demand_kgph = ratio * float(original.F_mass - original.imass["Water"])
        surplus_kgph = float(SX.ins[0].F_mass)
        SX.split = min(1.0, demand_kgph / surplus_kgph) if surplus_kgph > 0.0 else 0.0

    SY = bst.Splitter("SY", ins=SX - 1, outs=(condensate_to_f1_wash, "excess_condensate"), split=0.0)

    @SY.add_specification(run=True)
    def send_surplus_to_f1_wash():
        original = F1.outs[0]          # the cake of the previous iteration (F1 is defined below)
        demand_kgph = f1_ratio * float(original.F_mass - original.imass["Water"])
        surplus_kgph = float(SY.ins[0].F_mass)
        SY.split = min(1.0, demand_kgph / surplus_kgph) if surplus_kgph > 0.0 else 0.0

    spent_leachate = bst.Stream("spent_leachate", Water=0.0, units="kg/hr") if use_ree else None
    condensate_to_leach = bst.Stream("condensate_to_leach", Water=0.0, units="kg/hr") if use_ree else None
    SZ = None
    if use_ree:       # the condensate that nothing else needs is the water of the REE leach (clean water at about 52 C)
        SY.outs[1].ID = "condensate_surplus_leach"
        SZ = bst.Splitter("SZ", ins=SY - 1, outs=(condensate_to_leach, "excess_condensate"), split=0.0)

        @SZ.add_specification(run=True)
        def send_surplus_to_leach():
            cake = F1R.outs[0]          # the cake of the previous iteration (defined below)
            solids = sum(float(cake.imass[c.ID]) for c in cake.chemicals if c.ID not in ("Water", "Na2CO3", "NaOH", "NaCl", "KCl"))
            demand_kgph = LC1.water_demand_kgph(solids)
            surplus_kgph = float(SZ.ins[0].F_mass)
            SZ.split = min(1.0, demand_kgph / surplus_kgph) if surplus_kgph > 0.0 else 0.0

    D1 = bst.Mixer(
        "D1",
        ins=(
            RS1 - 0,
            SW - 0,
            dissolution_water,
            wash_liquor,
            *([spent_leachate] if spent_leachate is not None else []),
        ),
        outs=("dissolved_att_slurry",),
    )

    @D1.add_specification(run=True)
    def adjust_dissolution_water():
        att_residue = D1.ins[0]

        na2co3_kgph = max(
            float(att_residue.imass["Na2CO3"]),
            0.0,
        )
        demand_kgph = dissolution_water_kg_per_kg_Na2CO3 * na2co3_kgph
        recycled_water_kgph = float(wash_liquor.imass["Water"])
        if spent_leachate is not None:
            recycled_water_kgph += float(spent_leachate.imass["Water"])

        dissolution_water.empty()
        makeup_kgph = demand_kgph - float(D1.ins[1].F_mass) - recycled_water_kgph
        dissolution_water.imass["Water"] = makeup_kgph if makeup_kgph > 1e-6 else 0.0      # no roundoff dust

    # --------------------------------------------------------------
    # F1 - First filtration (native BioSTEAM PressureFilter)
    #
    # Insoluble ATT residue is retained in the cake. The retained liquid is modeled as MOTHER LIQUOR, not
    # pure water: Water, Na2CO3, and NaOH are entrained in the same
    # proportion as the surrounding liquid phase.
    #
    # The 30 wt% cake-moisture target is retained for F1. The fraction
    # of mother liquor entrained is solved dynamically each run so that
    # the native filter reaches this water fraction while preserving the
    # liquid-phase composition in the retained liquor.
    #
    # Native SolidsSeparator convention:
    #   outs[0] = retentate / cake
    #   outs[1] = permeate / filtrate
    # --------------------------------------------------------------
    mother_liquor_IDs = (
        "Water",
        "Na2CO3",
        "NaOH",
        "NaCl",
        "KCl",
    )
    filtration_solids_recovery = float(
        _ATT_DOWNSTREAM[
            "filtration_solids_recovery"
        ]
    )

    def make_initial_filter_split(chemicals):
        return {
            ID: (
                0.0
                if ID in mother_liquor_IDs
                else filtration_solids_recovery
            )
            for ID in chemicals.IDs
        }

    def add_mother_liquor_entrainment_spec(
        unit,
        target_cake_water_wt_frac,
        solids_recovery=filtration_solids_recovery,
    ):
        target = float(target_cake_water_wt_frac)

        @unit.add_specification(run=True)
        def adjust_mother_liquor_entrainment():
            feed = unit.ins[0]

            water_kgph = float(
                feed.imass["Water"]
            )
            dissolved_nonwater_kgph = sum(
                float(feed.imass[ID])
                for ID in mother_liquor_IDs
                if ID != "Water"
            )
            insoluble_feed_kgph = max(
                float(feed.F_mass)
                - water_kgph
                - dissolved_nonwater_kgph,
                0.0,
            )
            insoluble_solids_kgph = (
                solids_recovery
                * insoluble_feed_kgph
            )

            # If r is the fraction of mother liquor retained in the
            # cake, enforcing the target water fraction x gives:
            #
            #   x = r*W / [S + r*(W + D)]
            #
            # where W is liquid water, D is dissolved non-water solute,
            # and S is insoluble dry solids. Therefore:
            #
            #   r = x*S / [W - x*(W + D)]
            denominator = (
                water_kgph
                - target
                * (
                    water_kgph
                    + dissolved_nonwater_kgph
                )
            )

            if insoluble_solids_kgph <= 0.0:
                retained_liquor_fraction = 0.0
            elif denominator <= 0.0:
                raise ValueError(
                    f"{unit.ID}: target cake moisture cannot be "
                    "reached while retaining mother liquor at the "
                    "feed-liquid composition."
                )
            else:
                retained_liquor_fraction = (
                    target
                    * insoluble_solids_kgph
                    / denominator
                )

            # Zero-wash refiltration can give 1 + roundoff at identical moisture.
            if -1e-12 <= retained_liquor_fraction <= 1.0 + 1e-12:
                retained_liquor_fraction = min(1.0, max(0.0, retained_liquor_fraction))
            if not 0.0 <= retained_liquor_fraction <= 1.0:
                raise ValueError(
                    f"{unit.ID}: calculated mother-liquor retention "
                    f"fraction {retained_liquor_fraction:.6g} is "
                    "outside [0, 1]."
                )

            # Water split is handled by the native BioSTEAM moisture
            # specification. Dissolved solutes use the same retained
            # fraction so the cake liquid remains representative mother
            # liquor rather than pure water. All other components are
            # treated as insoluble solids and retained in the cake.
            for ID in feed.chemicals.IDs:
                if ID == "Water":
                    unit.isplit[ID] = 0.0
                elif ID in mother_liquor_IDs:
                    unit.isplit[ID] = (
                        retained_liquor_fraction
                    )
                else:
                    unit.isplit[ID] = (
                        solids_recovery
                    )

            unit._mother_liquor_retention_fraction = (
                retained_liquor_fraction
            )

    F1 = bst.PressureFilter(
        "F1",
        ins=D1 - 0,
        outs=(
            "att_char",
            "carbonate_solution",
        ),
        split=make_initial_filter_split(
            D1.outs[0].chemicals
        ),
        moisture_content=_ATT_DOWNSTREAM[
            "f1_cake_moisture_wt_frac"
        ],
    )

    add_mother_liquor_entrainment_spec(
        F1,
        _ATT_DOWNSTREAM[
            "f1_cake_moisture_wt_frac"
        ],
    )

    # --------------------------------------------------------------
    # F1 cake wash: the residue cake is re-slurried with condensate and fresh water in W1 and
    # refiltered in F1R at the F1 cake moisture; the wash liquor (dissolved Na2CO3 / NaOH of the cake moisture) is
    # combined with the F1 filtrate in MC, so it is causticized and its sodium is recovered. The cake is not dried.
    # --------------------------------------------------------------
    f1_moisture = float(_ATT_DOWNSTREAM["f1_cake_moisture_wt_frac"])
    F1.outs[0].ID = "att_char_unwashed"
    F1.outs[1].ID = "f1_filtrate"
    f1_wash_water = bst.Stream("f1_wash_water", Water=0.0, phase="l", T=float(f1_cfg["temperature_K"]))
    W1 = bst.MixTank("W1", ins=(F1 - 0, f1_wash_water, condensate_to_f1_wash),
                     outs=("f1_wash_slurry",), tau=float(f1_cfg["contact_time_h"]))

    @W1.add_specification(run=True)
    def adjust_f1_wash_feed():
        original = F1.outs[0]
        dry_cake = float(original.F_mass - original.imass["Water"])
        from_condensate = float(condensate_to_f1_wash.imass["Water"])
        f1_wash_water.empty()
        makeup = f1_ratio * dry_cake - from_condensate                                   # fresh makeup only
        f1_wash_water.imass["Water"] = makeup if makeup > 1e-6 else 0.0                 # no roundoff dust
        f1_wash_water.phase = "l"
        f1_wash_water.T = float(f1_cfg["temperature_K"])

    F1R = bst.PressureFilter(
        "F1R", ins=W1 - 0, outs=("att_char", "f1_wash_liquor"),
        split={ID: 0.0 if ID in mother_liquor_IDs else 1.0 for ID in F1.outs[0].chemicals.IDs},
        moisture_content=f1_moisture)
    add_mother_liquor_entrainment_spec(F1R, f1_moisture, solids_recovery=1.0)
    MC = bst.Mixer("MC", ins=(F1 - 1, F1R - 1), outs=("carbonate_solution",))
    carbonate_solution = MC - 0

    # LC1 / RO1 - REE recovery from the washed char cake (att.yaml downstream.ree_recovery): HCl leach and oxalate precipitation, then
    # the roast of the leached char and the oxalate into the REE product; the spent leachate goes to the dissolver D1.
    LC1 = RO1 = None
    if use_ree:
        att_char_unleached = F1R.outs[0]
        att_char_unleached.ID = "att_char_unleached"          # internal; the leached char leaves LC1 as att_char (the residue product)
        keys = ("hcl_mol_per_kg_char", "leach_liquor_kg_per_kg_char", "oxalic_mol_per_kg_char", "oxalate_solution_kg_per_kg_char",
                "cake_moisture_wt_frac", "leach_tau_h", "oxalate_tau_h", "wastewater_TREE_mg_per_L", "seaweed_dose_g_per_L",
                "overall_recovery", "product_REO_wt_frac", "REO_per_TREE", "REE_molar_mass", "oxalate_per_REE",
                "scale_reagents_with_REE", "hcl_mol_per_mol_REE", "reagent_excess", "precipitate_wash_efficiency")
        LC1 = ATTReeLeach(
            "LC1", ins=(att_char_unleached, bst.Stream("fresh_hcl"), bst.Stream("fresh_oxalic_acid"), bst.Stream("leach_water"),
                        bst.Stream("leachate_naoh"), condensate_to_leach),
            outs=("roaster_feed", spent_leachate, "att_char", "leach_co2"),
            dry_feed_kgph=lambda: sum(float(D0.outs[0].imass[ID]) for ID in _SARGASSUM_DRY_IDS), **{k: float(ree_cfg[k]) for k in keys})
        RO1 = ATTReeRoaster(
            "RO1", ins=(LC1 - 0, bst.Stream("roaster_air")), outs=("ree_product", "roaster_exhaust"),
            temperature_K=float(ree_cfg["roaster_temperature_K"]), excess_air=float(ree_cfg["roaster_excess_air"]),
            heat_loss_fraction=float(ree_cfg["roaster_heat_loss_fraction"]), area_m2_per_t_per_day=float(ree_cfg["roaster_area_m2_per_t_per_day"]),
            refractory_factor=float(ree_cfg["roaster_refractory_factor"]))

    # --------------------------------------------------------------
    # C1 - Causticization
    #
    # Na2CO3 + Ca(OH)2 -> 2 NaOH + CaCO3
    #
    # Ca(OH)2 requirement is calculated automatically.
    # --------------------------------------------------------------
    lime = bst.Stream("lime")
    C1 = CausticizationReactor(
        "C1",
        ins=(
            carbonate_solution,
            lime,
        ),
        outs=("causticized_slurry",),
        conversion=_ATT_DOWNSTREAM["causticization_conversion"],
        lime_equiv=_ATT_DOWNSTREAM["lime_equiv"],
        target_temperature_K=_ATT_DOWNSTREAM["causticization_temperature_K"],
    )

    # --------------------------------------------------------------
    # F2 - Second filtration (native BioSTEAM RotaryVacuumFilter)
    #
    # CaCO3 and residual Ca(OH)2 are retained as the mineral cake.
    # The 25 wt% cake-moisture target is retained. As in F1, cake liquid
    # is treated as entrained mother liquor, so NaOH and residual Na2CO3
    # leave with the cake in proportion to the retained liquid water.
    #
    # A pressure-filter alternative (12-14 wt% moisture in the reviewed
    # CaCO3 literature) can be evaluated later. The present baseline
    # intentionally avoids extra dewatering beyond the ~25 wt% target.
    # --------------------------------------------------------------
    F2 = bst.RotaryVacuumFilter(
        "F2",
        ins=C1 - 0,
        outs=(
            "caco3_cake",
            "naoh_carbonate_liquor",
        ),
        split=make_initial_filter_split(
            C1.outs[0].chemicals
        ),
        moisture_content=_ATT_DOWNSTREAM[
            "f2_cake_moisture_wt_frac"
        ],
    )

    add_mother_liquor_entrainment_spec(
        F2,
        _ATT_DOWNSTREAM[
            "f2_cake_moisture_wt_frac"
        ],
    )

    # --------------------------------------------------------------
    # F3 - dewatering filter of the CO2-scrubber slurry (same filter type and cake moisture as F2): the cake is
    # the disposed CaCO3 (smaller than the slurry), the filtrate is recycled to the scrubber.
    # --------------------------------------------------------------
    F3 = SF = None
    if SCRUB is not None:
        F3 = bst.RotaryVacuumFilter(
            "F3",
            ins=SCRUB - 1,
            outs=("scrubber_cake", "scrubber_filtrate_out"),
            split=make_initial_filter_split(SCRUB.outs[1].chemicals),
            moisture_content=_ATT_DOWNSTREAM["f2_cake_moisture_wt_frac"],
        )
        add_mother_liquor_entrainment_spec(F3, _ATT_DOWNSTREAM["f2_cake_moisture_wt_frac"])
        SF = bst.Splitter("SF", ins=F3 - 1, outs=(scrubber_filtrate, scrubber_excess), split=1.0)

        @SF.add_specification(run=True)
        def return_needed_filtrate():
            total = float(SF.ins[0].F_mass)
            SF.split = min(1.0, float(SCRUB.filtrate_demand_kgph) / total) if total > 0.0 else 1.0

    # Single mixed washing stage, followed by native refiltration.
    # Fresh water dilutes the original cake mother liquor. The refilter
    # retains representative diluted liquor at the configured cake moisture.
    # No Ca(OH)2 dissolution or arbitrary sodium-removal efficiency is imposed.
    F2.outs[0].ID = "f2_unwashed_cake"
    wash_water = bst.Stream("f2_wash_water", Water=0.0, phase="l",
                            T=float(wash_settings["temperature_K"]))
    W2 = bst.MixTank("W2", ins=(F2 - 0, wash_water, condensate_to_wash),
                     outs=("f2_wash_slurry",), tau=float(wash_settings["contact_time_h"]))

    @W2.add_specification(run=True)
    def adjust_wash_feed():
        original = F2.outs[0]
        dry_cake = float(original.F_mass - original.imass["Water"])
        from_condensate = float(condensate_to_wash.imass["Water"])
        wash_water.empty()
        makeup = ratio * dry_cake - from_condensate                                      # fresh makeup only
        wash_water.imass["Water"] = makeup if makeup > 1e-6 else 0.0                    # no roundoff dust
        wash_water.phase = "l"
        wash_water.T = float(wash_settings["temperature_K"])

    F2R = bst.RotaryVacuumFilter(
        "F2R", ins=W2 - 0, outs=("caco3_cake", wash_liquor),
        split={ID: 0.0 if ID in mother_liquor_IDs else 1.0 for ID in F2.outs[0].chemicals.IDs},
        moisture_content=float(_ATT_DOWNSTREAM["f2_cake_moisture_wt_frac"]))
    add_mother_liquor_entrainment_spec(
        F2R, _ATT_DOWNSTREAM["f2_cake_moisture_wt_frac"], solids_recovery=1.0)

    # --------------------------------------------------------------
    # D2 / D3 - drying of the two CaCO3 cakes before sale (att.yaml downstream.caco3_drying): the same ATT drum dryer
    # as D0, steam heated, drying air sized for the exhaust relative humidity, the dryer settings of feed_preparation.
    # The cakes keep the IDs caco3_cake and scrubber_cake (the sold streams); the filter outlets become *_wet.
    # --------------------------------------------------------------
    dry_cfg = _ATT_DOWNSTREAM["caco3_drying"]

    def cake_dryer(ID, cake, air_ID, product_ID):
        wet_ID = product_ID + "_wet"
        cake.ID = wet_ID
        return ATTDrumDryer(
            ID, ins=(cake, bst.Stream(air_ID), bst.Stream(air_ID.replace("_air", "_backup_fuel"))),
            outs=(product_ID, air_ID.replace("_air", "_exhaust"), air_ID.replace("_air", "_emissions")),
            split={"Water": 1.0}, moisture_content=float(dry_cfg["product_moisture_wt_frac"]),
            T=_ATT_FEED_PREP["dryer_temperature_K"], P=101325.0, utility_agent="Steam",
            RH=float(_dryer_cfg["exhaust_relative_humidity"]),
            length_to_diameter=float(_dryer_cfg["drum_length_to_diameter"]),
            max_drum_diameter_m=float(_dryer_cfg["max_drum_diameter_m"]))

    D2 = cake_dryer("D2", F2R.outs[0], "caco3_dryer_air", "caco3_cake")
    D3 = cake_dryer("D3", F3.outs[0], "scrubber_dryer_air", "scrubber_cake") if F3 is not None else None

    # The original F2 filtrate and NaOH loop are unchanged. The wash liquor is recycled to the dissolver D1;
    # it is never routed to EC1.
    sp1_feed = F2 - 1

    # --------------------------------------------------------------
    # SP1 - Whole-liquor purge / recycle split
    #
    # The earlier model selectively recycled NaOH + water while sending
    # all residual Na2CO3 to purge. That separation had no defined
    # physical basis.
    #
    # The revised baseline uses BioSTEAM's native Splitter and applies
    # the same split to every dissolved component. The reported 95%
    # NaOH recycling value is provisionally interpreted as 95% of the
    # whole filtrate liquor recycled and 5% purged.
    #
    # This gives residual Na2CO3 a real system outlet and allows its
    # recycle concentration to be determined by steady-state convergence.
    # --------------------------------------------------------------
    liquor_recycle_fraction = float(_ATT_DOWNSTREAM["whole_liquor_recycle_fraction"])
    if not 0.0 < liquor_recycle_fraction < 1.0:
        raise ValueError("SP1 recycle fraction must be strictly between 0 and 1")

    SP1 = bst.Splitter(
        "SP1",
        ins=sp1_feed,
        outs=(
            "liquor_to_concentrator",
            "liquor_purge",
        ),
        split=liquor_recycle_fraction,
    )

    # --------------------------------------------------------------
    # Gross NaOH requirement (1 kg NaOH / kg DRY Sargassum)
    #
    # Dry Sargassum = the feedstock solids of the D0 outlet (the same
    # species U2 counts as dry feed, ash included). D0 is upstream of M1,
    # so no recycle liquor, fresh NaOH or other process chemical is in it.
    # --------------------------------------------------------------
    def required_gross_naoh_kgph():
        conditioned_sargassum = D0.outs[0]
        dry_feed_kgph = sum(
            float(conditioned_sargassum.imass[ID])
            for ID in _SARGASSUM_DRY_IDS
            if ID in conditioned_sargassum.chemicals
        )
        return naoh_kg_per_kg_dry * dry_feed_kgph

    # --------------------------------------------------------------
    # EC1 - Recycle-liquor evaporator (single effect, vacuum, 90 C)
    #
    # Only the water in excess of what the target concentration allows
    # after the fresh NaOH makeup (added in M1) is evaporated:
    #
    #     water_max = gross NaOH * (1 - x) / x,   x = NaOH/(NaOH + H2O)
    #
    # No evaporation if the liquor already holds less water. EC1 is a simple
    # model: latent-heat duty, constant boiling-point elevation and a fixed
    # dissolved fraction of Na2CO3 (att.yaml downstream.ec1_*).
    # --------------------------------------------------------------
    if _ATT_DOWNSTREAM["recycle_naoh_concentration_basis"] != "naoh_plus_water":
        raise ValueError(
            "EC1 requires recycle_naoh_concentration_basis='naoh_plus_water'."
        )
    target_naoh_wt_frac = float(_ATT_DOWNSTREAM["recycle_naoh_wt_frac"])

    ec1_T = float(_ATT_DOWNSTREAM["concentration_temperature_K"])
    EC1 = NaOHEvaporator(
        "EC1",
        ins=SP1 - 0,
        outs=("ec1_concentrate", ec1_condensate),
        T=ec1_T,
        heat_loss_fraction=_ATT_DOWNSTREAM["heat_loss_fraction"],
    )

    @EC1.add_specification(run=True)
    def set_ec1_water_limit():
        EC1.max_water_kgph = (
            required_gross_naoh_kgph()
            * (1.0 - target_naoh_wt_frac)
            / target_naoh_wt_frac
        )

    # XL1 - salt crystallizer on the EC1 concentrate: the NaCl and KCl of the seaweed ash leave as a salt cake; the clarified liquor
    # is the NaOH recycle.
    XL1 = ATTSaltCrystallizer(
        "XL1", ins=EC1 - 0, outs=(naoh_recycle, "salt_cake"), removal=float(salt_cfg["removal_fraction"]),
        cake_liquor_wt_frac=float(salt_cfg["cake_liquor_wt_frac"]), tau_h=float(salt_cfg["vessel_tau_h"]))

    # --------------------------------------------------------------
    # System
    # --------------------------------------------------------------
    path = [
        D0,
        M1,
        U2,
        U3HX,
        U3C,
        *([SCRUB, F3, SF] if SCRUB is not None else []),
        *([D3] if D3 is not None else []),
        U3D,
        U3K,
        *([U3P, U3V] if psa else []),
        RC1,
        RS1,
        W3,
        SW,
        SX,
        SY,
        *([SZ] if SZ is not None else []),
        D1,
        F1,
        W1,
        F1R,
        MC,
        *([LC1, RO1] if LC1 is not None else []),
        C1,
        F2,
        W2,
        F2R,
        D2,
        SP1,
        EC1,
        XL1,
    ]

    # Not matched: the fired heaters of U2 and the REE roaster (fuel-fired, no process stream pair) and the solids
    # cooler RC1. The HXN flashes every stream it matches and RC1's stream is all solid (no boiling point), so it
    # fails; a water proxy would misstate a 500 -> 90 C sensible duty. Its 1.6 MW is cooled with cooling water.
    HXN = bst.HeatExchangerNetwork(
        "HXN", T_min_app=float(_ATT_HEAT_RECOVERY["minimum_approach_temperature_K"]),
        ignored=[U2, RC1, *([RO1] if RO1 is not None else [])])

    sys = bst.System(
        "att_sys",
        path=path,
        recycle=(naoh_recycle, ec1_condensate, tail_gas_fuel, *([scrubber_filtrate] if SCRUB is not None else []), wash_liquor, condensate_to_wash, condensate_to_f1_wash, *([spent_leachate, condensate_to_leach] if spent_leachate is not None else [])),
        # The makeup/concentration specification is nonlinear.
        # Aitken acceleration can overshoot to nonphysical intermediate
        # recycle compositions (e.g., too little water at F1), so use the
        # unaccelerated fixed-point method for robust positive-flow
        # convergence.
        method="fixedpoint",
        # The tear stream is the EC1 concentrate (recovered NaOH only); the
        # fresh NaOH makeup in M1 closes the loop. BioSTEAM's default
        # tolerances (1 kmol/h, 1 %) are far too loose at the 1 kg/h basis
        # and would stop the iteration before the makeup has converged.
        molar_tolerance=1e-9,
        relative_molar_tolerance=1e-7,
        facilities=(HXN,),
    )

    return sys
