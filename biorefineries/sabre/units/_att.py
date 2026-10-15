import biosteam as bst
import numpy as np
import thermosteam as tmo

from biorefineries.sabre import _naoh_properties as _naoh
from biorefineries.sabre.utils import load_assumptions

__all__ = (
    "ATTReactor",
    "solve_att_u2_closure",
    "close_att_u2_balance",
    "CausticizationReactor",
    "NaOHEvaporator",
    "NaOHMakeupMixer",
    "aqueous_naoh_enthalpy_correction_kJph",
    "ATTHeatRecovery",
)

_ATT_DATA = load_assumptions("att.yaml")["att"]

_ATT = _ATT_DATA["reactor"]
_ATT_DOWNSTREAM = _ATT_DATA["downstream"]

_SARGASSUM_DRY_IDS = (
    "Ash",
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


def _solve_att_u2_CHO(feed_atoms, fixed_atoms, gas_atoms, char_atoms):
    # x*gas + char*c + H2O*w = feed - fixed, for the C, H and O balances.
    water_atoms = {"H": 2, "O": 1}
    CHO = ("C", "H", "O")
    A = np.array([
        [gas_atoms.get(e, 0.0), char_atoms.get(e, 0.0), water_atoms.get(e, 0.0)]
        for e in CHO
    ])
    b = np.array([feed_atoms.get(e, 0.0) - fixed_atoms.get(e, 0.0) for e in CHO])
    return tuple(map(float, np.linalg.solve(A, b)))


def close_att_u2_balance(method, feed_atoms, fixed_atoms, measured_gas_kmolph,
                         species_atoms, char_atoms, closure_gas_ID="CO2"):
    """
    Close the U2 C, H and O balances; return (gas kmol/h by species, char
    kmol/h, product water kmol/h, gas scale factor s or nan).

    ``uniform_redox_scaling``: every measured gas is scaled by one factor s.
    ``h2_priority``: the measured H2 is kept; the other reported gases are
    not imposed and the remaining C, H and O leave as char, water and one
    closure gas (an unmeasured closure product, not an experimental yield).
    """
    def atoms_of(flows):
        totals = {}
        for ID, kmolph in flows.items():
            for element, n in species_atoms[ID].items():
                totals[element] = totals.get(element, 0.0) + n * kmolph
        return totals

    if method == "uniform_redox_scaling":
        scale, char_kmolph, water_kmolph = solve_att_u2_closure(
            feed_atoms, fixed_atoms, atoms_of(measured_gas_kmolph), char_atoms
        )
        gas = {ID: scale * n for ID, n in measured_gas_kmolph.items()}
        return gas, char_kmolph, water_kmolph, scale
    if method == "h2_priority":
        h2 = measured_gas_kmolph["H2"]
        fixed = dict(fixed_atoms)
        fixed["H"] = fixed.get("H", 0.0) + 2.0 * h2
        closure, char_kmolph, water_kmolph = _solve_att_u2_CHO(
            feed_atoms, fixed, species_atoms[closure_gas_ID], char_atoms
        )
        if min(closure, char_kmolph, water_kmolph) < 0.0:
            raise RuntimeError(
                "H2-priority U2 closure is infeasible: "
                f"{closure_gas_ID} {closure:.6g}, char {char_kmolph:.6g}, "
                f"water {water_kmolph:.6g} kmol/h. The measured H2 cannot be "
                "kept with this char formula and closure gas."
            )
        gas = {ID: 0.0 for ID in measured_gas_kmolph}
        gas["H2"] = h2
        gas[closure_gas_ID] = gas.get(closure_gas_ID, 0.0) + closure
        return gas, char_kmolph, water_kmolph, float("nan")
    if method in ("h2_measured_ch4_max", "uniform_co2_free"):
        # Alternative gas-yield scenarios (char = 0; selected feasible scenarios, not the baseline).
        # h2_measured_ch4_max: H2 and CO measured; CH4, CO2, water from C/H/O.
        # uniform_co2_free: H2, CH4, CO x s; CO2 and water close C and O.
        import numpy as np_
        rows = ("C", "H", "O")
        rest = {e: feed_atoms.get(e, 0.0) - fixed_atoms.get(e, 0.0) for e in rows}
        if method == "h2_measured_ch4_max":
            h2, co = measured_gas_kmolph["H2"], measured_gas_kmolph["CO"]
            b = [rest["C"] - co, rest["H"] - 2.0 * h2, rest["O"] - co]
            M = [[1.0, 1.0, 0.0], [4.0, 0.0, 2.0], [0.0, 2.0, 1.0]]          # CH4, CO2, H2O
            ch4, co2, water = map(float, np_.linalg.solve(M, b))
            gas, scale = {"H2": h2, "CH4": ch4, "CO": co, "CO2": co2}, float("nan")
        else:
            scaled = {ID: measured_gas_kmolph[ID] for ID in ("H2", "CH4", "CO")}
            g = atoms_of(scaled)
            M = [[g.get(e, 0.0), species_atoms["CO2"].get(e, 0.0), {"H": 2.0, "O": 1.0}.get(e, 0.0)] for e in rows]
            scale, co2, water = map(float, np_.linalg.solve(M, [rest[e] for e in rows]))
            gas = {ID: scale * n for ID, n in scaled.items()}
            gas["CO2"] = co2
        if min(*gas.values(), water) < 0.0 or (scale == scale and not 0.0 < scale <= 1.0):
            raise RuntimeError(f"U2 bound closure '{method}' infeasible: gases {gas}, water {water:.6g}.")
        for ID in measured_gas_kmolph:
            gas.setdefault(ID, 0.0)
        return gas, 0.0, water, scale
    if method == "experimental_fixed":
        # All measured gases kept exactly. C closes on the char and H on the
        # product water (the only unmeasured C- and H-bearing outlets); O has
        # no remaining unmeasured carrier and is NOT closed: the outlet O
        # deficit equals half the redox excess of the measured gases and is
        # reported by the reactor as an unresolved elemental residual.
        gas = dict(measured_gas_kmolph)
        fixed = dict(fixed_atoms)
        for element, n in atoms_of(gas).items():
            fixed[element] = fixed.get(element, 0.0) + n
        remaining = {e: feed_atoms.get(e, 0.0) - fixed.get(e, 0.0) for e in ("C", "H")}
        char_kmolph = remaining["C"] / char_atoms["C"]
        water_kmolph = (remaining["H"] - char_kmolph * char_atoms.get("H", 0.0)) / 2.0
        if char_kmolph < 0.0 or water_kmolph < 0.0:
            raise RuntimeError(
                f"Experimental-fixed U2 closure gives negative char ({char_kmolph:.6g}) "
                f"or water ({water_kmolph:.6g}) kmol/h."
            )
        return gas, char_kmolph, water_kmolph, float("nan")
    raise ValueError(f"Unsupported gas_closure_method '{method}'.")


def solve_att_u2_closure(feed_atoms, fixed_atoms, gas_atoms, char_atoms):
    """
    Solve the U2 C, H and O balances for the common scale factor s of the
    measured gases, the char flow and the product water [kmol/h]:

        s*gas + char*c + H2O*w = feed - fixed

    ``fixed_atoms`` are the outlets set independently (ash, Na2CO3,
    residual NaOH, retained N/S and any other specified product).
    s is a RECONCILIATION factor, not a measurement.
    """
    scale, char_kmolph, water_kmolph = _solve_att_u2_CHO(
        feed_atoms, fixed_atoms, gas_atoms, char_atoms
    )
    if not 0.0 < scale <= 1.0 + 1e-12:
        raise RuntimeError(
            f"U2 gas scale factor s = {scale:.6g} is outside (0, 1]. "
            "s > 1 means the measured gases do not exhaust the feed's "
            "reducing power, so the char formula or NaOH conversion, "
            "not the gas yields, must close the balance."
        )
    if char_kmolph < 0.0 or water_kmolph < 0.0:
        raise RuntimeError(
            f"U2 closure gives negative char ({char_kmolph:.6g}) or "
            f"water ({water_kmolph:.6g}) kmol/h."
        )
    return scale, char_kmolph, water_kmolph


class ATTReactor(bst.Unit):
    """
    Alkaline thermal treatment (ATT) reactor for Sargassum.

    The baseline case is Ni-CatATT. NaOH loading is defined on the actual
    SaBRe dry-ash-free feed basis; NaOH-to-Na2CO3 conversion follows
    att.yaml (workbook: complete).

    All elements (C, H, O, N, S, Na, Ca) are closed exactly; feed N and S
    are retained in the char (``CharN``/``CharS``). The reported absolute gas
    yields together exceed the reducing power (available electrons) of the
    feed organics, so not all of them can be kept (``gas_closure_method``):

    - ``uniform_redox_scaling`` (baseline, Gas-C; att.yaml): the measured gas
      composition is kept and every measured gas is scaled by one factor s
      (0.5998); the remaining C leaves as char.
    - ``h2_priority`` (comparison): the measured H2 yield is kept. CH4, CO and
      CO2 are not imposed (not complete product yields); the remaining C, H
      and O leave as char (``Char``), product water and one closure gas
      (att.yaml ``h2_priority_closure_gas``), an unmeasured closure product.
    - ``h2_measured_ch4_max`` (Gas-A) / ``uniform_co2_free`` (Gas-Cprime):
      alternative element-balanced gas-yield scenarios (char = 0), not the
      baseline: measured H2 and CO with the maximum feasible CH4; or H2, CH4
      and CO scaled by s with CO2 determined by carbon closure.
    - ``experimental_fixed`` (experimental-fidelity check): all measured gases
      kept exactly; C closes on char and H on water; the O residual cannot
      close (the measured gases exceed the feed's available electrons) and is
      reported in ``_unresolved_element_kmolph``, not assigned to a species.

    The model yields are reported next to the unchanged measured yields.

    The process heat duty is Hnet(outlets) - Hnet(inlet) and therefore
    includes the reaction enthalpy. The organic feed's formation enthalpy is
    re-referenced to the HHV in att.yaml, and the dissolved NaOH in the
    feed is corrected to the NaOH(aq) electrolyte enthalpy
    (``aqueous_feed_enthalpy_correction_kJph``, set by the flowsheet).

    Notes
    -----
    The auxiliary HXutility represents heat supplied to the ATT reactor.
    This is a reduced-order, data-reconciled yield model, not a kinetic or
    mechanistic reaction model.
    """

    _N_ins = 1
    _N_outs = 2

    # Official BioSTEAM auxiliary-unit pattern.
    auxiliary_unit_names = ("heat_exchanger",)

    def _init(
        self,
        target_temperature_K=_ATT["target_temperature_K"],
        heat_loss_fraction=_ATT["heat_loss_fraction"],
        case_name=None,
        gas_closure_method=None,
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

        if case_name is None:
            case_name = _ATT["baseline_case"]

        cases = _ATT["cases"]
        if case_name not in cases:
            raise KeyError(
                f"Unknown ATT case '{case_name}'. "
                f"Available cases: {tuple(cases)}"
            )

        self.case_name = case_name
        self.case_data = cases[case_name]

        self.naoh_kg_per_kg_daf = float(
            self.case_data["naoh_kg_per_kg_daf"]
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

        self.gas_closure_method = str(
            balance["gas_closure_method"] if gas_closure_method is None
            else gas_closure_method
        )
        self.closure_gas_ID = str(balance["h2_priority_closure_gas"])
        if self.gas_closure_method not in ("h2_priority", "uniform_redox_scaling", "experimental_fixed",
                                           "h2_measured_ch4_max", "uniform_co2_free"):
            raise ValueError(
                f"Unsupported gas_closure_method '{self.gas_closure_method}'."
            )
        self.char_ID = str(balance["char_species"])
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

        # Auxiliary HXutility.
        #
        # The detailed thermodynamic duty is calculated in _design().
        # The auxiliary exchanger then carries the utility and equipment-
        # cost bookkeeping for that calculated duty.
        self.auxiliary(
            "heat_exchanger",
            bst.HXutility,
            ins=self.ins,
            T=self.target_temperature_K,
            rigorous=False,
            heat_only=True,
            heat_transfer_efficiency=self.heat_transfer_efficiency,
        )

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
            feed.imass["Ash"]
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
        residue.imass["Ash"] = ash_kgph

        sodium_kmolph = float(feed.get_atomic_flow("Na"))
        na2co3_kmolph = (
            0.5 * sodium_kmolph * self.naoh_to_na2co3_conversion
        )
        residue.imol["Na2CO3"] = na2co3_kmolph
        residue.imol["NaOH"] = sodium_kmolph - 2.0 * na2co3_kmolph

        chemicals = feed.chemicals
        inorganic_IDs = ("Water", "NaOH", "Na2CO3", "Ash")
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
        # 3. Close the C, H and O balances (gas_closure_method):
        #    h2_priority - measured H2 kept, closure gas + char + water;
        #    uniform_redox_scaling - all measured gases x s + char + water.
        # ----------------------------------------------------------
        fixed_atoms = atoms_of(flows_of(residue))
        char_atoms = chemicals[self.char_ID].atoms
        species_atoms = {
            ID: chemicals[ID].atoms
            for ID in (*measured_gas_kmolph, self.closure_gas_ID)
        }
        model_gas_kmolph, char_kmolph, water_kmolph, scale = close_att_u2_balance(
            self.gas_closure_method, feed_atoms, fixed_atoms,
            measured_gas_kmolph, species_atoms, char_atoms, self.closure_gas_ID,
        )
        gas_atoms = atoms_of(model_gas_kmolph)

        for ID, kmolph in model_gas_kmolph.items():
            gas.imol[ID] = kmolph
        gas.imol["Water"] = water_kmolph
        residue.imol[self.char_ID] = char_kmolph

        # ----------------------------------------------------------
        # 4. Verification and reporting.
        # ----------------------------------------------------------
        out_atoms = atoms_of(flows_of(gas, residue))
        atomic_balance_errors = {
            element: out_atoms.get(element, 0.0) - feed_atoms.get(element, 0.0)
            for element in set(feed_atoms) | set(out_atoms)
        }
        tolerance = 1e-9 * max(1.0, max(map(abs, feed_atoms.values())))
        # Unresolved elemental residuals (outlet - inlet, kmol/h): allowed
        # only for the experimental_fixed closure, where they are reported,
        # never silently closed.
        self._unresolved_element_kmolph = {
            element: error for element, error in atomic_balance_errors.items()
            if abs(error) > tolerance
        }
        if self._unresolved_element_kmolph and self.gas_closure_method != "experimental_fixed":
            raise RuntimeError(
                f"U2 elemental balance not closed: {atomic_balance_errors}"
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
             for ID in (self.char_ID, *self.heteroatom_IDs.values())}
        )

        self._measured_gas_kmolph = measured_gas_kmolph
        self._gas_scale_factor = scale
        # Model (closed) gas yields: H2 = measured under h2_priority,
        # measured x s under uniform_redox_scaling.
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
        self._char_kgph = sum(
            float(residue.imass[ID])
            for ID in (self.char_ID, *self.heteroatom_IDs.values())
        )
        self._char_carbon_fraction_of_feed_organic_C = (
            char_kmolph * char_atoms.get("C", 0.0) / organic_atoms["C"]
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
        if self.gas_closure_method == "uniform_redox_scaling":
            status = (f"C/H/O/N/S/Na/Ca closed; all measured gases scaled by s = {scale:.4f} "
                      "to the feed's redox capacity.")
        elif self.gas_closure_method == "h2_priority":
            status = (f"C/H/O/N/S/Na/Ca closed; measured H2 kept, CH4/CO not imposed, "
                      f"{self.closure_gas_ID} is a closure product.")
        elif self.gas_closure_method in ("h2_measured_ch4_max", "uniform_co2_free"):
            status = (f"C/H/O/N/S/Na/Ca closed; alternative gas-yield scenario {self.gas_closure_method} "
                      "(char = 0); not the baseline.")
        else:
            status = ("NOT CLOSED: all measured gases kept; C closed on char, H on water; unresolved "
                      f"residuals (kmol/h) {self._unresolved_element_kmolph}.")
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
            if chemical.ID not in ("Water", "NaOH", "Na2CO3", "Ash")
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

        # Populate the auxiliary HX outlet with a temperature endpoint
        # for exchanger design/costing. The detailed phase-change duty is
        # supplied explicitly from the ThermoSteam enthalpy calculation
        # above, so this auxiliary outlet is only a design representation.
        hx = self.heat_exchanger
        hx_out = hx.outs[0]
        hx_out.copy_like(feed)
        hx_out.T = self.target_temperature_K
        hx_out.P = feed.P

        # Design/cost the auxiliary exchanger at the calculated process
        # duty. BioSTEAM automatically rolls auxiliary utilities and costs
        # into the parent ATT reactor.
        hx.simulate(
            run=False,
            design_kwargs={
                "duty": heat_duty_kJph,
            },
        )

        utility_heat_duty_kJph = sum(
            max(float(hu.duty), 0.0)
            for hu in hx.heat_utilities
        )

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

        # Gas basis: measured vs model (closed) yields.
        if self.gas_closure_method == "uniform_redox_scaling":
            self.design_results[
                "Gas yield scale factor s (reconciliation, not measured)"
            ] = self._gas_scale_factor
        elif self.gas_closure_method == "experimental_fixed":
            for element, error in self._unresolved_element_kmolph.items():
                self.design_results[
                    f"UNRESOLVED {element} balance, outlet - inlet [mmol/g daf]"
                ] = error * 1000.0 / self._daf_sargassum_kgph
        else:
            self.design_results[
                f"Closure {self.closure_gas_ID} [mmol/g daf] (unmeasured closure product)"
            ] = self._model_gas_yield_mmol_per_g_daf[self.closure_gas_ID]
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
        self.target_temperature_K = float(target_temperature_K)
        self.heat_loss_fraction = float(heat_loss_fraction)

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
        lime.empty()
        lime.imol["CaOH2"] = required_lime_kmolph
        lime.phase = "s"
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
        from biorefineries.sabre.analyses.att.thermodynamics import from_reactor_streams
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
        # Step 7.16 scope superseded by aqueous reference scope above
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

        # Register C1's calculated duty with BioSTEAM.  The argument to
        # add_heat_utility is the PROCESS duty (hu.unit_duty), NOT the
        # already loss-adjusted utility duty (hu.duty).  Otherwise the
        # 5% assumed heat loss would be counted twice.
        #
        # A two-inlet reactive unit has no single process-inlet T-Q curve.
        # The operating temperature is used only as a utility-agent
        # selection proxy, NOT as evidence of an isothermal process.
        # Keep this lumped duty outside automatic HXN matching until a
        # physically defensible reaction/sensible heat profile exists.
        if abs(heat_duty_kJph) > 1e-12:
            efficiency = (
                1.0 / (1.0 + self.heat_loss_fraction)
                if heat_duty_kJph > 0.0 else 1.0
            )
            hu = self.add_heat_utility(
                heat_duty_kJph,
                self.target_temperature_K,
                self.target_temperature_K,
                heat_transfer_efficiency=efficiency,
                hxn_ok=False,
            )
            # Use actual registered utility for reporting; both values
            # should match by construction for this lumped baseline.
            utility_heat_duty_kJph = float(hu.duty)
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
# NaOH-Na2CO3-H2O recycle liquor: EC1 evaporator and M2 makeup mixer
# ======================================================================
_MW_NAOH = 39.997      # g/mol
_MW_NA2CO3 = 105.988   # g/mol
_LIQUOR_IDS = ("Water", "NaOH", "Na2CO3")


def _liquor_masses(stream, unit_ID):
    other = {
        chemical.ID: float(stream.imass[chemical.ID])
        for chemical in stream.chemicals
        if chemical.ID not in _LIQUOR_IDS and float(stream.imass[chemical.ID]) != 0.0
    }
    if other:
        raise RuntimeError(
            f"{unit_ID}: the NaOH-Na2CO3-H2O property model cannot handle {other}."
        )
    return tuple(float(stream.imass[ID]) for ID in _LIQUOR_IDS)


def _solid_na2co3_kgph(stream):
    if stream.phases and "s" in stream.phases:
        return float(stream.imass["s", "Na2CO3"])
    return float(stream.imass["Na2CO3"]) if stream.phase == "s" else 0.0


def _na2co3_sensible_kJph(kgph, T_in, T_out, chemicals):
    """Na2CO3 sensible enthalpy change (solid Cp) [kJ/h]."""
    if kgph == 0.0 or T_in == T_out:
        return 0.0
    Cn = chemicals["Na2CO3"].Cn
    T_mean = 0.5 * (T_in + T_out)
    return kgph / _MW_NA2CO3 * Cn("s", T_mean) * (T_out - T_in)


def aqueous_naoh_enthalpy_correction_kJph(stream):
    """
    Enthalpy of the dissolved NaOH in ``stream`` from the electrolyte model
    minus ThermoSTEAM's value [kJ/h].

    ThermoSTEAM represents dissolved NaOH as pure (subcooled molten) liquid
    NaOH; the electrolyte model uses solid NaOH + water -> NaOH(aq) with the
    concentration-dependent heat of solution. Water enthalpy is common to
    both and cancels.
    """
    water = float(stream.imass["Water"])
    naoh = float(stream.imass["NaOH"])
    if naoh <= 0.0:
        return 0.0
    T = float(stream.T)
    x = naoh / (naoh + water)
    real = (
        (naoh + water) * _naoh.solution_enthalpy_kJ_per_kg(x, T)
        - water * _naoh.solution_enthalpy_kJ_per_kg(0.0, T)
        - naoh * _naoh.solid_naoh_enthalpy_kJ_per_kg(T)
    )
    NaOH = stream.chemicals["NaOH"]
    native = naoh / _MW_NAOH * (NaOH.H("l", T) - NaOH.H("s", T))
    return real - native


class NaOHEvaporator(bst.Unit):
    """
    EC1: single-effect vacuum evaporator for the NaOH-Na2CO3-H2O recycle
    liquor, operated at a fixed boiling temperature, with Na2CO3 salting-out.

    Only water in excess of ``max_water_kgph`` is evaporated; that limit is
    set by the system so the liquor reaches the target NaOH/(NaOH + H2O)
    after the downstream fresh solid-NaOH makeup. If the liquor already
    holds less water, nothing is evaporated.

    Physics (see biorefineries.sabre._naoh_properties):
    * operating pressure = water vapor pressure over the outlet NaOH(aq)
      (Olsson et al. 1997), i.e. including boiling-point elevation;
    * Na2CO3 above its solubility in the outlet liquor (Wu et al. 2020,
      363.15 K) crystallizes as anhydrous Na2CO3 and stays in the slurry;
    * duty from the NaOH(aq) enthalpy-concentration correlation, the vapor
      enthalpy, the Na2CO3 crystallization enthalpy and a heat-loss factor;
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
              allow_na2co3_solubility_extrapolation=False):
        self.T = float(T)
        self.heat_loss_fraction = float(heat_loss_fraction)
        self.max_water_kgph = float(max_water_kgph)
        # Scenarios away from 363.15 K only (unverified assumption).
        self.allow_na2co3_solubility_extrapolation = bool(allow_na2co3_solubility_extrapolation)

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

        m_naoh = naoh / _MW_NAOH * 1e3 / water_out           # mol/kg H2O
        m_sat, solid = _naoh.na2co3_solubility_mol_per_kg_water(
            m_naoh, T, self.allow_na2co3_solubility_extrapolation
        )
        self._na2co3_solubility_extrapolated = abs(T - 363.15) > 0.5
        dissolved = min(carbonate, m_sat * water_out * _MW_NA2CO3 / 1e3)
        crystals = carbonate - dissolved
        if crystals > 0.0 and solid != "Na2CO3":
            raise NotImplementedError(
                f"{self.ID}: Na2CO3.H2O crystallization is not modeled."
            )

        concentrate.empty()
        concentrate.phases = ("l", "s")
        concentrate.imass["l", "Water"] = water_out
        concentrate.imass["l", "NaOH"] = naoh
        concentrate.imass["l", "Na2CO3"] = dissolved
        concentrate.imass["s", "Na2CO3"] = crystals
        concentrate.T = T
        concentrate.P = 101325.0

        condensate.empty()
        if evaporated > 0.0:
            P = _naoh.water_vapor_pressure_Pa(x_out, T)
            T_condensation = float(feed.chemicals["Water"].Tsat(P))
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
        concentrate = self.outs[0]
        water_in, naoh, carbonate = _liquor_masses(feed, self.ID)
        water_out = float(concentrate.imass["l", "Water"])
        evaporated = self._evaporated_water_kgph
        T_in, T = float(feed.T), float(concentrate.T)
        h = _naoh.solution_enthalpy_kJ_per_kg

        liquor_in = (naoh + water_in) * h(naoh / (naoh + water_in), T_in)
        liquor_out = (naoh + water_out) * h(self._outlet_naoh_wt_frac_naoh_water, T)
        Water = feed.chemicals["Water"]
        h_vapor = h(0.0, T) + Water.Hvap(T) / Water.MW         # kJ/kg
        vapor = evaporated * h_vapor
        crystallization = (
            -_naoh.NA2CO3_DISSOLUTION_kJ_per_mol
            * self._na2co3_crystals_kgph / _MW_NA2CO3 * 1e3
        )
        sensible_carbonate = _na2co3_sensible_kJph(carbonate, T_in, T, feed.chemicals)
        duty = liquor_out + vapor - liquor_in + crystallization + sensible_carbonate

        condenser = 0.0
        if evaporated > 0.0:
            condenser = -evaporated * (
                h_vapor - h(0.0, self._condensation_temperature_K)
            )

        if duty > 0.0:
            self.add_heat_utility(
                duty, T, T,
                heat_transfer_efficiency=1.0 / (1.0 + self.heat_loss_fraction),
                hxn_ok=False,
            )
        if condenser < 0.0:
            self.add_heat_utility(
                condenser, self._condensation_temperature_K,
                self._condensation_temperature_K, hxn_ok=False,
            )

        self._heat_duty_kJph = duty
        self._crystallization_heat_kJph = crystallization
        self._condenser_duty_kJph = condenser
        self._utility_heat_duty_kJph = sum(
            hu.duty for hu in self.heat_utilities if hu.duty > 0.0
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
                T - self._condensation_temperature_K if P is not None else 0.0
            ),
            "Outlet NaOH/(NaOH+H2O)": self._outlet_naoh_wt_frac_naoh_water,
            "Na2CO3 crystals": self._na2co3_crystals_kgph,
            "Na2CO3 solubility extrapolated from 90 C": int(self._na2co3_solubility_extrapolated),
            "Process heat duty": duty,
            "Condenser duty": condenser,
        })
        self._units = {
            "Evaporated water": "kg/hr", "Operating temperature": "K",
            "Operating pressure": "Pa", "Boiling-point elevation": "K",
            "Outlet NaOH/(NaOH+H2O)": "-", "Na2CO3 crystals": "kg/hr",
            "Na2CO3 solubility extrapolated from 90 C": "-",
            "Process heat duty": "kJ/hr", "Condenser duty": "kJ/hr",
        }


class NaOHMakeupMixer(bst.Unit):
    """
    M2: adiabatic dissolution of fresh solid NaOH into the EC1 concentrate.

    The outlet temperature follows from the NaOH(aq) enthalpy model,
    including the heat released by dissolving the solid NaOH. The higher
    NaOH concentration salts out Na2CO3: dissolved Na2CO3 is re-equilibrated
    with the 363.15 K solubility data (used within +/-2 K of 90 C; otherwise
    held at the inlet amount and flagged), and its crystallization enthalpy
    enters the adiabatic balance.

    ins: [0] EC1 slurry concentrate, [1] fresh solid NaOH.
    """

    #: Outlet temperatures within this band of 363.15 K use the 90 C data.
    solubility_temperature_band_K = 2.0

    line = "NaOH makeup mixer"
    _N_ins = 2
    _N_outs = 1

    def _run(self):
        liquor, fresh = self.ins
        out = self.outs[0]
        water, naoh_in, carbonate = _liquor_masses(liquor, self.ID)
        fresh_naoh = float(fresh.imass["NaOH"])
        if float(fresh.F_mass) - fresh_naoh > 1e-12:
            raise RuntimeError(f"{self.ID}: fresh makeup must be pure NaOH.")
        crystals = _solid_na2co3_kgph(liquor)
        naoh_out = naoh_in + fresh_naoh
        h = _naoh.solution_enthalpy_kJ_per_kg
        T_liquor, T_fresh = float(liquor.T), float(fresh.T)

        H_in = (
            (naoh_in + water) * h(naoh_in / (naoh_in + water), T_liquor)
            + fresh_naoh * _naoh.solid_naoh_enthalpy_kJ_per_kg(T_fresh)
        )
        x_out = naoh_out / (naoh_out + water)
        crystallization_kJ_per_kg = -_naoh.NA2CO3_DISSOLUTION_kJ_per_mol / _MW_NA2CO3 * 1e3

        def solve_T(extra_crystals):
            def residual(T):
                return (
                    (naoh_out + water) * h(x_out, T)
                    + _na2co3_sensible_kJph(carbonate, T_liquor, T, liquor.chemicals)
                    + extra_crystals * crystallization_kJ_per_kg
                    - H_in
                )
            # Near saturation the cold solid can cool the liquor; the upper
            # bound is the 204 C limit of the enthalpy correlation.
            return brentq(residual, T_liquor - 40.0, 477.15)

        def equilibrium_crystals(T):
            if abs(T - 363.15) > self.solubility_temperature_band_K:
                return None
            m_naoh = naoh_out / _MW_NAOH * 1e3 / water
            m_sat, solid = _naoh.na2co3_solubility_mol_per_kg_water(m_naoh, 363.15)
            if solid != "Na2CO3":
                return None
            return carbonate - min(carbonate, m_sat * water * _MW_NA2CO3 / 1e3)

        from scipy.optimize import brentq
        T_out = solve_T(0.0)
        new_crystals = crystals
        equilibrated = False
        for _ in range(3):
            eq = equilibrium_crystals(T_out)
            if eq is None:
                break
            new_crystals, equilibrated = eq, True
            T_out = solve_T(new_crystals - crystals)
        boiling_margin = _naoh.water_vapor_pressure_Pa(x_out, T_out) - 101325.0
        if boiling_margin > 0.0:
            raise RuntimeError(
                f"{self.ID}: makeup dissolution would boil the liquor at 1 atm."
            )

        out.empty()
        out.phases = ("l", "s")
        out.imass["l", "Water"] = water
        out.imass["l", "NaOH"] = naoh_out
        out.imass["l", "Na2CO3"] = carbonate - new_crystals
        out.imass["s", "Na2CO3"] = new_crystals
        out.T = T_out
        out.P = 101325.0
        self._outlet_naoh_wt_frac_naoh_water = x_out
        self._dissolution_temperature_rise_K = T_out - T_liquor
        self._na2co3_salted_out_kgph = new_crystals - crystals
        self._na2co3_equilibrated = equilibrated


class ATTHeatRecovery(bst.Facility):
    """
    OPTIONAL heat-integration scenario; never part of the baseline flowsheet.

    After the flowsheet converges, designs the heat-exchanger network with
    ``design_att_heat_exchanger_network`` (baseline DrumDryer, so D0 is not
    integrated) and credits only matches whose temperature feasibility is
    verified on process T-Q curves. This is UTILITY BOOKKEEPING: no
    exchanger units or streams are inserted. The heating utilities of EC1
    and C1 become (process duty - recovered heat + heat loss), with the
    recovery bounded by the process-stream duty; the cooling utilities of
    U3HX, RC1 and the EC1 condenser drop by the recovered heat. Process-side
    duties (HeatUtility.unit_duty, unit attributes) are unchanged and
    exchanger capital is not costed.

    ``att_system`` must be set to the ATT system before simulation.
    """

    network_priority = 0
    _N_ins = 0
    _N_outs = 0

    def _init(self, delta_T_min_K=None):
        self.delta_T_min_K = delta_T_min_K
        self.att_system = None

    def _run(self):
        pass

    def _design(self):
        from biorefineries.sabre.analyses.att.heat_integration import (
            design_att_heat_exchanger_network, _process_side_duties,
            _baseline_heating_utilities, _units_of,
        )
        if self.att_system is None:
            raise RuntimeError(f"{self.ID}: att_system is not set.")
        u = _units_of(self.att_system)
        design = design_att_heat_exchanger_network(
            self.att_system, dryer=None, delta_T_min_K=self.delta_T_min_K
        )
        credited = [m for m in design["matches"] if m["basis"] == "temperature_verified"]
        # Heating: unintegrated utility (process duty + heat loss) minus the
        # recovered heat, which never exceeds the process-stream duty, so the
        # heat-loss allowance stays with the external utility. Cooling:
        # process heat release minus the recovered heat.
        hot_duties = _process_side_duties(u)
        heating_utilities = _baseline_heating_utilities(u)
        recovered = {}
        for m in credited:
            for key in ((m["cold_unit"], "cold"), (m["hot_unit"], "hot")):
                recovered[key] = recovered.get(key, 0.0) + m["duty_kJph"]
        for (ID, kind), Q in recovered.items():
            heating = kind == "cold"
            hus = [hu for hu in getattr(u, ID).heat_utilities
                   if (hu.duty > 0.0 if heating else hu.duty < 0.0)]
            current = abs(sum(hu.duty for hu in hus))
            target = (heating_utilities[ID] if heating else hot_duties[(ID, kind)]) - Q
            if target < -1e-6:
                raise RuntimeError(f"{self.ID}: credited heat exceeds the {ID} baseline duty.")
            if current > 0.0:
                for hu in hus:
                    hu.scale(max(target, 0.0) / current)
        self.hen_design = design
        self.credited_matches = credited
        self.credited_recovery_kJph = sum(m["duty_kJph"] for m in credited)
        self.design_results.update({
            "Credited heat recovery": self.credited_recovery_kJph,
            "Credited matches": len(credited),
            "Exchanger area (unverified U)": sum(m["area_m2_UNVERIFIED_U"] for m in credited),
        })
        self._units = {"Credited heat recovery": "kJ/hr", "Credited matches": "-",
                       "Exchanger area (unverified U)": "m2"}

    def _cost(self):
        pass
