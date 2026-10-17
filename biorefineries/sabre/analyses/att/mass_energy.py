# Bioindustrial-Park: BioSTEAM's Premier Biorefinery Models and Results
# Copyright (C) 2026-, Yu Zhou,
#                      Yalin Li <mailto.yalin.li@gmail.com>
#
# This module is under the UIUC open-source license. See
# github.com/BioSTEAMDevelopmentGroup/biosteam/blob/master/LICENSE.txt
# for license details.

"""ATT mass and energy accounting.

Energy accounting helpers for the SaBRe ATT flowsheet are analysis/reporting
logic only; process construction remains in systems/_att_system.py.
ATT physical-heat and gas-product chemical-energy diagnostics are reported
explicitly. Step 6.4 provides a non-invasive energy-consistency audit.
Step 6.5 adds a non-invasive standard-state reaction-enthalpy consistency
audit based on the current balanced Ni-CatATT flowsheet and ThermoSteam
Chemical.Hf values. No flowsheet changes are made by these helpers.

``wash_balance`` is the conservative mass-only filter-cake washing balance
called by the W2 washer in systems/_att_system.py (no equilibrium/heat
claims).
"""
import math

import biosteam as bst

from biorefineries.sabre.utils import load_assumptions

__all__ = (
    "get_att_energy_summary",
    "get_att_heat_recovery_summary",
    "get_att_energy_consistency_audit",
    "calculate_heat_source",
    "get_att_energy_source_summary",
    "get_att_recycle_summary",
    "get_att_u3_summary",
    "wash_balance",
)


# ==========================================================================
# Energy accounting
# ==========================================================================

def _units_of(sys):
    # Units of *this* system by ID; sys.flowsheet.unit is a shared registry
    # that is overwritten when another ATT system is built in the session.
    # Shared with heat_integration.
    from types import SimpleNamespace
    if not hasattr(sys, "units"):  # minimal test stand-ins
        return sys.flowsheet.unit
    return SimpleNamespace(**{unit.ID: unit for unit in (*sys.units, *getattr(sys, "facilities", ()))})


_ATT_DATA = load_assumptions(
    "att.yaml"
)["att"]

_ATT_ENERGY = _ATT_DATA[
    "energy_sources"
]

_ATT_U3 = _ATT_DATA[
    "gas_treatment"
]

_ATT_HEAT_RECOVERY = _ATT_DATA[
    "heat_recovery"
]

_ATT_FEED_ENERGY_REFERENCE = _ATT_DATA[
    "feed_energy_reference"
]

_ATT_DRYER = _ATT_DATA["feed_preparation"]["dryer"]


def _positive_heat_utility_kJph(unit):
    """Return total positive heat-utility duty for a simulated unit."""
    return sum(
        max(float(hu.duty), 0.0)
        for hu in unit.heat_utilities
    )



def _physical_heat_available_kJph(unit):
    """
    Return the process-stream enthalpy drop across a cooler [kJ/h].

    This is the theoretical physical heat released by the process stream.
    It is independent of any later assumption about how efficiently that
    heat can be recovered and reused.
    """
    inlet = unit.ins[0]
    outlet = unit.outs[0]
    return max(
        float(inlet.H - outlet.H),
        0.0,
    )


def _component_heating_values_kJph(
    stream,
    species,
):
    """
    Return component LHV/HHV contributions for selected gas species.

    Chemical LHV/HHV are stored by ThermoSteam in J/mol. Multiplication
    by stream flow in kmol/h is numerically equal to kJ/h.

    Absolute magnitudes are used because ThermoSteam database versions
    have historically differed in heating-value sign convention.
    """
    components = {}
    missing = []

    total_lhv = 0.0
    total_hhv = 0.0

    for ID in species:
        chemical = stream.chemicals[ID]
        mol_kmolph = float(
            stream.imol[ID]
        )

        LHV = chemical.LHV
        HHV = chemical.HHV

        if LHV is None or HHV is None:
            missing.append(ID)
            continue

        lhv_kJph = (
            abs(float(LHV))
            * mol_kmolph
        )
        hhv_kJph = (
            abs(float(HHV))
            * mol_kmolph
        )

        components[ID] = {
            "flow_kmolph":
                mol_kmolph,
            "LHV_kJph":
                lhv_kJph,
            "HHV_kJph":
                hhv_kJph,
        }

        total_lhv += lhv_kJph
        total_hhv += hhv_kJph

    return {
        "components":
            components,
        "missing_heating_value_species":
            tuple(missing),
        "LHV_kJph":
            total_lhv,
        "HHV_kJph":
            total_hhv,
    }


