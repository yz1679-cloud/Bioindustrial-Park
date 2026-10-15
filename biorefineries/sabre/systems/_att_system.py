import biosteam as bst

from biorefineries.sabre._chemicals import create_chemicals
from biorefineries.sabre.utils import (
    make_sargassum_feed,
    load_assumptions,
    get_feedstock_type_params,
)
from biorefineries.sabre.analyses.att.mass_energy import wash_balance
from biorefineries.sabre.units._att import (
    ATTReactor,
    CausticizationReactor,
    NaOHEvaporator,
    NaOHMakeupMixer,
    ATTHeatRecovery,
    aqueous_naoh_enthalpy_correction_kJph,
)

__all__ = ("create_att_system",)

_ATT_DATA = load_assumptions("att.yaml")["att"]
_FEEDSTOCK_DATA = load_assumptions("feedstock.yaml")

_ATT_FEED_PREP = _ATT_DATA["feed_preparation"]
_ATT = _ATT_DATA["reactor"]
_ATT_U3 = _ATT_DATA["gas_treatment"]
_ATT_DOWNSTREAM = _ATT_DATA["downstream"]
if "heat_recovery" not in _ATT_DATA:
    raise KeyError(
        "Missing 'att.heat_recovery' in biorefineries/sabre/data/att.yaml. "
        "Install the Step 6 data file as data/att.yaml (not under a versioned filename)."
    )
_ATT_HEAT_RECOVERY = _ATT_DATA["heat_recovery"]

