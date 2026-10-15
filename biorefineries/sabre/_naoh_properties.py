"""
Property correlations for the NaOH-Na2CO3-H2O recycle liquor (ATT EC1/M2).

Sources
-------
[1] J. Olsson, A. Jernqvist, G. Aly, "Thermophysical properties of aqueous
    NaOH-H2O solutions at high concentrations", Int. J. Thermophys. 18 (1997)
    779-793. Water vapor pressure and solution enthalpy (coefficients as
    implemented in the propertiesNaOH package, TU Berlin). Checked here
    against steam tables (pure water within 0.3 %), the 1 atm boiling point
    of 50 wt% NaOH (146 C, cf. ~145-147 C in caustic handbooks) and the
    OxyChem heat-of-dilution table [2] (within ~5 %).
[2] OxyChem, Caustic Soda Handbook, Tables 6, 11 and 12 (anhydrous NaOH
    enthalpy, integral heat of solution, heat of dilution).
[3] J. Wu, J. Liu, Z. Wu, ACS Omega 5 (2020) 4875-4889, Tables 7, 8 and 14:
    Na2CO3 solubility in NaOH solutions at 363.15 K. The reported NaOH(s)
    co-saturation at 48.79 wt% NaOH contradicts the paper's own binary NaOH
    solubility (76.28 wt%) and is not used; the liquid composition is used
    only as a Na2CO3-saturation point.
[4] NBS Tables of Chemical Thermodynamic Properties (1982): heat of solution
    of anhydrous Na2CO3 at infinite dilution, -26.7 kJ/mol (25 C).

Concentrations x are mass fractions NaOH / (NaOH + H2O).

Validation (tests in test_att_ec1_naoh_evaporator.py)
------------------------------------------------------
- Pure-water vapor pressure: within 1 % of ThermoSTEAM/IAPWS, 20-150 C.
- 1 atm boiling points: within 2.5 K of supplier data (25, 33, 50 wt%) and
  of the ASSDA boiling curve (20-50 wt%). At 90 C this is about +/-7-12 %
  in pressure.
- Vapor pressure vs enthalpy (independently fitted): the water
  vaporization enthalpy from Clausius-Clapeyron agrees with the enthalpy
  model within 1.5 % for x = 0.18-0.50 at 80-100 C.
- Heat capacity: within 2.5 % of OxyChem Table 3 (10-50 wt%, 27-93 C).
- Heat of dilution / solution: within ~5 % of OxyChem Tables 11 and 12.
- Na2CO3 solubility in pure water at 90 C (Wu et al.): within 0.1 wt% of
  handbook values (45.62 g/100 g at 60 C, 43.6 at 100 C).
- Na2CO3 solubility, Na2CO3.H2O branch (<= 15 wt% NaOH): within -5 to
  +11 % of Ghaffari et al., Ind. Eng. Chem. Res. (2025) at 85 C and of
  Silcock (1976) at 100 C as tabulated by Qin et al., J. Chem. Eng. Data
  (2015); the two bracket 90 C.
- No NaOH(s) at x <= 0.50: Morey & Burlew, J. Phys. Chem. 68 (1964) give
  NaOH(s) + Na2CO3(s) co-saturation at 90 C at x = 0.749.
Not independently validated: Na2CO3 solubility in the anhydrous branch
(17-50 wt% NaOH; only Wu et al., no other 90 C data; 100 C data suggest the
model may be ~1.5-2x high at 19-35 wt% and up to ~2.6x low near 50 wt%,
i.e. +/-0.02 kg/h crystals and < 10 kJ/h in the baseline), the stable solid
there (Na2CO3 vs Na2CO3.H2O), its temperature dependence, and the
crystallization enthalpy in concentrated NaOH (infinite-dilution value).
"""
from math import exp, log

__all__ = (
    "water_vapor_pressure_Pa",
    "solution_enthalpy_kJ_per_kg",
    "solid_naoh_enthalpy_kJ_per_kg",
    "na2co3_solubility_mol_per_kg_water",
    "NA2CO3_DISSOLUTION_kJ_per_mol",
)