def get_att_heat_recovery_summary(sys):
    """
    Return current ATT heat and gas-energy diagnostics without applying credit.

    Current resolved interpretation
    -------------------------------
    * Only ATT residue is cooled from 500 C to 90 C before dissolution.
    * Hot U2 gas/steam is treated in the Step 7.5b U3 train.
    * U3HX performs the explicit U2-to-U3 cooling/partial condensation.
    * U3C performs equilibrium gas/liquid separation.
    * U3D is an ideal dryer placeholder.
    * U3P is an idealized PSA surrogate.
    * U3K compresses the H2 product.
    * H2 is a product and is not counted as process fuel.
    * PSA tail gas remains available for future combustion/heat recovery.

    Tail-gas combustion is not yet implemented, so no chemical-energy heat
    credit or net utility reduction is applied here.
    """
    u = _units_of(sys)

    dry_feed_kgph = float(
        u.U2._dry_sargassum_kgph
    )

    residue_physical_kJph = (
        _physical_heat_available_kJph(
            u.RC1
        )
    )

    # U3HX is now the explicit U2-to-U3 process cooler. Report its
    # process-stream enthalpy drop as physical heat available. This is not
    # yet counted as usable recovered heat; temperature-feasible heat
    # integration will be handled separately.
    gas_physical_kJph = (
        _physical_heat_available_kJph(
            u.U3HX
        )
    )

    gas = u.U2.outs[0]

    all_combustible_species = tuple(
        _ATT_HEAT_RECOVERY[
            "gas_energy_diagnostic_species"
        ]
    )
    h2_product_species = tuple(
        _ATT_HEAT_RECOVERY[
            "hydrogen_product_species"
        ]
    )
    future_tail_fuel_species = tuple(
        _ATT_HEAT_RECOVERY[
            "future_tail_gas_fuel_species"
        ]
    )

    total_combustible = _component_heating_values_kJph(
        gas,
        all_combustible_species,
    )
    h2_product = _component_heating_values_kJph(
        gas,
        h2_product_species,
    )
    future_tail_fuel = _component_heating_values_kJph(
        gas,
        future_tail_fuel_species,
    )

    def per_kg(value):
        return (
            float(value)
            / 1000.0
            / dry_feed_kgph
        )

    return {
        "dry_feed_kgph":
            dry_feed_kgph,

        "residue_cooling_target_temperature_K":
            float(
                _ATT_HEAT_RECOVERY[
                    "residue_cooling_target_temperature_K"
                ]
            ),

        "gas_path_status":
            _ATT_HEAT_RECOVERY[
                "gas_path_status"
            ],

        "future_U3_sequence":
            _ATT_HEAT_RECOVERY[
                "future_U3_sequence"
            ],

        "gas_physical_heat_available_kJph":
            gas_physical_kJph,
        "gas_physical_heat_status":
            "U3HX process-stream enthalpy drop; available physical heat only, no recovery credit applied",

        "residue_physical_heat_available_kJph":
            residue_physical_kJph,
        "total_physical_heat_available_kJph":
            gas_physical_kJph
            + residue_physical_kJph,
        "total_physical_heat_available_MJ_per_kg_dry":
            per_kg(
                gas_physical_kJph
                + residue_physical_kJph
            ),

        # Total combustible-gas diagnostic at U2 outlet.
        "gas_product_energy_species":
            all_combustible_species,
        "gas_product_energy_components":
            total_combustible["components"],
        "gas_product_missing_heating_values":
            total_combustible[
                "missing_heating_value_species"
            ],
        "gas_product_LHV_kJph":
            total_combustible["LHV_kJph"],
        "gas_product_HHV_kJph":
            total_combustible["HHV_kJph"],
        "gas_product_LHV_MJ_per_kg_dry":
            per_kg(
                total_combustible["LHV_kJph"]
            ),
        "gas_product_HHV_MJ_per_kg_dry":
            per_kg(
                total_combustible["HHV_kJph"]
            ),

        # H2 is a product, not an internal fuel.
        "H2_product_energy_species":
            h2_product_species,
        "H2_product_LHV_kJph":
            h2_product["LHV_kJph"],
        "H2_product_HHV_kJph":
            h2_product["HHV_kJph"],
        "H2_product_LHV_MJ_per_kg_dry":
            per_kg(
                h2_product["LHV_kJph"]
            ),
        "H2_product_HHV_MJ_per_kg_dry":
            per_kg(
                h2_product["HHV_kJph"]
            ),

        # CH4 + CO are future PSA-tail-gas fuel potential.
        # No combustion credit is applied before U3 is modeled.
        "future_tail_gas_fuel_species":
            future_tail_fuel_species,
        "future_tail_gas_LHV_kJph":
            future_tail_fuel["LHV_kJph"],
        "future_tail_gas_HHV_kJph":
            future_tail_fuel["HHV_kJph"],
        "future_tail_gas_LHV_MJ_per_kg_dry":
            per_kg(
                future_tail_fuel["LHV_kJph"]
            ),
        "future_tail_gas_HHV_MJ_per_kg_dry":
            per_kg(
                future_tail_fuel["HHV_kJph"]
            ),

        "hydrogen_disposition":
            _ATT_HEAT_RECOVERY[
                "hydrogen_disposition"
            ],
        "hydrogen_energy_credit_status":
            _ATT_HEAT_RECOVERY[
                "hydrogen_energy_credit_status"
            ],

        "heat_integration_method":
            _ATT_HEAT_RECOVERY[
                "integration_method"
            ],
        "minimum_approach_temperature_K":
            float(
                _ATT_HEAT_RECOVERY[
                    "minimum_approach_temperature_K"
                ]
            ),

        "usable_recovered_heat_kJph":
            None,
    }


