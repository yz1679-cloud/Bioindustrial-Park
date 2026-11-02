# ATT Scenario 1: implementation notes (2026-10-31)

Independent copy of the SaBRe ATT model (`biorefineries/sabre`, branch `sabre`, HEAD `17c75376`), started
from SaBRe Scenario 5. The SaBRe directory was not modified: its 106 files were hashed with SHA-256 before
and after the work, and the two hash lists match.

## Layout

| Path | Content |
|---|---|
| `data/att.yaml` | **Authoritative ATT configuration**: `att.scenarios.att_s1` (flowsheet switches, capacity), `reactor.cases.Ni-CatATT_1to1` (gas yields, NaOH dose), `reactor.material_balance` (carbon closure), `downstream` (C1 0.88) |
| `data/feedstock.yaml`, `tea.yaml`, `att_tea.yaml`, `att_lca.yaml` | Copies of the SaBRe files (unchanged) |
| `units/_att.py`, `system.py` | Process units and flowsheet |
| `analyses/scenarios.py` | `ATT_S1`, `ATT_S2`, `create()`, `scale()`, `tea_config()`, `lca_overrides()` (single source of the scenario assumptions); no run-time parameter patching |
| `analyses/{breakdown,tea,lca,inventory,...}.py` | TEA/LCA/inventory (SaBRe method) |
| `test/` | `test_att_s1_parameters.py` (new) and the adapted SaBRe tests |
| `reference_data/ATT Inputs and Assumptions_261023.xlsx` | Read-only copy (sha256 `db8ff0f4...f949`, identical to the original) |
| `results/` | Default output folder of the runners (`analyses/paths.py`) |

All imports are `biorefineries.ATT.*`. Importing or running ATT loads no `biorefineries.sabre` module; the
test `test_no_sabre_import` checks this.

## Changes from SaBRe Scenario 5

| Item | SaBRe S5 | ATT S1 | Where |
|---|---|---|---|
| Gross NaOH | 1.0 kg/kg **daf** (0.6793 kg/kg dry) | **1.0 kg/kg dry**: the sum of the feedstock solids leaving D0 (`_SARGASSUM_DRY_IDS`); fresh NaOH = gross − recycled | `att.yaml` `naoh_kg_per_kg_dry`; `system.py` `required_gross_naoh_kgph`, recycle seed |
| Gas yields (mmol/g daf) | H2 70.52, CH4 0.70, CO 0.31, CO2 22.68 (team slides) | **54.15 / 0.60 / 0.00 / 0.77** (workbook 261023, Ni-CatATT 1:1); still multiplied by the U2 daf flow | `att.yaml` `gas_yield_mmol_per_g_daf` |
| CO2 override | `scenarios.dose()` rewrote CO2 to 22.68 | removed; `att.yaml` is the only source | `analyses/scenarios.py` |
| Residual organic carbon | extra gas CO2 (+2.24 mmol/g daf) | **solid `Char`** (CH0.5O0.1), PROVISIONAL; switch `residual_carbon_fate: char\|co2` | `units/_att.py` `close_att_u2_balance` |
| H excess of the products | `RuntimeError` | `hydrogen_excess_action: report`: the run is kept, a warning is raised, and `balance_checks()` reports FAIL. No product is added or removed | `units/_att.py` |
| C1 conversion | 0.85 | **0.88**; guard `conversion <= lime_equiv` | `att.yaml`; `CausticizationReactor` |
| Capacity | run time: the dry feed at which SaBRe S4 uses the 92.47 kt/yr waste lime | **fixed at 5029.17 kg dry/h** (the same value, computed once on the unmodified S5 copy); SaBRe S4 is not built | `att.yaml` `scenarios.att_s1.dry_feed_kgph` |
| D0 dryer | `DrumDryer(R=...)` (fails on BioSTEAM 2.53) | `DrumDryer(RH=0.8)`, the same air sizing in the installed API | `system.py` |
| Defaults | PSA on, scrubber off | `psa_enabled: false`, `co2_scrubber.enabled: true` (= ATT S1) | `att.yaml` |
| LCA contributions | the Ca(OH)2 line omitted `scrubber_lime` (latent SaBRe bug; zero effect with waste lime) | both lime streams counted | `analyses/lca.py` |
| Outputs | `<repo>/results/` | `biorefineries/ATT/results/` | `analyses/paths.py` |

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
Diagnostics: `results/validation/u2_ec1_lca_diagnostics_att_s1_1kgph.txt`.

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

Full table: `results/validation/u2_element_balance_att_s1_1kgph.txt` (1 kg/h dry basis).
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
- `analyses/lca.py` (excluded species), `analyses/breakdown.py` (status fields).
- `system.py`: the chemical-set check only.
- `test/test_att_s1_parameters.py`.