def create_att_system(
    dry_sargassum_kgph=1.0,
    att_case=None,
    f2_wash_enabled=None,
    f2_wash_ratio=None,
    liquor_recycle_fraction=None,
    ec1_temperature_K=None,
    heat_integration=False,
    u2_gas_closure=None,
):
    """
    Build the alkaline thermal treatment (ATT) process.

    Parameters
    ----------
    dry_sargassum_kgph : float
        Dry-Sargassum scaling basis [kg dry solids/h]. The actual inlet
        stream is constructed from the default SaBRe wet-feed composition
        and therefore has a larger wet mass flow.
    att_case : str or None
        ATT process case. None selects the baseline case defined in
        data/att.yaml (currently Ni-CatATT).
    u2_gas_closure : str or None
        U2 gas closure: 'uniform_redox_scaling' (baseline, Gas-C),
        'h2_priority', 'experimental_fixed', 'uniform_co2_free' (Gas-Cprime)
        or 'h2_measured_ch4_max' (Gas-A). None uses att.yaml
        reactor.material_balance.gas_closure_method.
    f2_wash_enabled : bool or None
        Add the W2 F2-cake washer. None uses att.yaml downstream.f2_washing.
    f2_wash_ratio : float or None
        W2 wash water [kg/kg dry cake]. None uses att.yaml.
    liquor_recycle_fraction : float or None
        SP1 whole-liquor recycle fraction. None uses att.yaml.
    ec1_temperature_K : float or None
        EC1 boiling temperature for OPTIMIZATION SCENARIOS. None keeps the
        baseline (att.yaml concentration_temperature_K, 90 C). Any other
        value extrapolates the 90 C Na2CO3 solubility data (flagged).
    heat_integration : bool
        OPTIONAL SCENARIO: add the ATTHeatRecovery facility, which credits
        only temperature-verified heat-exchanger matches (D0 not integrated).
        False (default) is the baseline without heat recovery.

    Returns
    -------
    sys : bst.System
        ATT process system.
    """

    # --------------------------------------------------------------
    # Thermodynamic property package
    # --------------------------------------------------------------
    try:
        bst.settings.get_chemicals()
    except Exception:
        create_chemicals()

    # --------------------------------------------------------------
    # ATT case selection
    # --------------------------------------------------------------
    if att_case is None:
        att_case = _ATT["baseline_case"]

    cases = _ATT["cases"]
    if att_case not in cases:
        raise KeyError(
            f"Unknown ATT case '{att_case}'. "
            f"Available cases: {tuple(cases)}"
        )

    att_case_data = cases[att_case]

    # --------------------------------------------------------------
    # Raw Sargassum feed - use the default SaBRe composition.
    #
    # Do not override moisture or ash with ATT-specific values here.
    # dry_sargassum_kgph is retained only as a convenient dry-solids
    # scaling basis.
    # --------------------------------------------------------------
    feedstock_type = _ATT_FEED_PREP["feedstock_type"]
    feed_params = get_feedstock_type_params(
        _FEEDSTOCK_DATA,
        feedstock_type,
    )

    raw_moisture_frac = float(
        feed_params["moisture_frac"]
    )
    raw_ash_wt_frac_dry = float(
        feed_params["ash_wt_frac_dry"]
    )

    fresh_feed_kgph = (
        dry_sargassum_kgph
        / (1.0 - raw_moisture_frac)
    )

    raw_feed = make_sargassum_feed(
        fresh_feed_kgph=fresh_feed_kgph,
        moisture_frac=raw_moisture_frac,
        ash_wt_frac_dry=raw_ash_wt_frac_dry,
    )

    raw_feed.ID = "att_sargassum_feed"

    # --------------------------------------------------------------
    # P1 - Mechanical dewatering before ATT.
    #
    # Use BioSTEAM's native ScrewPress so that power/design/cost
    # correlations remain available for later TEA work.
    #
    # The press-cake moisture is a fallback assumption from the
    # current ATT modeling notes (75 wt% until a stronger literature
    # basis is identified).
    # --------------------------------------------------------------
    press_split = {
        ID: 1.0
        for ID in raw_feed.chemicals.IDs
        if ID != "Water"
    }

    P1 = bst.ScrewPress(
        "P1",
        ins=raw_feed,
        outs=(
            "pressed_sargassum",
            "press_liquid",
        ),
        split=press_split,
        moisture_content=_ATT_FEED_PREP[
            "press_cake_moisture_wt_frac"
        ],
    )

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

    D0 = bst.DrumDryer(
        "D0",
        ins=(
            P1 - 0,
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
    )

    # --------------------------------------------------------------
    # ATT NaOH requirement
    #
    # Advisor-confirmed Ni-CatATT baseline:
    #
    #     1 g NaOH / 0.5 g daf seaweed
    #   = 2 kg NaOH / kg daf seaweed
    #
    # The daf flow is calculated from the actual SaBRe feed reaching
    # M1, so the model continues to use the SaBRe default ash fraction.
    # Reported gas yields are handled separately in U2 and are not
    # rescaled when this NaOH loading is applied.
    # --------------------------------------------------------------
    naoh_kg_per_kg_daf = float(
        att_case_data[
            "naoh_kg_per_kg_daf"
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
    # With solid NaOH makeup located downstream of U2, an exactly empty
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
    initial_daf_kgph = (
        dry_sargassum_kgph
        * (1.0 - raw_ash_wt_frac_dry)
    )
    initial_naoh_kgph = (
        naoh_kg_per_kg_daf
        * initial_daf_kgph
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
    # The recycle liquor (M2 outlet) already contains both recovered
    # NaOH and the required fresh SOLID NaOH makeup. M1 therefore only
    # combines the conditioned Sargassum with this recycle liquor.
    # --------------------------------------------------------------
    M1 = bst.Mixer(
        "M1",
        ins=(
            D0 - 0,
            naoh_recycle,
        ),
        outs=("att_feed",),
    )

    # M1 is adiabatic, so the true U2 feed enthalpy is ThermoSTEAM's value
    # plus the electrolyte correction of the NaOH(aq) recycle liquor
    # (ThermoSTEAM treats dissolved NaOH as subcooled molten NaOH).
    @M1.add_specification(run=True)
    def set_u2_aqueous_naoh_correction():
        U2.aqueous_feed_enthalpy_correction_kJph = (
            aqueous_naoh_enthalpy_correction_kJph(naoh_recycle)
        )

    # --------------------------------------------------------------
    # U2 - ATT reactor
    # --------------------------------------------------------------
    U2 = ATTReactor(
        "U2",
        ins=M1 - 0,
        outs=(
            "att_gas",
            "att_residue",
        ),
        case_name=att_case,
        gas_closure_method=u2_gas_closure,
    )

    # --------------------------------------------------------------
    # U3 - ATT gas treatment train
    #
    # Current Step 7.5 sequence:
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
    # We keep the same reduced-order material specification used in Step 7.5:
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

    U3D = bst.MolecularSieve(
        "U3D",
        ins=U3C - 0,
        outs=(
            "u3_dry_gas",
            "u3_dryer_removed_water",
        ),
        split=dryer_split,
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

    U3P = bst.Splitter(
        "U3P",
        ins=U3D - 0,
        outs=(
            "u3_raw_h2_product",
            "u3_tail_gas",
        ),
        split=psa_split,
    )

    # U3K - Native BioSTEAM H2 product compressor.
    # Product pressure/efficiency are provisional and live in att.yaml.
    U3K = bst.units.IsothermalCompressor(
        "U3K",
        ins=U3P - 0,
        outs=("h2_product",),
        P=float(
            _ATT_U3["h2_product_pressure_Pa"]
        ),
        eta=float(
            _ATT_U3[
                "h2_compressor_efficiency"
            ]
        ),
        vle=False,
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
    )

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
    dissolution_water = bst.Stream(
        "dissolution_water",
        Water=0.0,
        units="kg/hr",
    )

    D1 = bst.Mixer(
        "D1",
        ins=(
            RC1 - 0,
            dissolution_water,
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

        dissolution_water.empty()
        dissolution_water.imass["Water"] = (
            _ATT_DOWNSTREAM[
                "dissolution_water_kg_per_kg_Na2CO3"
            ]
            * na2co3_kgph
        )

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
                filtration_solids_recovery
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

            if not (
                0.0
                <= retained_liquor_fraction
                <= 1.0
            ):
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
                        filtration_solids_recovery
                    )

            unit._mother_liquor_retention_fraction = (
                retained_liquor_fraction
            )

    F1 = bst.PressureFilter(
        "F1",
        ins=D1 - 0,
        outs=(
            "ash_residue_cake",
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
            F1 - 1,
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
    # W2 - Optional F2 cake washer. Material-only engineering scenario.
    # BOTH cake and filtrate enter W2, so recovered solutes flow to SP1.
    # In the wash-enabled case, the unwashed F2 cake is not the final cake.
    # --------------------------------------------------------------
    wash_settings = _ATT_DOWNSTREAM.get("f2_washing", {})
    wash_enabled = (
        bool(wash_settings.get("enabled", False))
        if f2_wash_enabled is None
        else bool(f2_wash_enabled)
    )
    if f2_wash_ratio is None:
        f2_wash_ratio = wash_settings.get("wash_ratio_kg_per_kg_dry_cake", 1.0)
    f2_wash_ratio = float(f2_wash_ratio)
    if f2_wash_ratio < 0:
        raise ValueError("F2 washing ratio must be nonnegative")
    if wash_enabled:
        f2_dry_ids = tuple(ID for ID in C1.outs[0].chemicals.IDs
                           if ID not in ("Water", "NaOH", "Na2CO3"))
        wash_water = bst.Stream("f2_wash_water", Water=0.0, phase="l",
                                T=float(wash_settings.get("temperature_K", 363.15)))

        class F2CakeWasher(bst.Unit):
            _N_ins = 3
            _N_outs = 2
            def _run(self):
                original_cake, original_filtrate, wash = self.ins
                cake, liquor = self.outs
                cake.copy_like(original_cake)
                liquor.copy_like(original_filtrate)
                dry_mass=sum(float(original_cake.imass[ID]) for ID in f2_dry_ids)
                wash_mass=float(wash.imass["Water"])
                result=wash_balance(
                    dry_insolubles=dry_mass,
                    retained_water=float(original_cake.imass["Water"]),
                    retained_naoh=float(original_cake.imass["NaOH"]),
                    retained_na2co3=float(original_cake.imass["Na2CO3"]),
                    filtrate_water=float(original_filtrate.imass["Water"]),
                    filtrate_naoh=float(original_filtrate.imass["NaOH"]),
                    filtrate_na2co3=float(original_filtrate.imass["Na2CO3"]),
                    wash_water=wash_mass,
                    target_moisture=float(_ATT_DOWNSTREAM["f2_cake_moisture_wt_frac"]),
                    displacement_factor=float(wash_settings.get("displacement_factor", 1.0)),
                )
                for ID in ("Water", "NaOH", "Na2CO3"):
                    cake.imass[ID]=result["cake"][ID]
                    liquor.imass[ID]=result["filtrate"][ID]
                self._wash_audit=result
                # Thermal enthalpy of washing and temperature mixing NOT modeled.
                # No fabricated heating or cooling credits are assigned.

        W2=F2CakeWasher("W2", ins=(F2-0, F2-1, wash_water),
                        outs=("caco3_cake_washed", "naoh_carbonate_liquor_washed"))
        @W2.add_specification(run=True)
        def adjust_wash_feed():
            unwashed_cake=W2.ins[0]
            dry_kgph=max(0.0, float(unwashed_cake.F_mass)
                       -sum(float(unwashed_cake.imass[ID])
                            for ID in ("Water", "NaOH", "Na2CO3")))
            wash_water.empty()
            wash_water.imass["Water"]=f2_wash_ratio*dry_kgph
            wash_water.phase="l"
            wash_water.T=float(wash_settings.get("temperature_K", 363.15))
        sp1_feed=W2-1
    else:
        W2=None
        sp1_feed=F2-1

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
    if liquor_recycle_fraction is None:
        liquor_recycle_fraction = _ATT_DOWNSTREAM["whole_liquor_recycle_fraction"]
    liquor_recycle_fraction = float(liquor_recycle_fraction)
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
    # Gross NaOH requirement (advisor-confirmed 2 kg NaOH/kg daf)
    # --------------------------------------------------------------
    def required_gross_naoh_kgph():
        conditioned_sargassum = D0.outs[0]
        dry_feed_kgph = (
            float(conditioned_sargassum.F_mass)
            - float(conditioned_sargassum.imass["Water"])
        )
        daf_feed_kgph = max(
            dry_feed_kgph - float(conditioned_sargassum.imass["Ash"]),
            0.0,
        )
        return naoh_kg_per_kg_daf * daf_feed_kgph

    # --------------------------------------------------------------
    # EC1 - Recycle-liquor evaporator (single effect, vacuum, 90 C)
    #
    # Only the water in excess of what the target concentration allows
    # after the M2 makeup is evaporated:
    #
    #     water_max = gross NaOH * (1 - x) / x,   x = NaOH/(NaOH + H2O)
    #
    # No evaporation if the liquor already holds less water. Boiling
    # pressure, duty and Na2CO3 salting-out use the NaOH(aq) property
    # model (biorefineries.sabre._naoh_properties).
    # --------------------------------------------------------------
    if _ATT_DOWNSTREAM["recycle_naoh_concentration_basis"] != "naoh_plus_water":
        raise ValueError(
            "EC1 requires recycle_naoh_concentration_basis='naoh_plus_water'."
        )
    target_naoh_wt_frac = float(_ATT_DOWNSTREAM["recycle_naoh_wt_frac"])

    baseline_ec1_T = float(_ATT_DOWNSTREAM["concentration_temperature_K"])
    ec1_T = baseline_ec1_T if ec1_temperature_K is None else float(ec1_temperature_K)
    EC1 = NaOHEvaporator(
        "EC1",
        ins=SP1 - 0,
        outs=("ec1_concentrate", "ec1_condensate"),
        T=ec1_T,
        heat_loss_fraction=_ATT_DOWNSTREAM["heat_loss_fraction"],
        allow_na2co3_solubility_extrapolation=abs(ec1_T - baseline_ec1_T) > 0.5,
    )
    EC1.is_baseline_temperature = abs(ec1_T - baseline_ec1_T) <= 0.5

    @EC1.add_specification(run=True)
    def set_ec1_water_limit():
        EC1.max_water_kgph = (
            required_gross_naoh_kgph()
            * (1.0 - target_naoh_wt_frac)
            / target_naoh_wt_frac
        )

    # --------------------------------------------------------------
    # M2 - Fresh solid-NaOH makeup, dissolved after EC1
    #
    # Fresh NaOH = gross requirement - NaOH recovered through SP1. No
    # water is added. The heat of solution warms the recycle liquor.
    # --------------------------------------------------------------
    M2 = NaOHMakeupMixer(
        "M2",
        ins=(EC1 - 0, fresh_naoh_solid),
        outs=naoh_recycle,
    )

    @M2.add_specification(run=True)
    def adjust_solid_naoh_makeup():
        required_naoh_kgph = required_gross_naoh_kgph()
        recovered_naoh_kgph = float(M2.ins[0].imass["NaOH"])
        fresh_naoh_kgph = max(required_naoh_kgph - recovered_naoh_kgph, 0.0)

        fresh_naoh_solid.empty()
        fresh_naoh_solid.imass["NaOH"] = fresh_naoh_kgph
        fresh_naoh_solid.phase = "s"
        fresh_naoh_solid.T = _ATT_FEED_PREP["fresh_naoh_temperature_K"]
        fresh_naoh_solid.P = 101325.0

        M2._required_gross_naoh_kgph = required_naoh_kgph
        M2._recovered_naoh_kgph = recovered_naoh_kgph
        M2._fresh_naoh_makeup_kgph = fresh_naoh_kgph

    # --------------------------------------------------------------
    # System
    # --------------------------------------------------------------
    path = [
        P1,
        D0,
        M1,
        U2,
        U3HX,
        U3C,
        U3D,
        U3P,
        U3K,
        RC1,
        D1,
        F1,
        C1,
        F2,
        *([W2] if W2 is not None else []),
        SP1,
        EC1,
        M2,
    ]

    HXR = ATTHeatRecovery("HXR") if heat_integration else None

    sys = bst.System(
        "att_sys",
        path=path,
        recycle=naoh_recycle,
        # Step 7.4 adds a nonlinear makeup/concentration specification.
        # Aitken acceleration can overshoot to nonphysical intermediate
        # recycle compositions (e.g., too little water at F1), so use the
        # unaccelerated fixed-point method for robust positive-flow
        # convergence.
        method="fixedpoint",
        facilities=(HXR,) if heat_integration else (),
    )
    if heat_integration:
        HXR.att_system = sys

    return sys