# [1] vapor pressure: ln(P/kPa) = (a1 + a2*T)/(T - a3), T in C,
# a_i polynomials in ln(water mass fraction).
_P_K = (-113.93947, 209.82305, 494.77153, 6860.8330, 2676.6433,
        -21740.328, -34750.872, -20122.157, -4102.9890)
_P_L = (16.240074, -11.864008, -223.47305, -1650.3997, -5997.3118,
        -12318.744, -15303.153, -11707.480, -5364.9554, -1338.5412,
        -137.96889)
_P_M = (-226.80157, 293.17155, 5081.8791, 36752.126, 131262.00,
        259399.54, 301696.22, 208617.90, 81774.024, 15648.526,
        906.29769)
# (upper T bound [C], minimum water mass fraction) for the vapor pressure.
_P_RANGE = ((20.0, 0.582), (60.0, 0.500), (70.0, 0.353),
            (150.0, 0.300), (200.0, 0.200))

# [1] enthalpy: h = c1 + c2*T + c3*T^2 + c4*T^3 [kJ/kg solution], T in C,
# reference liquid water at 0 C.
_H_K = (1288.4485, -0.49649131, -4387.8908, -4.0915144, 4938.2298,
        7.2887292, -1841.1890, -3.0202651)
_H_L = (2.3087919, -9.0004252, 167.59914, -1051.6368, 3394.3378,
        -6115.0986, 6220.8249, -3348.8098, 743.87432)
_H_M = (0.02302860, -0.37866056, 2.4529593, -8.2693542, 15.728833,
        -16.944427, 9.6254192, -2.2410628)
_H_N = (-8.5131313e-5, 136.52823e-5, -875.68741e-5, 2920.0398e-5,
        -5488.2983e-5, 5841.8034e-5, -3278.7483e-5, 754.45993e-5)
_H_RANGE = ((4.0, 0.780), (10.0, 0.680), (15.0, 0.580), (26.0, 0.540),
            (37.0, 0.440), (48.0, 0.400), (60.0, 0.340), (71.0, 0.300),
            (82.0, 0.280), (93.0, 0.240), (204.0, 0.220))

# Solid NaOH enthalpy in the frame of [1]: 1065 kJ/kg at 20 C, from the
# integral heats of solution in [2] Table 11 (nine points, 1048-1086 kJ/kg),
# plus the sensible enthalpy of [2] Table 6 (deg F, BTU/lb above 32 F).
_H_SOLID_20C = 1065.0
_SOLID_TABLE_F = (32, 50, 100, 150, 200, 250, 300, 350, 400, 450, 500, 550)
_SOLID_TABLE_BTU = (0.00, 5.57, 21.71, 38.82, 56.91, 75.98, 96.01, 117.03,
                    139.02, 161.98, 185.92, 210.83)
_BTU_PER_LB = 2.326  # kJ/kg

# [3] Na2CO3 saturation at 363.15 K as (NaOH, Na2CO3) molalities [mol/kg
# H2O]. Below 5.96 mol/kg NaOH the solid is Na2CO3.H2O, above it anhydrous
# Na2CO3 (C + C1 co-saturation at 5.96 / 1.44).
_SOLUBILITY_T_K = 363.15
_C1_BRANCH = ((0.0, 4.14), (5.96, 1.44))
_C_BRANCH = ((5.96, 1.44), (24.08, 0.10))
_C_BRANCH_MAX_NAOH = 26.0  # modest extrapolation limit (~51 wt% NaOH)

NA2CO3_DISSOLUTION_kJ_per_mol = -26.7  # [4]


def _poly(coefficients, x):
    return sum(c * x**i for i, c in enumerate(coefficients))