def get_att_energy_summary(sys):
    """
    Return current gross ATT heat demands.

    Notes
    -----
    U2 process heat is thermodynamically calculated from the actual feed
    state. U2 utility heat includes the modeled heat-loss fraction.

    D0 is a native DrumDryer. Its positive heat utility is reported
    directly from BioSTEAM.

    C1 remains the current ATT-specific reaction implementation.
    EC1 is the NaOH(aq) vacuum evaporator; its duty is the latent heat of
    the evaporated water plus the 5% heat-loss factor.

    No ATT heat-recovery credit is applied in this function.
    """

    u = _units_of(sys)

    dry_feed_kgph = float(
        u.U2._dry_sargassum_kgph
    )

    d0_utility_kJph = (
        _positive_heat_utility_kJph(u.D0)
    )

    u2_process_kJph = float(
        u.U2._heat_duty_kJph
    )
    u2_heat_loss_kJph = float(
        u.U2._heat_loss_kJph
    )
    u2_utility_kJph = float(
        u.U2._utility_heat_duty_kJph
    )

    c1_process_kJph = float(
        u.C1._heat_duty_kJph
    )
    c1_heat_loss_kJph = float(
        u.C1._heat_loss_kJph
    )
    # Registered heat utility (reduced only in the optional heat-integration
    # scenario); C1._utility_heat_duty_kJph is the unintegrated value.
    c1_utility_kJph = _positive_heat_utility_kJph(u.C1)

    # EC1 vacuum evaporator: latent-heat duty plus heat loss.
    ec1_utility_kJph = (
        _positive_heat_utility_kJph(
            u.EC1
        )
    )
    ec1_process_kJph = max(float(u.EC1._heat_duty_kJph), 0.0)
    ec1_heat_loss_kJph = float(u.EC1._heat_loss_kJph)

    gross_utility_kJph = (
        d0_utility_kJph
        + u2_utility_kJph
        + c1_utility_kJph
        + ec1_utility_kJph
    )

    recovery = (
        get_att_heat_recovery_summary(
            sys
        )
    )

    return {
        "dry_feed_kgph":
            dry_feed_kgph,

        "D0_utility_heat_kJph":
            d0_utility_kJph,
        # D0 utility is an ASSUMED THERMAL DUTY (ideal heat balance), not
        # dryer-equipment performance; equipment heat input ranges below are
        # typical literature values and are not used in any utility.
        "D0_thermal_duty_basis":
            _ATT_DRYER["thermal_duty_basis"],
        "D0_water_evaporated_kgph":
            float(u.D0.outs[1].imass["Water"]),
        "D0_assumed_specific_thermal_duty_MJ_per_kg_water":
            (d0_utility_kJph / 1e3 / float(u.D0.outs[1].imass["Water"])
             if float(u.D0.outs[1].imass["Water"]) > 0.0 else 0.0),
        "D0_equipment_heat_input_range_kJph_NOT_USED":
            {
                kind: [lo * 1e3 * float(u.D0.outs[1].imass["Water"]),
                       hi * 1e3 * float(u.D0.outs[1].imass["Water"])]
                for kind, (lo, hi) in _ATT_DRYER[
                    "equipment_specific_energy_MJ_per_kg_water"
                ].items()
            },

        "U2_water_heating_evaporation_kJph":
            float(
                u.U2._water_heating_duty_kJph
            ),
        "U2_dry_sargassum_heating_kJph":
            float(
                u.U2._dry_sargassum_heating_duty_kJph
            ),
        "U2_NaOH_heating_kJph":
            float(
                u.U2._naoh_heating_duty_kJph
            ),
        "U2_process_heat_kJph":
            u2_process_kJph,
        "U2_heat_loss_kJph":
            u2_heat_loss_kJph,
        "U2_utility_heat_kJph":
            u2_utility_kJph,

        "C1_process_heat_kJph":
            c1_process_kJph,
        "C1_heat_loss_kJph":
            c1_heat_loss_kJph,
        "C1_utility_heat_kJph":
            c1_utility_kJph,

        "EC1_process_heat_kJph":
            ec1_process_kJph,
        "EC1_heat_loss_kJph":
            ec1_heat_loss_kJph,
        "EC1_utility_heat_kJph":
            ec1_utility_kJph,

        "gross_utility_heat_kJph_before_recovery":
            gross_utility_kJph,

        "gross_utility_heat_MJ_per_kg_dry_before_recovery":
            gross_utility_kJph
            / 1000.0
            / dry_feed_kgph,

        "physical_heat_available_kJph":
            recovery[
                "total_physical_heat_available_kJph"
            ],
        "physical_heat_available_MJ_per_kg_dry":
            recovery[
                "total_physical_heat_available_MJ_per_kg_dry"
            ],

        # Total chemical-energy diagnostic of modeled combustible
        # species at the U2 gas outlet.
        "gas_product_LHV_kJph":
            recovery[
                "gas_product_LHV_kJph"
            ],
        "gas_product_HHV_kJph":
            recovery[
                "gas_product_HHV_kJph"
            ],
        "gas_product_LHV_MJ_per_kg_dry":
            recovery[
                "gas_product_LHV_MJ_per_kg_dry"
            ],
        "gas_product_HHV_MJ_per_kg_dry":
            recovery[
                "gas_product_HHV_MJ_per_kg_dry"
            ],

        # H2 is treated as a product.
        "H2_product_LHV_kJph":
            recovery[
                "H2_product_LHV_kJph"
            ],
        "H2_product_HHV_kJph":
            recovery[
                "H2_product_HHV_kJph"
            ],
        "H2_product_LHV_MJ_per_kg_dry":
            recovery[
                "H2_product_LHV_MJ_per_kg_dry"
            ],
        "H2_product_HHV_MJ_per_kg_dry":
            recovery[
                "H2_product_HHV_MJ_per_kg_dry"
            ],

        # CH4 + CO are future U3/PSA tail-gas fuel potential.
        "future_tail_gas_LHV_kJph":
            recovery[
                "future_tail_gas_LHV_kJph"
            ],
        "future_tail_gas_HHV_kJph":
            recovery[
                "future_tail_gas_HHV_kJph"
            ],
        "future_tail_gas_LHV_MJ_per_kg_dry":
            recovery[
                "future_tail_gas_LHV_MJ_per_kg_dry"
            ],
        "future_tail_gas_HHV_MJ_per_kg_dry":
            recovery[
                "future_tail_gas_HHV_MJ_per_kg_dry"
            ],

        "usable_recovered_heat_kJph":
            None,
        "net_utility_heat_after_recovery_kJph":
            None,
    }