**ATT S1, U2, per g daf** (`results/validation/u2_element_balance_att_s1_1kgph_lumped.txt`):
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
- `analyses/tea.py`:
  - `caco3_sales_accounting()` (new): per cake, revenue = fraction × CaCO3 component × price; disposal = the
    tea.yaml solid disposal price × (cake mass − sold CaCO3).
  - `evaluate_att_tea(..., caco3_sales=)` sets each cake's net price, so the revenue enters the DCF once.
  - `_opex_table` splits that net price into "CaCO3 sales: ID" and "CaCO3 cake disposal (non-sold mass): ID"
    and drops the generic whole-cake lines for a sold cake.
- `analyses/breakdown.py`: applies the configuration to ATT S1, adds `caco3_price` and `sys` arguments,
  maps the group "CaCO3 byproduct sales" (cost type "Coproduct revenue"), and adds summary fields.
- `analyses/att_caco3_sales.py` (new): recovery table and price sensitivity. Outputs in `results/tables/`.
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
- `analyses/marine_whr.py`:
  - engine sources at a load, temperature-limited;
  - S1 heat sinks after the HXN;
  - temperature-feasible allocation;
  - itemized equipment;
  - `check_whr`.
- `analyses/marine_tea.py`: floating CAPEX and labor; WHR utility savings and pumps.
- `analyses/marine_lca.py`: incremental GWP.
- `analyses/att_s2_marine.py`: driver; writes `results/tables/att_s2_*.csv`.
- `test/test_att_s2.py`.

**Changed files** (hooks are neutral by default; S1 results unchanged).
- `analyses/tea.py`:
  - `ATTTEA(foc_fixed)` with `_FOC`;
  - `evaluate_att_tea(operating_hours, extra_capital, extra_voc, foc_frac_of_fci, foc_fixed)`;
  - the FCI-factor adjustment is now an itemized capital line.
- `analyses/breakdown.py`: `tea_kwargs` pass-through; WHR and FCI-factor groups; refuses `att_s2` without the
  marine hooks.
- `analyses/scenarios.py`: `ATT_S2` in `OPTIONAL_SCENARIOS`.
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

## Post-review entry-point corrections (after commit 92cc3f0b)

Reproducibility fixes only. The process model, chemistry, inputs, WHR, TEA and LCA assumptions are unchanged, and
so are the S1/S2 results.

**Single source of the scenario assumptions.** `analyses/scenarios.py` now holds all of them:
- `create` / `scale`: flowsheet, capacity and annual basis;
- `tea_config`: waste lime at 0 USD/kg and CaCO3 sales (moved here from `breakdown._build`);
- `lca_overrides`: waste lime is burden-free.

**Entry points corrected.** The following no longer build the reference-scale model (about 49.6 t dry/h, with
purchased lime and no CaCO3 sales). They now use `att_s1` (5029.17 kg dry/h):
- `tea.create_att_tea_system`;
- `tea.export_att_tea`;
- `lca.create_att_lca_system`;
- `lca.export_att_lca`;
- `inventory.build_att_inventory_tables`;
- the 1 kg/h audit comparison;
- `reporting.build_att_documentation`;
- `reporting.build_att_consolidated_results`.

The headline TEA and LCA results apply `tea_config` / `lca_overrides`.

The SaBRe reference-treatment tables are kept and labeled **LEGACY**:
- Case A/B;
- the lime-price cases;
- the "Case-A-consistent" LCA row;
- the old key findings.

The reference-scale model itself is `scenarios.create_legacy_reference()`. A `configuration` argument, or a
`lime_recycle` value that contradicts the scenario, raises an error instead of silently changing S1.

**Output directory.** `analyses/paths.py` reads the `ATT_PROJECT_RESULTS_DIR` environment variable
(`paths.RESULTS_ENV`). `run_att_all --out` now sets the same variable; it previously set `ATT_OUTPUTS_DIR`, which
nothing read. The S1/S2 table scripts (`analyses/att_*.py`) write to `output_dir("tables")`. The default location
is unchanged: `biorefineries/ATT/results/tables`.

**S2 engine load.** `marine_tea.operating_modes()` returns the hours and the `engine_load` of Modes A and B
(`marine_whr.yaml`), and `att_s2_marine.mode_tea_cases()` passes that load to `evaluate_case`. Both modes are at
0.75 MCR, so the published results are unchanged.

**DCF: inherited BioSTEAM behaviour, kept on purpose.** BioSTEAM 2.53.11 deducts the whole loan payment,
principal included, from taxable cash flow. The original SaBRe `_tea.py` (17c75376) inherits this method and does
not override it. ATT keeps it so that the results stay consistent with SaBRe. This is a methodology-consistency
decision, not a claim that loan principal is tax deductible. Loans, financing, tax, NPV and the MSP solver are
unchanged.

