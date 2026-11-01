# ATT Scenario 1: implementation notes (2026-10-31)

Independent copy of the SaBRe ATT model (`biorefineries/sabre`, branch `sabre`, HEAD `17c75376`), started
from SaBRe Scenario 5. The SaBRe directory was not modified: its 106 files were hashed with SHA-256 before
and after the work, and the two hash lists match.

## Layout

| Path | Content |
|---|---|
| `data/att.yaml` | **Authoritative ATT configuration**: `att.scenarios.att_s1` (flowsheet switches, capacity), `reactor.cases.Ni-CatATT_1to1` (gas yields, NaOH dose), `reactor.material_balance` (carbon closure), `downstream` (C1 0.88) |
| `data/feedstock.yaml`, `tea.yaml`, `att_tea.yaml`, `att_lca.yaml` | Copies of the SaBRe files (unchanged) |
| `units/_att.py`, `systems/_att_system.py` | Process units and flowsheet |
| `analyses/att/scenarios.py` | `ATT_S1`, `create()`; no run-time parameter patching |
| `analyses/att/{breakdown,tea,lca,inventory,...}.py` | TEA/LCA/inventory (SaBRe method) |
| `test/` | `test_att_s1_parameters.py` (new) and the adapted SaBRe tests |
| `reference_data/ATT Inputs and Assumptions_261023.xlsx` | Read-only copy (sha256 `db8ff0f4...f949`, identical to the original) |
| `README_SABRE_ATT_original.md` | SaBRe ATT README, for reference only (describes SaBRe, not ATT S1) |
| `outputs/` | Default output folder of the runners (`analyses/att/paths.py`) |

All imports are `biorefineries.ATT.*`. Importing or running ATT loads no `biorefineries.sabre` module; the
test `test_no_sabre_import` checks this.

## Changes from SaBRe Scenario 5

| Item | SaBRe S5 | ATT S1 | Where |
|---|---|---|---|
| Gross NaOH | 1.0 kg/kg **daf** (0.6793 kg/kg dry) | **1.0 kg/kg dry**: the sum of the feedstock solids leaving D0 (`_SARGASSUM_DRY_IDS`); fresh NaOH = gross − recycled | `att.yaml` `naoh_kg_per_kg_dry`; `_att_system.py` `required_gross_naoh_kgph`, recycle seed |
| Gas yields (mmol/g daf) | H2 70.52, CH4 0.70, CO 0.31, CO2 22.68 (team slides) | **54.15 / 0.60 / 0.00 / 0.77** (workbook 261023, Ni-CatATT 1:1); still multiplied by the U2 daf flow | `att.yaml` `gas_yield_mmol_per_g_daf` |
| CO2 override | `scenarios.dose()` rewrote CO2 to 22.68 | removed; `att.yaml` is the only source | `analyses/att/scenarios.py` |
| Residual organic carbon | extra gas CO2 (+2.24 mmol/g daf) | **solid `Char`** (CH0.5O0.1), PROVISIONAL; switch `residual_carbon_fate: char\|co2` | `units/_att.py` `close_att_u2_balance` |
| H excess of the products | `RuntimeError` | `hydrogen_excess_action: report`: the run is kept, a warning is raised, and `balance_checks()` reports FAIL. No product is added or removed | `units/_att.py` |
| C1 conversion | 0.85 | **0.88**; guard `conversion <= lime_equiv` | `att.yaml`; `CausticizationReactor` |
| Capacity | run time: the dry feed at which SaBRe S4 uses the 92.47 kt/yr waste lime | **fixed at 5029.17 kg dry/h** (the same value, computed once on the unmodified S5 copy); SaBRe S4 is not built | `att.yaml` `scenarios.att_s1.dry_feed_kgph` |
| D0 dryer | `DrumDryer(R=...)` (fails on BioSTEAM 2.53) | `DrumDryer(RH=0.8)`, the same air sizing in the installed API | `_att_system.py` |
| Defaults | PSA on, scrubber off | `psa_enabled: false`, `co2_scrubber.enabled: true` (= ATT S1) | `att.yaml` |
| LCA contributions | the Ca(OH)2 line omitted `scrubber_lime` (latent SaBRe bug; zero effect with waste lime) | both lime streams counted | `analyses/att/lca.py` |
| Outputs | `<repo>/att_outputs/` | `biorefineries/ATT/outputs/` | `analyses/att/paths.py` |

**Unchanged from SaBRe S5:**
- Feed: presscake `nlr_pressed`, 76.3 % moisture, ash 32.07 wt % dry; no P1; D0 dries to 50 %; U2 at 500 C.
- Chemistry and recycle: Ca(OH)2/Na2CO3 1.1; NaOH→Na2CO3 100 %; dissolution water 3 kg/kg Na2CO3; EC1 at NaOH/(NaOH+H2O) = 0.5; 95 % liquor recycle (5 % purge).
- CO2 scrubber: 99 % capture, lime excess 1.1. No PSA.
- Waste lime: free and burden-free; CaCO3 cakes disposed (no CaCO3 revenue).
- Heat losses 5 % and the emission factors are kept from workbook 261005, which still lists them; 261023 removed them.
- TEA/LCA method as in SaBRe. REE/Nd data are not modeled.

