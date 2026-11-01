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
- GWP (superseded by the targeted repair below): 4.59 kg CO2e/kg H2 net, including −15.2 for carbon stored in
  landfilled char and carbonates; about 19.8 without any storage credit.

SaBRe S5 was not run at full scale for comparison.

Tests (`python -m unittest discover -s biorefineries/ATT/test -p "test_att_*.py" -t .` from the repo root):
72 run, 71 pass. The one failure, `test_u2_checks_pass`, is the unresolved U2 hydrogen balance below; it is
intentionally kept failing. Not run: the `test/run_att_*.py` export scripts and `analyses/att_scenarios.py`.

## Targeted repair (after commit 76fc5527)

Scope: the measured gas yields, NaOH 1 kg/kg dry, C1 0.88, feed, capacity and flowsheet are all unchanged.
Diagnostics: `outputs/validation/u2_ec1_lca_diagnostics_att_s1_1kgph.txt`.

**U2 (no code error found).**
- Per g daf: C, O, N, S and Na close exactly. Feed organics reproduce the presscake CHN (C 46.16, H 5.71, N 1.72 % of daf).
- The carbonate is 18.40 mmol formed in U2 plus 1.92 mmol recycled.
- The char has MW 14.115, HHV 32.7 MJ/kg and Cp 1.0 J/g/K, as specified.
- The whole residual is hydrogen: +40.88 mmol H/g daf. That is 0.0280 kg/h at the 1 kg/h basis, i.e. the full
  +0.676 % mass error.
- It equals the electron excess: gases 113.10 + char 80.24 against feed organics 152.47. Closure would need the
  18.66 mmol/g daf of residual carbon to carry 2.11 available e⁻ per C; CH0.5O0.1 carries 4.30. So the residual
  carbon must be about half as oxidized as CO2/carbonate, e.g. organic acids or carbonate of the ash cations, and
  none of these was measured.
- Because the measured gases have a fixed CO2, the closure cannot be chosen uniquely from the available data.
  Nothing was changed to force it.
- Only diagnostics were added to `balance_checks()`: C/O/electron residuals under the existing standards, the
  e⁻/C needed for closure, gases + char HHV ratio (0.85, PASS), and the U2 duty labeled PROVISIONAL.

**U2 energy.**
- The routine is consistent: Hess re-referencing of the feed to HHV, and char Hf from its HHV.
- The excess H effectively burns hydrogen the feed does not supply into product water. The duty is therefore
  probably too low, by an amount on the order of 4.9-5.8 kJ/g daf (H2 LHV-HHV), i.e. 3.4-4.0 MJ/kg dry, against
  8.16 MJ/kg dry. It is kept as computed and labeled PROVISIONAL; no correction is applied.

**EC1.** Within the stated ranges, so nothing was changed:
- feed NaOH/(NaOH+H2O) 0.181 (heat of solution valid ≤ ~0.20);
- outlet 0.434 (BPE valid 0.40-0.46);
- carbonate load 0.138 kg Na2CO3/kg outlet water vs 0.18 baseline. By the yaml's scaling note the dissolved
  fraction would be ≈ 0.065 instead of 0.05. That is inside its 0.05-0.11 range and has a negligible mass and
  energy effect, so it was left unchanged.

**LCA storage credit.**
- Conversion 44.0095/12.011 is correct; no double counting. Biogenic emissions are 0, there is no uptake credit,
  and feed C = stored + H2-product C + purge C.
- Char carbon was 0.152 of the 0.308 kg C/kg dry credited.
- The char's quantity is not supported (the U2 electron balance) and its landfill permanence is not supported, so
  it is now excluded from the net credit: `att_lca.yaml carbon_storage.credit_char_carbon: false`,
  `lca._stored_carbon_kgph(sys, include_char)`.
- Carbonates (CaCO3, entrained Na2CO3) stay credited. The char-inclusive value is reported for comparison only.

Full scale, before → after:

| Item | Before | After |
|---|---|---|
| H2 | 2,954 t/yr | 2,954 t/yr |
| MSP | 4.80 USD/kg | 4.80 USD/kg (PROVISIONAL) |
| U2 duty | 8.16 MJ/kg dry | 8.16 MJ/kg dry (PROVISIONAL) |
| Ca(OH)2 | 43.9 kt/yr | 43.9 kt/yr |
| NaOH recycled / fresh | 30,478 / 9,353 t/yr | 30,478 / 9,353 t/yr |
| Net GWP | 4.59 | **12.12** kg CO2e/kg H2 |
| Storage credit in net | −15.21 (char + carbonates) | **−7.69** (carbonates) |
| GWP, no storage credit | 19.80 | 19.80 |
| GWP with provisional char credit | — | 4.59 (comparison only) |