def _check(x, T_C, ranges, name):
    if not 0.0 <= x < 1.0:
        raise ValueError(f"{name}: NaOH mass fraction {x} outside [0, 1)")
    water = 1.0 - x
    for T_max, water_min in ranges:
        if T_C < T_max or (T_max == ranges[-1][0] and T_C <= T_max):
            if water < water_min:
                raise ValueError(
                    f"{name}: x = {x:.4f} at {T_C:.2f} C is outside the "
                    f"validated range of Olsson et al. (1997)."
                )
            return
    raise ValueError(f"{name}: T = {T_C:.2f} C above the validated range.")


def water_vapor_pressure_Pa(x, T_K):
    """Water vapor pressure over NaOH(aq) [Pa] [1]."""
    T_C = T_K - 273.15
    _check(x, T_C, _P_RANGE, "water_vapor_pressure_Pa")
    lnw = log(1.0 - x)
    a1, a2, a3 = _poly(_P_K, lnw), _poly(_P_L, lnw), _poly(_P_M, lnw)
    return 1000.0 * exp((a1 + a2 * T_C) / (T_C - a3))


def solution_enthalpy_kJ_per_kg(x, T_K):
    """Specific enthalpy of NaOH(aq) [kJ/kg solution] [1]."""
    T_C = T_K - 273.15
    _check(x, T_C, _H_RANGE, "solution_enthalpy_kJ_per_kg")
    xi = 1.0 - x
    c1 = ((_H_K[0] + _H_K[2] * xi + _H_K[4] * xi**2 + _H_K[6] * xi**3)
          / (1.0 + _H_K[1] * xi + _H_K[3] * xi**2 + _H_K[5] * xi**3 + _H_K[7] * xi**4))
    return (c1 + _poly(_H_L, xi) * T_C + _poly(_H_M, xi) * T_C**2
            + _poly(_H_N, xi) * T_C**3)


def solid_naoh_enthalpy_kJ_per_kg(T_K):
    """Anhydrous NaOH(s) enthalpy in the reference frame of [1] [kJ/kg]."""
    T_F = (T_K - 273.15) * 1.8 + 32.0

    def table(T):
        for i in range(len(_SOLID_TABLE_F) - 1):
            T0, T1 = _SOLID_TABLE_F[i], _SOLID_TABLE_F[i + 1]
            if T0 <= T <= T1:
                h0, h1 = _SOLID_TABLE_BTU[i], _SOLID_TABLE_BTU[i + 1]
                return h0 + (h1 - h0) * (T - T0) / (T1 - T0)
        raise ValueError(f"Solid NaOH enthalpy: {T:.1f} F outside 32-550 F.")

    return _H_SOLID_20C + _BTU_PER_LB * (table(T_F) - table(68.0))


def na2co3_solubility_mol_per_kg_water(m_naoh, T_K, allow_temperature_extrapolation=False):
    """
    Na2CO3 saturation molality and stable solid in NaOH(aq) at 363.15 K [3].
    Returns (mol Na2CO3 / kg H2O, 'Na2CO3' or 'Na2CO3.H2O').
    Log-linear interpolation between measured invariant/saturation points.
    With ``allow_temperature_extrapolation`` the 363.15 K data are used at
    other temperatures (an unverified assumption; scenarios only).
    """
    if abs(T_K - _SOLUBILITY_T_K) > 0.5 and not allow_temperature_extrapolation:
        raise ValueError("Na2CO3 solubility data are only for 363.15 K.")
    if m_naoh < 0.0 or m_naoh > _C_BRANCH_MAX_NAOH:
        raise ValueError(
            f"NaOH molality {m_naoh:.3f} outside the Na2CO3 solubility data."
        )
    if m_naoh < _C_BRANCH[0][0]:
        (m0, s0), (m1, s1), solid = *_C1_BRANCH, "Na2CO3.H2O"
    else:
        (m0, s0), (m1, s1), solid = *_C_BRANCH, "Na2CO3"
    slope = (log(s1) - log(s0)) / (m1 - m0)
    return exp(log(s0) + slope * (m_naoh - m0)), solid