def get_att_energy_consistency_audit(sys):
    """
    Return a non-invasive ATT energy-consistency audit.

    This function does not change the flowsheet, unit specifications,
    heat utilities, recovery assumptions, or process streams. It only
    reads results from an already-simulated ATT system.

    The audit deliberately keeps the following quantities separate:

      1. provisional feed HHV reference,
      2. gross external/process heat demand,
      3. theoretical physical heat available from cooling,
      4. H2 product energy and future CH4/CO tail-gas fuel potential,
      5. usable recovered heat,
      6. net utility heat after recovery.

    Items 5 and 6 remain None until a validated heat-integration /
    combustion-recovery model is implemented.

    Notes
    -----
    In the current flowsheet:
      * C1 is the causticization reactor.
      * EC1 is the NaOH concentration unit.

    Therefore both C1 heat and EC1 concentration heat are reported
    separately to avoid conflating the two operations.
    """

    u = _units_of(sys)

    # Reuse the existing summaries so this audit does not duplicate or
    # alter any process calculations.
    energy = get_att_energy_summary(sys)
    recovery = get_att_heat_recovery_summary(sys)

    dry_feed_kgph = float(
        energy["dry_feed_kgph"]
    )

    if dry_feed_kgph <= 0.0:
        raise ValueError(
            "ATT dry-feed flow must be positive for energy audit."
        )

    # --------------------------------------------------------------
    # Feed HHV reference
    #
    # The current reference is expressed on a dry ash-free basis.
    # Convert it to the ACTUAL SaBRe dry-feed basis using the ash mass
    # that reaches U2; do not hard-code an ash fraction.
    # --------------------------------------------------------------
    feed_hhv_daf_MJ_per_kg = float(
        _ATT_FEED_ENERGY_REFERENCE[
            "HHV_MJ_per_kg_daf_baseline"
        ]
    )

    ash_kgph = float(
        u.U2.ins[0].imass["Ash"]
    )

    daf_feed_kgph = max(
        dry_feed_kgph - ash_kgph,
        0.0,
    )

    daf_fraction_dry = (
        daf_feed_kgph
        / dry_feed_kgph
    )

    feed_hhv_reference_MJph = (
        feed_hhv_daf_MJ_per_kg
        * daf_feed_kgph
    )

    feed_hhv_reference_MJ_per_kg_dry = (
        feed_hhv_reference_MJph
        / dry_feed_kgph
    )

    # --------------------------------------------------------------
    # Gross external heat demand
    # --------------------------------------------------------------
    d0_external_kJph = float(
        energy["D0_utility_heat_kJph"]
    )

    u2_water_kJph = float(
        energy[
            "U2_water_heating_evaporation_kJph"
        ]
    )
    u2_dry_sargassum_kJph = float(
        energy[
            "U2_dry_sargassum_heating_kJph"
        ]
    )
    u2_naoh_kJph = float(
        energy[
            "U2_NaOH_heating_kJph"
        ]
    )
    u2_process_kJph = float(
        energy["U2_process_heat_kJph"]
    )
    u2_loss_kJph = float(
        energy["U2_heat_loss_kJph"]
    )
    u2_external_kJph = float(
        energy["U2_utility_heat_kJph"]
    )

    # C1 = causticization; EC1 = concentration in the present model.
    c1_process_kJph = float(
        energy["C1_process_heat_kJph"]
    )
    c1_external_kJph = float(
        energy["C1_utility_heat_kJph"]
    )

    ec1_process_kJph = float(
        energy["EC1_process_heat_kJph"]
    )
    ec1_external_kJph = float(
        energy["EC1_utility_heat_kJph"]
    )

    gross_external_kJph = float(
        energy[
            "gross_utility_heat_kJph_before_recovery"
        ]
    )

    # --------------------------------------------------------------
    # Physical heat available from 500 C -> 90 C cooling
    # --------------------------------------------------------------
    gas_physical_kJph = recovery[
        "gas_physical_heat_available_kJph"
    ]
    residue_physical_kJph = float(
        recovery[
            "residue_physical_heat_available_kJph"
        ]
    )
    physical_available_kJph = float(
        recovery[
            "total_physical_heat_available_kJph"
        ]
    )

    # --------------------------------------------------------------
    # U2 gas chemical-energy diagnostics
    # --------------------------------------------------------------
    fuel_components = dict(
        recovery["gas_product_energy_components"]
    )

    component_energy = {}

    for ID, values in fuel_components.items():
        lhv_kJph = float(
            values["LHV_kJph"]
        )
        hhv_kJph = float(
            values["HHV_kJph"]
        )

        component_energy[ID] = {
            "flow_kmolph":
                float(values["flow_kmolph"]),
            "LHV_kJph":
                lhv_kJph,
            "HHV_kJph":
                hhv_kJph,
            "LHV_MJ_per_kg_dry":
                lhv_kJph
                / 1000.0
                / dry_feed_kgph,
            "HHV_MJ_per_kg_dry":
                hhv_kJph
                / 1000.0
                / dry_feed_kgph,
        }

    core_lhv_kJph = float(
        recovery["gas_product_LHV_kJph"]
    )
    core_hhv_kJph = float(
        recovery["gas_product_HHV_kJph"]
    )

    core_lhv_MJ_per_kg_dry = (
        core_lhv_kJph
        / 1000.0
        / dry_feed_kgph
    )
    core_hhv_MJ_per_kg_dry = (
        core_hhv_kJph
        / 1000.0
        / dry_feed_kgph
    )

    h2_product_lhv_MJ_per_kg_dry = float(
        recovery[
            "H2_product_LHV_MJ_per_kg_dry"
        ]
    )
    h2_product_hhv_MJ_per_kg_dry = float(
        recovery[
            "H2_product_HHV_MJ_per_kg_dry"
        ]
    )

    tail_fuel_lhv_MJ_per_kg_dry = float(
        recovery[
            "future_tail_gas_LHV_MJ_per_kg_dry"
        ]
    )
    tail_fuel_hhv_MJ_per_kg_dry = float(
        recovery[
            "future_tail_gas_HHV_MJ_per_kg_dry"
        ]
    )

    # --------------------------------------------------------------
    # Recovery / net-energy status
    # --------------------------------------------------------------
    usable_recovered_heat_kJph = (
        recovery["usable_recovered_heat_kJph"]
    )

    if usable_recovered_heat_kJph is None:
        usable_recovered_heat_MJ_per_kg_dry = None
        net_utility_after_recovery_kJph = None
        net_utility_after_recovery_MJ_per_kg_dry = None
    else:
        usable_recovered_heat_kJph = float(
            usable_recovered_heat_kJph
        )

        usable_recovered_heat_MJ_per_kg_dry = (
            usable_recovered_heat_kJph
            / 1000.0
            / dry_feed_kgph
        )

        net_utility_after_recovery_kJph = max(
            gross_external_kJph
            - usable_recovered_heat_kJph,
            0.0,
        )

        net_utility_after_recovery_MJ_per_kg_dry = (
            net_utility_after_recovery_kJph
            / 1000.0
            / dry_feed_kgph
        )

    # --------------------------------------------------------------
    # Consistency diagnostics only.
    #
    # Do NOT interpret a positive gas-LHV-minus-feed-HHV value as an
    # energy-balance violation by itself: the current U2 duty excludes
    # full reaction enthalpy and the ATT process receives external heat.
    # --------------------------------------------------------------
    gas_lhv_minus_feed_hhv_reference = (
        core_lhv_MJ_per_kg_dry
        - feed_hhv_reference_MJ_per_kg_dry
    )

    warnings = (
        "Feed HHV = 16.9 MJ/kg daf is a literature-based Excel reference, not a measured HHV for the modeled SaBRe feed.",
        "Current U2 heat duty includes feed heating/evaporation but not a complete reaction-enthalpy balance.",
        "Current physical heat available includes residue cooling only; U2 gas cooling is deferred to later U3 treatment.",
        "H2 is treated as a product. CH4/CO are only future PSA-tail-gas fuel potential; no combustion credit is applied before U3 is modeled.",
        "C1 is causticization; EC1 is the NaOH concentration unit in the current flowsheet.",
        "Net utility after recovery remains undefined until explicit heat integration/combustion recovery is modeled.",
    )

    return {
        "audit_type":
            "non-invasive energy-consistency audit",

        "dry_feed_kgph":
            dry_feed_kgph,

        # Feed-energy reference
        "feed_HHV_reference_status":
            _ATT_FEED_ENERGY_REFERENCE[
                "status"
            ],
        "feed_HHV_reference_MJ_per_kg_daf":
            feed_hhv_daf_MJ_per_kg,
        "actual_daf_fraction_of_dry_feed":
            daf_fraction_dry,
        "feed_HHV_reference_MJ_per_kg_dry":
            feed_hhv_reference_MJ_per_kg_dry,
        "feed_HHV_reference_MJph":
            feed_hhv_reference_MJph,

        # D0
        "D0_external_heat_kJph":
            d0_external_kJph,
        "D0_external_heat_MJ_per_kg_dry":
            d0_external_kJph
            / 1000.0
            / dry_feed_kgph,

        # U2
        "U2_water_heating_evaporation_kJph":
            u2_water_kJph,
        "U2_water_heating_evaporation_MJ_per_kg_dry":
            u2_water_kJph
            / 1000.0
            / dry_feed_kgph,
        "U2_dry_sargassum_heating_kJph":
            u2_dry_sargassum_kJph,
        "U2_NaOH_heating_kJph":
            u2_naoh_kJph,
        "U2_process_heat_kJph":
            u2_process_kJph,
        "U2_heat_loss_kJph":
            u2_loss_kJph,
        "U2_external_heat_kJph":
            u2_external_kJph,
        "U2_external_heat_MJ_per_kg_dry":
            u2_external_kJph
            / 1000.0
            / dry_feed_kgph,

        # Downstream heat
        "C1_causticization_process_heat_kJph":
            c1_process_kJph,
        "C1_causticization_external_heat_kJph":
            c1_external_kJph,
        "EC1_concentration_process_heat_kJph":
            ec1_process_kJph,
        "EC1_concentration_external_heat_kJph":
            ec1_external_kJph,
        "EC1_concentration_external_heat_MJ_per_kg_dry":
            ec1_external_kJph
            / 1000.0
            / dry_feed_kgph,

        # Gross external demand
        "gross_external_heat_before_recovery_kJph":
            gross_external_kJph,
        "gross_external_heat_before_recovery_MJ_per_kg_dry":
            gross_external_kJph
            / 1000.0
            / dry_feed_kgph,

        # Physical heat availability
        "gas_physical_heat_available_kJph":
            gas_physical_kJph,
        "residue_physical_heat_available_kJph":
            residue_physical_kJph,
        "physical_heat_available_kJph":
            physical_available_kJph,
        "physical_heat_available_MJ_per_kg_dry":
            physical_available_kJph
            / 1000.0
            / dry_feed_kgph,

        # Chemical-energy diagnostics
        "gas_product_energy_species":
            tuple(
                recovery["gas_product_energy_species"]
            ),
        "core_fuel_species":
            tuple(
                recovery["gas_product_energy_species"]
            ),
        "fuel_component_energy":
            component_energy,
        "total_combustible_gas_LHV_kJph":
            core_lhv_kJph,
        "total_combustible_gas_HHV_kJph":
            core_hhv_kJph,
        "total_combustible_gas_LHV_MJ_per_kg_dry":
            core_lhv_MJ_per_kg_dry,
        "total_combustible_gas_HHV_MJ_per_kg_dry":
            core_hhv_MJ_per_kg_dry,

        "H2_product_LHV_MJ_per_kg_dry":
            h2_product_lhv_MJ_per_kg_dry,
        "H2_product_HHV_MJ_per_kg_dry":
            h2_product_hhv_MJ_per_kg_dry,

        "future_tail_gas_LHV_MJ_per_kg_dry":
            tail_fuel_lhv_MJ_per_kg_dry,
        "future_tail_gas_HHV_MJ_per_kg_dry":
            tail_fuel_hhv_MJ_per_kg_dry,
        "missing_core_heating_values":
            tuple(
                recovery[
                    "gas_product_missing_heating_values"
                ]
            ),

        # Recovery status
        "usable_recovered_heat_kJph":
            usable_recovered_heat_kJph,
        "usable_recovered_heat_MJ_per_kg_dry":
            usable_recovered_heat_MJ_per_kg_dry,
        "net_utility_after_recovery_kJph":
            net_utility_after_recovery_kJph,
        "net_utility_after_recovery_MJ_per_kg_dry":
            net_utility_after_recovery_MJ_per_kg_dry,

        # Diagnostic comparison only
        "total_combustible_gas_LHV_minus_feed_HHV_reference_MJ_per_kg_dry":
            gas_lhv_minus_feed_hhv_reference,

        "hydrogen_disposition":
            recovery[
                "hydrogen_disposition"
            ],
        "gas_path_status":
            recovery[
                "gas_path_status"
            ],

        "heat_integration_method":
            recovery[
                "heat_integration_method"
            ],
        "minimum_approach_temperature_K":
            recovery[
                "minimum_approach_temperature_K"
            ],

        "warnings":
            warnings,
    }