Tests: 75 run, 74 pass. The new tests cover flowsheet invariance, the C/O diagnostics and char exclusion; the one
failure is `test_u2_checks_pass` (U2 H/electron balance), unchanged standard.

Status: **operational, with an unresolved U2 elemental/energy balance**. U2 duty, MSP and GWP are provisional;
nothing is experimentally validated.

## Open issues that affect ATT S1

1. **U2 hydrogen and electron balance is unresolved.** The measured gases (113.1 mmol e⁻/g daf) plus the
   residual carbon as char (+80.2) exceed the feed organics (152.5). As a result:
   - the identified products hold 40.9 mmol H/g daf more H than the feed;
   - the mass-balance error is +0.68 %;
   - the H excess is worth about 5.8 kJ/g daf (H2 HHV), i.e. about 4.0 MJ/kg dry, against a U2 duty of 8.2 MJ/kg dry.

   **The U2 heat duty, and the MSP/GWP that depend on it, are therefore not reliable.** Resolving this needs
   data the workbook does not give: char yield and composition, tars, liquid organics, or the carbonate held by
   the ash cations (K, Ca, Mg).
2. **Char is provisional.** CH0.5O0.1 with Hf from the Channiwala-Parikh correlation and Cp 1 J/g/K. It sets the
   ash/char cake disposal cost (0.46 USD/kg H2). Its carbon is no longer credited as stored in the net GWP (see
   "Targeted repair"); with that credit the GWP would be 4.59 instead of 12.12 kg CO2e/kg H2.
3. **Gas yields are transferred per g daf** from the experimental seaweed (ash 17.2 %) to the presscake
   (ash 32.07 %). The mass basis of the 0.25 g seaweed in the experiment is not stated.
4. **Capacity is the SaBRe S5 waste-lime scale.** It is not re-derived for ATT S1, whose lime use is
   43.9 kt/yr, well inside the 92.5 kt/yr supply.
5. **EC1 constants were not re-derived.** `ec1_boiling_point_elevation_K`, `ec1_na2co3_dissolved_fraction` and
   `naoh_heat_of_solution_kJ_per_kg` were tuned for the S5 liquor. The ATT S1 EC1 state is inside their stated
   ranges (see "Targeted repair"); the dissolved fraction would scale to about 0.065 (negligible effect).
6. **Environment.** BioSTEAM 2.53.11 (`.venv`) is used through the `RH` argument of the D0 dryer. SaBRe
   itself does not run in this environment (`DrumDryer(R=...)`).

## U2 elemental-balance investigation (second pass, no model change)

Full table: `outputs/validation/u2_element_balance_att_s1_1kgph.txt` (1 kg/h dry basis).
- U2 reacts only `ins[0]`. The tail-gas inlet is furnace fuel and is empty without a PSA.
- C, O, N, S and Na close exactly. H is +40.877 mmol/g daf (+9.7 % of the H fed); that mass, 0.02799 kg/h, is
  the whole +0.676 % mass error.
- The electron residual is +40.877 with either convention (C/H/O, or with N as NH3).
- Water/steam (0 e⁻) and 2 NaOH → Na2CO3 (−2 → −2) are electron-neutral, so neither moisture, steam nor the
  sodium cycle can explain it.
- The measured gases use 74.2 % of the feed's reducing power (113.10 of 152.47). The excess comes only from
  assigning all residual carbon (18.66 mmol/g daf) to char-like CH0.5O0.1 (4.30 e⁻/C, against 2.11 available).

No coding error was found. Closure would need about 51 % of that carbon (9.5 mmol/g daf) in a fully oxidized form
that is not in the measured gas CO2. Candidates: carbonate of the ash cations, dissolved organic acids (formate
2 e⁻/C), or an O-rich residue. None is supported by data, so none was implemented.

Measurements needed to close it:
- solid residue yield with CHNO and total inorganic carbon;
- dissolved organic/inorganic carbon and its speciation in the residue leachate (D1/F1 liquor);
- condensable liquids/tar;
- the run's water balance;
- CHNO and ash of the experimental seaweed.

Status unchanged: operational; U2 elemental balance unresolved; U2 duty, MSP and GWP PROVISIONAL.

## Lumped residual product: stoichiometrically closed baseline (supersedes the char closure)

**What changed.** The organic carbon not in the measured gases or the carbonate now leaves U2 as a
**lumped residual product CH0.5O_b**: an ASSUMED stoichiometric surrogate, not measured char.
- a = 0.5 is assumed (`att.yaml reactor.material_balance.lumped_residue.H_per_C`).
- b is solved by U2 from its own C/H/O balance: product water closes H, b closes O.
- It is carried as two basis pseudo-components with the same H/C, `ResidueCH` (CH0.5) and `ResidueCHO`
  (CH0.5O2). Their sum is the one product.