An independent DCF recalculation estimated these MSP values under the alternative tax treatment (USD/kg H2).
They are independently estimated alternative DCF values, not outputs of the runtime model:

| Case | Current model | Alternative tax treatment |
|---|---:|---:|
| S1 | 3.029244 | 3.050088 |
| S2 WHR, 7920 h | 3.204215 | 3.232048 |
| S2 WHR, 2640 h | 5.136015 | 5.219512 |

**Deferred: U2 feed-preheat accounting.** The conceptual U2 feed preheater is credited as a reduction in U2
furnace duty equal to its sensible heat × (1 + heat loss). This mixes physical duty with furnace-equivalent
displacement. The issue is not resolved here because the current allocation gives the preheater 0 kW, so S2 results
are unaffected. Revisit it if a future version assigns recovered heat to U2 preheating.

Tests: `test/test_att_entry_points.py` (new; S1 entry points vs `build_att_breakdown`, output root, S2 engine load).

## Targeted F2 washing and boundary/check fixes

Scope: only ATT source/config/tests. Existing entry-point corrections, frozen
reaction chemistry, S1/S2 capacity, marine sources/multipliers/hours, DCF and carbon
credit methods are retained.

- Replaced the old optional material-only W2 (which recycled wash liquor to SP1)
  with native W2 MixTank plus F2R RotaryVacuumFilter. washing_on is now default;
  scenarios.create(washing="washing_off") selects the original flowsheet.
- Wash water = 1 kg/kg original F2 dry cake (all non-water components). Fresh water
  is 298.15 K; native adiabatic mixing. Contact time 0.25 h is a configurable ENG
  sizing assumption, not measured kinetics. NaOH and Na2CO3 are dissolved; CaCO3
  and Ca(OH)2 are retained as solids with no additional reaction/dissolution.
- Refiltration retains representative diluted mother liquor at the original F2
  moisture. If S is retained insoluble mass, W water, D dissolved non-water mass
  and x target water fraction, retained liquor fraction r = x*S/((1-x)*W-x*D).
  Thus sodium removal follows dilution/refiltration, never an arbitrary 100% split.
- Final product ID remains caco3_cake. F2 wash filtrate has its own wastewater
  outlet; the original F2 filtrate/SP1/EC1 loop and F3 remain unchanged.
- Native tank/filter costs and power roll into the process FCI/utilities. Wash
  water uses the existing process-water price/CF; wash liquid uses the existing
  wastewater price/CF and H2SO4 neutralization endpoint (OH -> water,
  CO3 -> HCO3, one H+ each). No new wastewater factor or treatment plant.
- f2_sales=False means zero F2 saleable fraction and whole wet F2 cake disposal;
  F3 sales are retained. Default 100 USD/t CaCO3 is explicitly optimistic and
  unverified. Both operating configurations and both commercial boundaries are
  exported by analyses/att_washing.py.
- inventory.get_att_external_flows excludes only the component-empty u3_tail_gas
  placeholder when it appears as a no-PSA feed. Any nonzero flow still undergoes
  normal documented-boundary checks.
- reporting._consistency now includes both lime and scrubber_lime. Actual TEA
  pricing and LCA activities already included both; dosing/factors were not changed.
- Added native washing/component conservation, independent reference-value,
  conservative-sales, placeholder and lime-check regressions. The old exact
  topology test explicitly selects washing_off; neutralization tests include
  the separate washing purge.
- Inherited sold-CaCO3 landfill storage credits remain unchanged and conditional.
  Soluble carbonate moved from cake to wastewater changes its modeled routing;
  no new storage credit is assigned to the wash liquid.

### Validated targeted-change results

At 5029.17 kg dry/h and 7920 h/yr:
- F2 dry CaCO3 purity: 77.0308% washing_off -> 82.5451% washing_on; insoluble-only
  upper bound 84.3831%. CaCO3 5586.568 kg/h and Ca(OH)2 1033.911 kg/h retained.
- Fresh wash water 7252.384 kg/h; washed cake 9023.869 wet / 6767.902 dry kg/h.
  Remaining NaOH 124.863 and Na2CO3 22.560 kg/h. Wash filtrate 7898.359 kg/h:
  water 7413.878, NaOH 410.343, Na2CO3 74.139 kg/h. Sodium removal 76.6701%.
- W2 tank volume 3.849986 m3, purchase 27818.57 USD, installed 45900.65 USD,
  power 0.379224 kW. F2R area 149.225853 ft2 (13.863535 m2), purchase
  251644.11 USD, installed 536100.53 USD, power 28.781298 kW.
- Combined installed capital +582001.17 USD; S2 process increment +727501.47 USD
  after the existing floating multiplier. No engine/WHR change.