def get_att_u3_summary(sys):
    """
    Return material/energy diagnostics for the Step 7.5 U3 gas-treatment train.

    Notes
    -----
    U3HX is a native BioSTEAM HXutility.
    U3C is a native BioSTEAM Flash.
    U3D is a native BioSTEAM MolecularSieve used for reduced-order gas dehydration.
    U3P is a native Splitter used as an idealized PSA surrogate.
    U3K is a native BioSTEAM IsothermalCompressor.

    PSA recovery, product pressure, compressor efficiency, and dryer
    performance are provisional assumptions stored in ``att.yaml``.
    Tail-gas combustion is not included in this step.
    """
    u = _units_of(sys)

    u2_gas = u.U2.outs[0]
    cooled_gas = u.U3HX.outs[0]
    wet_gas = u.U3C.outs[0]
    condensate = u.U3C.outs[1]
    dry_gas = u.U3D.outs[0]
    dryer_water = u.U3D.outs[1]
    h2_product = u.U3P.outs[0] if hasattr(u, "U3P") else u.U3K.outs[0]
    tail_gas = u.U3V.outs[0] if hasattr(u, "U3V") else bst.Stream(None, phase="g")      # no PSA: no tail gas

    def mass(stream, ID):
        return float(stream.imass[ID])

    def mol(stream, ID):
        return float(stream.imol[ID])

    h2_in = mol(dry_gas, "H2")
    h2_product_mol = mol(h2_product, "H2")
    actual_h2_recovery = (
        h2_product_mol / h2_in
        if h2_in > 0.0
        else 0.0
    )

    product_total_mol = float(h2_product.F_mol)
    h2_mol_purity = (
        h2_product_mol / product_total_mol
        if product_total_mol > 0.0
        else 0.0
    )

    hx_physical_heat_kJph = (
        _physical_heat_available_kJph(
            u.U3HX
        )
    )

    flash_net_heat_kJph = sum(
        float(hu.duty)
        for hu in u.U3C.heat_utilities
    )
    flash_cooling_kJph = max(
        -flash_net_heat_kJph,
        0.0,
    )

    compressor_power_kW = float(
        u.U3K.power_utility.rate
    )

    dryer_power_kW = float(
        u.U3D.power_utility.rate
    )
    dryer_heating_kJph = (
        _positive_heat_utility_kJph(
            u.U3D
        )
    )
    dryer_cooling_kJph = sum(
        max(-float(hu.duty), 0.0)
        for hu in u.U3D.heat_utilities
    )

    tail_energy = _component_heating_values_kJph(
        tail_gas,
        ("H2", "CH4", "CO"),
    )

    return {
        "U2_hot_gas_total_kgph":
            float(u2_gas.F_mass),
        "U2_hot_gas_water_kgph":
            mass(u2_gas, "Water"),

        "U3HX_unit_type":
            type(u.U3HX).__name__,
        "U3HX_outlet_temperature_K":
            float(cooled_gas.T),
        "U3HX_physical_heat_available_kJph":
            hx_physical_heat_kJph,

        "U3C_unit_type":
            type(u.U3C).__name__,
        "U3C_temperature_K":
            float(_ATT_U3["condenser_temperature_K"]),
        "U3C_pressure_Pa":
            float(_ATT_U3["condenser_pressure_Pa"]),
        "U3C_wet_gas_total_kgph":
            float(wet_gas.F_mass),
        "U3C_condensate_total_kgph":
            float(condensate.F_mass),
        "U3C_condensed_water_kgph":
            mass(condensate, "Water"),
        "U3C_remaining_vapor_water_kgph":
            mass(wet_gas, "Water"),
        "U3C_residual_flash_cooling_duty_kJph":
            flash_cooling_kJph,

        "U3D_unit_type":
            type(u.U3D).__name__,
        "U3D_dry_gas_total_kgph":
            float(dry_gas.F_mass),
        "U3D_dry_gas_water_kgph":
            mass(dry_gas, "Water"),
        "U3D_removed_water_kgph":
            mass(dryer_water, "Water"),
        "U3D_power_kW":
            dryer_power_kW,
        "U3D_heating_duty_kJph":
            dryer_heating_kJph,
        "U3D_cooling_duty_kJph":
            dryer_cooling_kJph,

        "U3P_unit_type":
            type(u.U3P).__name__,
        "U3P_role":
            "idealized PSA surrogate",
        "U3P_H2_feed_mol_per_h":
            h2_in * 1000.0,
        "U3P_H2_product_mol_per_h":
            h2_product_mol * 1000.0,
        "U3P_actual_H2_recovery":
            actual_h2_recovery,
        "U3P_H2_product_mol_purity":
            h2_mol_purity,
        "U3P_tail_gas_total_kgph":
            float(tail_gas.F_mass),
        "U3P_tail_gas_H2_kgph":
            mass(tail_gas, "H2"),
        "U3P_tail_gas_CH4_kgph":
            mass(tail_gas, "CH4"),
        "U3P_tail_gas_CO_kgph":
            mass(tail_gas, "CO"),
        "U3P_tail_gas_CO2_kgph":
            mass(tail_gas, "CO2"),
        "U3P_tail_gas_LHV_kJph":
            tail_energy["LHV_kJph"],

        "U3K_H2_product_total_kgph":
            float(h2_product.F_mass),
        "U3K_H2_product_pressure_Pa":
            float(h2_product.P),
        "U3K_compressor_power_kW":
            compressor_power_kW,

        "psa_h2_recovery_assumption":
            float(_ATT_U3["psa_h2_recovery"]),
        "psa_status":
            _ATT_U3["psa_status"],
        "dryer_status":
            _ATT_U3["dryer_status"],
        "compressor_status":
            _ATT_U3["h2_compressor_status"],
        "tail_gas_combustion_status":
            _ATT_U3["tail_gas_combustion_status"],
    }