- Hf uses the existing Channiwala-Parikh route. It is linear in element mass fractions, so the sum equals the
  correlation at CH0.5O_b, but O-rich compositions are outside its validation range.
- Cp 1 J/g/K; solid.
- Routed with the solids: U2 residue → RC1 → D1 → F1 → ash_residue_cake. This is an assumption; part of such
  oxidized carbon may be soluble in reality.
- No revenue, no heating-value credit, and no storage credit
  (`att_lca.yaml provisional_residue_species`, `credit_char_carbon: false`).
- `residual_carbon_fate: char | co2` remain selectable.

**Files.**
- `_chemicals.py`: the two basis species.
- `units/_att.py`: `close_att_u2_balance` ('lumped' branch, raises if water < 0 or b outside 0-2);
  `ATTReactor._init`/`_run` (residue bookkeeping and solved formula); `_att_u2_balance_checks`.
- `data/att.yaml`, `data/att_lca.yaml`.
- `analyses/att/lca.py` (excluded species), `analyses/att/breakdown.py` (status fields).
- `systems/_att_system.py`: the chemical-set check only.
- `test/test_att_s1_parameters.py`.

**ATT S1, U2, per g daf** (`outputs/validation/u2_element_balance_att_s1_1kgph_lumped.txt`):
- All residuals are 0: C 40.297, H 420.305, O 234.778, N 1.227, S 0.026, Na 40.531. Mass error 3e-9;
  electron residual ~1e-13. All PASS under the unchanged standards.
- Solved formula **CH0.5O1.1953** (2.109 available e⁻/C); residual C 18.661 mmol.
- Lumped residue 0.590 g/g daf (0.401 kg/kg dry).
- Water 163.43 in → 150.14 out (13.29 mmol consumed).
- No negative flows anywhere.
- Gas yields exactly 54.15 / 0.60 / 0.00 / 0.77.

**Full scale.**

| Item | Char closure (H unresolved) | Lumped closure |
|---|---|---|
| H2 | 2,954 t/yr | 2,954 t/yr |
| Fresh NaOH | 9,353 t/yr | 10,263 t/yr |
| Recycled NaOH | 30,478 t/yr | 29,568 t/yr |
| Ca(OH)2 | 43.9 kt/yr | 42.6 kt/yr |
| U2 duty | 8.16 MJ/kg dry | 9.07 MJ/kg dry |
| MSP | 4.80 USD/kg | 5.22 USD/kg |
| FCI | 11.35 MUSD | 11.89 MUSD |
| Net GWP | 12.12 | 14.04 kg CO2e/kg H2 |
| GWP, no storage credit | 19.80 | 21.73 |
| GWP with residue credit (comparison only) | 4.59 | 6.52 |

Fresh NaOH rises because the larger ash/residue cake (1.22 kg/kg dry) carries more liquor.

Tests: 75/75 pass, with the standards unchanged.

Status: elementally and materially balanced under the assumed lumped-residue composition. Mass flows follow
from the measured gases plus that assumption. U2 duty, MSP and GWP are PROVISIONAL: they depend on the
surrogate's composition, Hf, phase and routing. Nothing is experimentally validated.

## CaCO3 byproduct sales in the TEA (after commit 72fdffac)

**Scope.** TEA only. The process model, U2 (lumped residue), the balances, the gas yields and the LCA are
unchanged.

**Configuration.** `att_tea.yaml tea.caco3_sales`: `enabled: true`, `streams: [caco3_cake, scrubber_cake]`,
`saleable_fraction: 1.0`, `price_usd_per_metric_ton: 100`, `disposal_of_sold_caco3: false`,
`dispose_non_caco3_mass: true`, sensitivity prices 0 / 100 / 315.
- The legacy SaBRe Case B table (`caco3_coproduct`, 250/50 USD/t) is labeled as a sensitivity only.

**Code.**
- `analyses/att/tea.py`:
  - `caco3_sales_accounting()` (new): per cake, revenue = fraction × CaCO3 component × price; disposal = the
    tea.yaml solid disposal price × (cake mass − sold CaCO3).
  - `evaluate_att_tea(..., caco3_sales=)` sets each cake's net price, so the revenue enters the DCF once.
  - `_opex_table` splits that net price into "CaCO3 sales: ID" and "CaCO3 cake disposal (non-sold mass): ID"
    and drops the generic whole-cake lines for a sold cake.
- `analyses/att/breakdown.py`: applies the configuration to ATT S1, adds `caco3_price` and `sys` arguments,
  maps the group "CaCO3 byproduct sales" (cost type "Coproduct revenue"), and adds summary fields.
- `analyses/att_caco3_sales.py` (new): recovery table and price sensitivity. Outputs in `outputs/tables/`.
- Tests: `test/test_att_breakdown.py` (reconciliation including the revenue; `test_caco3_sales_counted_once`).