- Optimistic MSP: S1 3.229398, S2 WHR 7920 h 3.415723, S2 WHR 2640 h 5.437067 USD/kg H2.
  No-F2-sales MSP (F3 sales retained): 5.326657 / 5.512982 / 7.534326 USD/kg H2.
- S1 GWP 14.243019; S2 WHR 12.852612 kg CO2e/kg H2. Increment +0.198737:
  electricity +0.035109, H2SO4 +0.064085, water +0.008946, wastewater +0.008048,
  reduced inherited carbonate-storage credit +0.082549. Credit METHOD unchanged.
- washing_off reproduces the six requested S1/S2 numerical references.
- Final complete test discovery: 111 tests, zero failures/errors/skips (existing 96
  plus 15 native washing/regression tests). Additional exported component checks: 88 PASS.
  Logs: results/validation/logs/washing_final_validation.log.
- run_att_all was executed: Steps 1-5 passed; Step 6 documentation stopped on the
  pre-existing missing preprocessing.yaml registry reference. The Step-1 water QC
  separately exposes a pre-existing omission of SCRUB reaction-water generation
  (-0.009328859 kg/h on the 1 kg dry/h basis). Neither is suppressed. Permission
  for those two additional report-only corrections was requested because the user
  explicitly restricted implementation to three tasks; they remain unmodified.
  The SVG and PNG diagram steps were independently executed successfully.
- The two requested bugs are fixed: empty no-PSA placeholder exclusion and the
  lime + scrubber_lime consistency check (PASS, 1.0701183803 kg/kg dry).
- SABRE's 106 tracked source files have the same aggregate SHA256 before/after;
  HEAD remains 92cc3f0b. No installed BioSTEAM source, DCF, commit or push changed.

## Finalization: CaCO3 sales and carbonate storage accounting (after commit 26981907)

Accounting only. The flowsheet, units, washing, WHR, TEA prices, DCF, H2 and every physical stream are unchanged,
and so is every MSP.

**What was inconsistent.** The TEA sells the CaCO3 of the F2 and F3 cakes (`att_tea.yaml caco3_sales`). The LCA
still treated both cakes as landfilled and credited all of their carbon as permanently stored. That is 773.98 kg
C/h, or -7.6046 kg CO2e/kg H2 with washing on:

| Credited carbon | kg C/h | Credit, kg CO2e/kg H2 |
|---|---:|---:|
| CaCO3, F2 and F3 (sold in the TEA) | 701.70 | -6.894 |
| Soluble Na2CO3 in landfilled solids | 72.28 | -0.710 |

The same CaCO3 therefore earned both revenue and a storage credit, and the GWP did not depend on whether F2 was
sold.

The credited carbon is biogenic. The feed has no carbonate, and the lime and NaOH carry no carbon. The plant
carbon balance closes. The F2 wash-liquor carbonate (8.40 kg C/h) goes to wastewater and is not credited.

**Fix: `att_lca.yaml carbon_storage.carbonate_storage_accounting`.**
- `conservative` (the baseline) credits only CaCO3 that is physically landfilled, meaning cake CaCO3 not sold under
  the TEA disposition.
  - Sold CaCO3 gets no storage credit and no substitution credit.
  - Soluble Na2CO3 gets no storage credit.
- `inherited` gives the previous result and is kept as an optimistic comparison:
  - `GWP_inherited_carbonate_credit_kgCO2e_per_kg_H2` in the breakdown and S2 rows;
  - `lca.get_att_stored_carbon_credit(..., accounting="inherited")`.

`lca.apply_att_gwp(caco3_sales=...)` receives the case's TEA disposition from `breakdown`. The sold share comes
from one helper, `lca.caco3_saleable_fraction`, which `tea.caco3_sales_accounting` also uses.

**TEA sales calculation.** No unit separates CaCO3 from the cake. The revenue/disposal split is a net price on the
whole wet cake: the CaCO3 content times the price, minus `disposal_solid` times the non-CaCO3 mass. It is not double
counted. It remains an upper-bound case, and "no F2 sales" is the conservative case.

**Results (washing on, kg CO2e/kg H2).**

| Case | Conservative, F2+F3 sold | Conservative, no F2 sales | Inherited (comparison) |
|---|---:|---:|---:|
| S1 | 21.847577 | 15.260492 | 14.243019 |
| S2 with WHR (7920 h or 2640 h) | 20.457170 | 13.870086 | 12.852612 |

- WHR contributes -1.390407 kg CO2e/kg H2.
- Washing adds +0.116188 under conservative accounting and +0.198737 under inherited accounting. In the inherited
  case, 0.082549 of that came from removing Na2CO3 that had been credited.

Tests: `test/test_att_carbon_accounting.py` (new). In `test_att_washing_integration.py`, the 12.653875 reference
now applies to the inherited column, and the conservative value is asserted beside it.