def get_att_recycle_summary(sys):
    """
    Return steady-state purge/recycle diagnostics after ``sys.simulate()``.

    The baseline uses:
        F2 -> SP1 whole-liquor split -> EC1 vacuum evaporator (excess
           water only, Na2CO3 salting-out) -> M1 (with the fresh
           solid-NaOH makeup) -> U2

    SP1 applies the same split to NaOH, residual Na2CO3, water, and any
    other dissolved components. EC1 removes only the water in excess of
    NaOH/(NaOH + H2O) = target after the fresh NaOH makeup (added in M1).
    """

    u = _units_of(sys)

    f1_cake = u.F1.outs[0]
    f1_liquor = u.F1.outs[1]
    f2_cake = u.F2.outs[0]
    f2_liquor = u.F2.outs[1]
    recovered_liquor = u.SP1.outs[0]
    purge = u.SP1.outs[1]
    ec1_concentrate = u.EC1.outs[0]
    fresh_naoh_solid = u.M1.ins[2]
    recycle = u.EC1.outs[0]
    removed_water = u.EC1.outs[1]
    u2_feed = u.U2.ins[0]

    def component_mass(stream, ID):
        return float(stream.imass[ID])

    def total_naoh_wt_frac(stream):
        if stream.F_mass <= 0.0:
            return 0.0
        return component_mass(stream, "NaOH") / float(stream.F_mass)

    def naoh_water_basis_wt_frac(stream):
        naoh = component_mass(stream, "NaOH")
        water = component_mass(stream, "Water")
        denom = naoh + water
        return naoh / denom if denom > 0.0 else 0.0

    return {
        "EC1_unit_type":
            type(u.EC1).__name__,
        "EC1_effect_count":
            1,
        "EC1_operating_pressure_Pa":
            u.EC1._operating_pressure_Pa,
        "EC1_Na2CO3_crystals_kgph":
            float(u.EC1._na2co3_crystals_kgph),

        "F1_filter_type":
            type(u.F1).__name__,
        "F1_mother_liquor_retention_fraction":
            float(
                getattr(
                    u.F1,
                    "_mother_liquor_retention_fraction",
                    0.0,
                )
            ),
        "F1_cake_total_kgph":
            float(f1_cake.F_mass),
        "F1_cake_water_kgph":
            component_mass(f1_cake, "Water"),
        "F1_cake_NaOH_loss_kgph":
            component_mass(f1_cake, "NaOH"),
        "F1_cake_Na2CO3_loss_kgph":
            component_mass(f1_cake, "Na2CO3"),
        "F1_filtrate_total_kgph":
            float(f1_liquor.F_mass),

        "F2_filter_type":
            type(u.F2).__name__,
        "F2_mother_liquor_retention_fraction":
            float(
                getattr(
                    u.F2,
                    "_mother_liquor_retention_fraction",
                    0.0,
                )
            ),
        "F2_cake_total_kgph":
            float(f2_cake.F_mass),
        "F2_cake_water_kgph":
            component_mass(f2_cake, "Water"),
        "F2_cake_NaOH_loss_kgph":
            component_mass(f2_cake, "NaOH"),
        "F2_cake_Na2CO3_loss_kgph":
            component_mass(f2_cake, "Na2CO3"),

        "F2_liquor_total_kgph":
            float(f2_liquor.F_mass),
        "F2_liquor_NaOH_kgph":
            component_mass(f2_liquor, "NaOH"),
        "F2_liquor_Na2CO3_kgph":
            component_mass(f2_liquor, "Na2CO3"),
        "F2_liquor_water_kgph":
            component_mass(f2_liquor, "Water"),

        "SP1_recovered_liquor_total_kgph":
            float(recovered_liquor.F_mass),
        "SP1_to_concentrator_total_kgph":
            float(recovered_liquor.F_mass),
        "SP1_recovered_NaOH_kgph":
            component_mass(recovered_liquor, "NaOH"),
        "SP1_recovered_Na2CO3_kgph":
            component_mass(recovered_liquor, "Na2CO3"),
        "SP1_recovered_water_kgph":
            component_mass(recovered_liquor, "Water"),
        "SP1_purge_total_kgph":
            float(purge.F_mass),
        "SP1_purge_NaOH_kgph":
            component_mass(purge, "NaOH"),
        "SP1_purge_Na2CO3_kgph":
            component_mass(purge, "Na2CO3"),
        "SP1_purge_water_kgph":
            component_mass(purge, "Water"),

        "EC1_concentrate_total_kgph":
            float(ec1_concentrate.F_mass),
        "EC1_concentrate_NaOH_kgph":
            component_mass(ec1_concentrate, "NaOH"),
        "EC1_concentrate_Na2CO3_kgph":
            component_mass(ec1_concentrate, "Na2CO3"),
        "EC1_concentrate_water_kgph":
            component_mass(ec1_concentrate, "Water"),

        "EC1_recycle_total_kgph":
            float(recycle.F_mass),
        "EC1_recycle_NaOH_kgph":
            component_mass(recycle, "NaOH"),
        "EC1_recycle_Na2CO3_kgph":
            component_mass(recycle, "Na2CO3"),
        "EC1_recycle_water_kgph":
            component_mass(recycle, "Water"),
        "EC1_recycle_NaOH_wt_frac_total_liquor":
            total_naoh_wt_frac(recycle),
        # Recycle liquor plus the fresh NaOH makeup added in M1.
        "EC1_recycle_NaOH_wt_frac_NaOH_water_basis":
            (component_mass(recycle, "NaOH") + component_mass(fresh_naoh_solid, "NaOH"))
            / (component_mass(recycle, "NaOH") + component_mass(fresh_naoh_solid, "NaOH")
               + component_mass(recycle, "Water")),
        "EC1_removed_water_kgph":
            component_mass(removed_water, "Water"),

        "fresh_NaOH_kgph":
            component_mass(fresh_naoh_solid, "NaOH"),
        "fresh_NaOH_form":
            "solid",
        "fresh_NaOH_makeup_water_kgph":
            component_mass(fresh_naoh_solid, "Water"),
        # Backward-compatible diagnostic key; should now be exactly zero.
        "fresh_NaOH_solution_water_kgph":
            component_mass(fresh_naoh_solid, "Water"),
        "gross_NaOH_target_kgph":
            float(
                getattr(
                    u.M1,
                    "_required_gross_naoh_kgph",
                    component_mass(u2_feed, "NaOH"),
                )
            ),

        "U2_feed_NaOH_kgph":
            component_mass(u2_feed, "NaOH"),
        "U2_feed_Na2CO3_kgph":
            component_mass(u2_feed, "Na2CO3"),
        "U2_feed_water_kgph":
            component_mass(u2_feed, "Water"),
    }