## Results (simulated, BioSTEAM 2.53.11 in `.venv`)

Per kg dry presscake (1 kg/h, no HXN). The S5 column is the unmodified SaBRe S5 copy with only the D0 RH fix.

| | SaBRe S5 | ATT S1 |
|---|---|---|
| Gross / fresh / recycled NaOH [kg] | 0.6793 / 0.1608 / 0.5185 | 1.0000 / 0.2348 / 0.7652 |
| U2 gas H2 / CH4 / CO / CO2 [mmol/g daf] | 70.52 / 0.70 / 0.31 / 24.92 | 54.15 / 0.60 / 0.00 / 0.77 |
| U2 dry gas H2 [mol %] | 73.1 | 97.53 |
| Char [kg] | 0 | 0.179 (0.263 g/g daf; 48.6 % of feed organic C) |
| U2 H residual (products − feed) [mmol H/g daf] | −5.2 | **+40.9 (FAIL)** |
| U2 mass-balance error | −0.10 % | **+0.68 % (FAIL, limit 0.5 %)** |
| U2 heat duty [MJ] | 7.97 | 8.16 (see issue 1) |
| C1 conversion (realized) | 0.85 | 0.88 |
| Ca(OH)2: C1 / scrubber [kg] | 0.743 / 1.366 | 1.060 / 0.042 |
| F2 cake CaCO3/(CaCO3+Ca(OH)2) [mass] | 82.1 % | 84.4 % |
| Purge Na2CO3 / NaOH [kg] | 0.0064 / 0.0273 | 0.0073 / 0.0403 |
| EC1 water evaporated [kg] / heat [MJ] | 1.75 / 4.18 | 2.46 / 5.89 |
| H2 product [kg] / purity [mol %] | 0.0966 / 98.25 | 0.0742 / 98.89 |

ATT S1 at full capacity (5029.17 kg dry/h = 120.7 t/d, with HXN):
- H2: 2,954 t/yr
- MSP: 4.80 USD/kg H2
- FCI: 11.35 MUSD
- Fresh NaOH: 9,353 t/yr
- Ca(OH)2: 43.9 kt/yr (supply 92.5 kt/yr)
- GWP: **4.59 kg CO2e/kg H2 net**. This includes **−15.2** for carbon stored in the landfilled solids (char and carbonates); without that credit it is about 19.8.

SaBRe S5 was not run at full scale for comparison.

Tests (`python -m unittest discover -s biorefineries/ATT/test -p "test_att_*.py" -t .` from the repo root):
72 run, 71 pass. The one failure, `test_u2_checks_pass`, is the unresolved U2 hydrogen balance below; it is
intentionally kept failing. Not run: the `test/run_att_*.py` export scripts and `analyses/att_scenarios.py`.

## Open issues that affect ATT S1

1. **U2 hydrogen and electron balance is unresolved.** The measured gases (113.1 mmol e⁻/g daf) plus the
   residual carbon as char (+80.2) exceed the feed organics (152.5). As a result:
   - the identified products hold 40.9 mmol H/g daf more H than the feed;
   - the mass-balance error is +0.68 %;
   - the H excess is worth about 5.8 kJ/g daf (H2 HHV), i.e. about 4.0 MJ/kg dry, against a U2 duty of 8.2 MJ/kg dry.

   **The U2 heat duty, and the MSP/GWP that depend on it, are therefore not reliable.** Resolving this needs
   data the workbook does not give: char yield and composition, tars, liquid organics, or the carbonate held by
   the ash cations (K, Ca, Mg).
2. **Char is provisional.** CH0.5O0.1 with Hf from the Channiwala-Parikh correlation and Cp 1 J/g/K. It also
   drives most of the LCA stored-carbon credit (−15.2 kg CO2e/kg H2) and the ash/char cake disposal cost
   (0.46 USD/kg H2).
3. **Gas yields are transferred per g daf** from the experimental seaweed (ash 17.2 %) to the presscake
   (ash 32.07 %). The mass basis of the 0.25 g seaweed in the experiment is not stated.
4. **Capacity is the SaBRe S5 waste-lime scale.** It is not re-derived for ATT S1, whose lime use is
   43.9 kt/yr, well inside the 92.5 kt/yr supply.
5. **EC1 constants were not re-derived.** `ec1_boiling_point_elevation_K`, `ec1_na2co3_dissolved_fraction` and
   `naoh_heat_of_solution_kJ_per_kg` were tuned for the S5 liquor; the higher NaOH dose changes the EC1 feed.
6. **Environment.** BioSTEAM 2.53.11 (`.venv`) is used through the `RH` argument of the D0 dryer. SaBRe
   itself does not run in this environment (`DrumDryer(R=...)`).