**Recovered CaCO3 at capacity** (component mass; the upstream slurries are internal and not counted):

| Cake | CaCO3 [kg/h] | Wet [kg/h] | Dry [kg/h] | Dry-basis purity | Other content [kg/h] |
|---|---|---|---|---|---|
| F2 | 5,586.6 | 9,669.8 | 7,252.4 | 77.0 % (84.4 % of CaCO3 + Ca(OH)2) | water 2,417.5, Ca(OH)2 1,033.9, NaOH 535.2, Na2CO3 96.7 |
| F3 | 260.7 | 373.3 | 279.9 | 93.1 % | water 93.3, Ca(OH)2 19.3 |
| Total | 5,847.2 | 10,043.1 | 7,532.3 | 77.6 % | — |

The total is 46,310 t/yr. The experimental ~97 % (by Ca content, stoichiometric lime) is a different quantity.

**TEA results** (H2 2,954 t/yr, FCI 11.89 MUSD, all PROVISIONAL):

| Case | CaCO3 revenue | CaCO3-cake disposal | AOC | MSP |
|---|---|---|---|---|
| Previous (whole cakes disposed) | 0 | 3.18 MUSD/yr | 13.89 MUSD/yr | 5.22 USD/kg |
| 0 USD/t | 0 | 1.33 | 12.04 | 4.60 |
| **100 USD/t (baseline)** | 4.63 | 1.33 | 7.41 | **3.03** |
| 315 USD/t | 14.59 | 1.33 | −2.55 | −0.34 |

At 315 USD/t the CaCO3 revenue exceeds all costs, so the H2 MSP is negative.

**Limitations.**
- The cake is assumed sold as recovered: wet, 77 % CaCO3 on a dry basis, with Ca(OH)2 and NaOH/Na2CO3. No
  washing, drying, classification, packaging, transport, market-size or offtake constraint is modeled.
- 100 % saleable fraction; industrial grade only.
- Prices are assumptions.

**Future LCA issue (not changed).** The LCA still credits the carbon of `caco3_cake` and `scrubber_cake` as
permanently stored in a landfill (`att_lca.yaml landfill_streams`). If the CaCO3 is sold, that storage claim
depends on the product's end use: a sale does not prove permanent storage. The net GWP (14.04 kg CO2e/kg H2) is
unchanged and remains PROVISIONAL.

## ATT Scenario 2: shipboard ATT with marine waste heat recovery (uncommitted, on top of fc690650)

S2 (`att_s2`) is the unchanged S1 process with two accounting layers on top: marine waste heat recovery (WHR)
and the floating TEA.

**Design basis and sources:** `docs/ATT_S2_DESIGN_BASIS.md` and `docs/ATT_S2_REFERENCES.md`.

**New files.**
- `data/marine_whr.yaml`, `data/marine_tea.yaml`.
- `analyses/att/marine_whr.py`:
  - engine sources at a load, temperature-limited;
  - S1 heat sinks after the HXN;
  - temperature-feasible allocation;
  - itemized equipment;
  - `check_whr`.
- `analyses/att/marine_tea.py`: floating CAPEX and labor; WHR utility savings and pumps.
- `analyses/att/marine_lca.py`: incremental GWP.
- `analyses/att_s2_marine.py`: driver; writes `outputs/tables/att_s2_*.csv`.
- `test/test_att_s2.py`.

**Changed files** (hooks are neutral by default; S1 results unchanged).
- `analyses/att/tea.py`:
  - `ATTTEA(foc_fixed)` with `_FOC`;
  - `evaluate_att_tea(operating_hours, extra_capital, extra_voc, foc_frac_of_fci, foc_fixed)`;
  - the FCI-factor adjustment is now an itemized capital line.
- `analyses/att/breakdown.py`: `tea_kwargs` pass-through; WHR and FCI-factor groups; refuses `att_s2` without the
  marine hooks.
- `analyses/att/scenarios.py`: `ATT_S2` in `OPTIONAL_SCENARIOS`.
- `data/att.yaml`: `scenarios.att_s2`.

**Key results** (all PROVISIONAL):
- WHR delivers 1.99 MW and 1.86 MW is used: 8.2 % of external heating, 20 % of purchased LP steam. The U2 fired
  duty is not eligible.
- WHR equipment: 1.01 MUSD; pumps 10.8 kW.
- MSP in USD/kg H2:

  | Case | MSP |
  |---|---|
  | S1 land | 3.03 |
  | S2 floating, no WHR, 7920 h | 3.26 |
  | S2 floating with WHR, 7920 h | 3.20 |
  | S2 floating with WHR, 2640 h (Mode B) | 5.14 |
  | S2 floating, no WHR, 2640 h | 5.09 |

- Incremental process GWP: 14.04 → 12.7 kg CO2e/kg H2.

Tests: 84 run, all pass.