def calculate_heat_source(
    heat_duty_kJph,
    source,
):
    """
    Convert delivered heat into source-energy demand and direct CO2e.

    This is a scenario helper only. It does not assign the actual
    utility source used by a BioSTEAM unit.
    """

    heat_duty_kJph = float(
        heat_duty_kJph
    )

    if heat_duty_kJph < 0.0:
        raise ValueError(
            "heat_duty_kJph must be non-negative."
        )

    delivered_heat_MJph = (
        heat_duty_kJph / 1000.0
    )

    if source == "natural_gas":
        data = _ATT_ENERGY[
            "natural_gas"
        ]
        efficiency = float(
            data["burner_efficiency"]
        )
        source_energy_MJph = (
            delivered_heat_MJph
            / efficiency
        )
        emissions_kgCO2eph = (
            source_energy_MJph
            * float(
                data[
                    "emission_factor_kgCO2e_per_MJ_fuel"
                ]
            )
        )

    elif source == "engine_waste_heat":
        data = _ATT_ENERGY[
            "engine_waste_heat"
        ]
        source_energy_MJph = (
            delivered_heat_MJph
        )
        emissions_kgCO2eph = (
            delivered_heat_MJph
            * float(
                data[
                    "emission_factor_kgCO2e_per_MJ_heat"
                ]
            )
        )

    else:
        raise ValueError(
            f"Unsupported heat source: {source}"
        )

    return {
        "source":
            source,
        "delivered_heat_MJph":
            delivered_heat_MJph,
        "source_energy_MJph":
            source_energy_MJph,
        "emissions_kgCO2eph":
            emissions_kgCO2eph,
    }


