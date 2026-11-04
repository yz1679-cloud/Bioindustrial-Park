# Bioindustrial-Park: BioSTEAM's Premier Biorefinery Models and Results
# Copyright (C) 2026-, Yu Zhou,
#                      Yalin Li <mailto.yalin.li@gmail.com>
#
# This module is under the UIUC open-source license. See
# github.com/BioSTEAMDevelopmentGroup/biosteam/blob/master/LICENSE.txt
# for license details.

"""ATT mass and energy accounting.

Energy accounting helpers for the ATT flowsheet are analysis/reporting
logic only; process construction remains in system.py.
ATT physical-heat and gas-product chemical-energy diagnostics are reported
explicitly. No flowsheet changes are made by these helpers.

``wash_balance`` is the conservative mass-only filter-cake washing balance
called by the W2 washer in system.py (no equilibrium/heat
claims).
"""
import math


from biorefineries.ATT.utils import load_assumptions

__all__ = (
    "get_att_energy_summary",
    "get_att_heat_recovery_summary",
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
    * Hot U2 gas/steam is treated in the U3 gas-treatment train.
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



# ==========================================================================
# F2 filter-cake washing balance (used by system.py, W2)
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