def get_att_energy_source_summary(
    sys,
    assignments,
):
    """
    Evaluate a user-specified heat-source scenario.

    Parameters
    ----------
    sys : bst.System
        Simulated ATT system.
    assignments : dict
        Optional source assignments using unit IDs as keys, e.g.
        {"U2": "natural_gas", "D0": "engine_waste_heat"}.

    Notes
    -----
    This function does not apply heat-recovery credits. Recovered ATT
    heat will be modeled explicitly in later process units.
    """

    energy = get_att_energy_summary(
        sys
    )

    duty_map = {
        "D0":
            energy["D0_utility_heat_kJph"],
        "U2":
            energy["U2_utility_heat_kJph"],
        "C1":
            energy["C1_utility_heat_kJph"],
        "EC1":
            energy["EC1_utility_heat_kJph"],
    }

    results = {}
    total_source_energy_MJph = 0.0
    total_emissions_kgCO2eph = 0.0

    for unit_ID, source in assignments.items():
        if unit_ID not in duty_map:
            raise KeyError(
                f"Unsupported ATT heat-demand unit: {unit_ID}"
            )

        result = calculate_heat_source(
            duty_map[unit_ID],
            source,
        )
        results[unit_ID] = result

        total_source_energy_MJph += (
            result["source_energy_MJph"]
        )
        total_emissions_kgCO2eph += (
            result["emissions_kgCO2eph"]
        )

    dry_feed_kgph = float(
        energy["dry_feed_kgph"]
    )

    results["total_source_energy_MJph"] = (
        total_source_energy_MJph
    )
    results["total_emissions_kgCO2eph"] = (
        total_emissions_kgCO2eph
    )
    results[
        "total_source_energy_MJ_per_kg_dry"
    ] = (
        total_source_energy_MJph
        / dry_feed_kgph
    )
    results[
        "total_emissions_kgCO2e_per_kg_dry"
    ] = (
        total_emissions_kgCO2eph
        / dry_feed_kgph
    )

    return results


# ==========================================================================
# F2 filter-cake washing balance (used by systems/_att_system.py, W2)
# ==========================================================================

def wash_balance(*, dry_insolubles, retained_water, retained_naoh, retained_na2co3, filtrate_water, filtrate_naoh, filtrate_na2co3, wash_water, target_moisture=0.25, displacement_factor=1.0):
    values=locals()
    if any(not math.isfinite(v) for v in values.values()):
        raise ValueError('All inputs must be finite')
    if any(v<0 for k,v in values.items() if k!='target_moisture') or not 0<target_moisture<1:
        raise ValueError('Negative mass/kinetic factor or invalid moisture')
    if retained_water<=0 and wash_water>0: raise ValueError('Wet-cake water must be positive for wash model')
    efficiency=0.0 if wash_water==0 or retained_water==0 else -math.expm1(-displacement_factor*wash_water/retained_water)
    new_naoh=retained_naoh*(1-efficiency)
    new_carbonate=retained_na2co3*(1-efficiency)
    if wash_water==0:
        new_water=retained_water  # preserve exact unwashed native baseline
    else:
        new_water=target_moisture/(1-target_moisture)*(dry_insolubles+new_naoh+new_carbonate)
        if new_water>retained_water+wash_water+1e-10:
            raise ValueError('Insufficient water to meet washed cake target')
    out={
      'efficiency_ASSUMED':efficiency,
      'cake':{'Water':new_water,'NaOH':new_naoh,'Na2CO3':new_carbonate},
      'filtrate':{'Water':filtrate_water+retained_water+wash_water-new_water,
                  'NaOH':filtrate_naoh+retained_naoh-new_naoh,
                  'Na2CO3':filtrate_na2co3+retained_na2co3-new_carbonate},
      'dry_insolubles':dry_insolubles,
      'wash_water':wash_water,
    }
    for ID in ('Water','NaOH','Na2CO3'):
        initial=(retained_water+filtrate_water+wash_water if ID=='Water' else
            retained_naoh+filtrate_naoh if ID=='NaOH' else retained_na2co3+filtrate_na2co3)
        final=out['cake'][ID]+out['filtrate'][ID]
        if abs(final-initial)>1e-9*max(1.0,initial): raise ArithmeticError(f'{ID} balance failure')
        if out['filtrate'][ID]<-1e-12: raise ArithmeticError('Negative filtrate mass')
    out['cake_moisture']=new_water/(dry_insolubles+sum(out['cake'].values())) if (dry_insolubles+sum(out['cake'].values())) else 0
    return out
