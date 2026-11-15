# ATT S1/S2: process basis, material balance and energy balance

This document records the process basis: the flowsheet, the inputs and their evidence, the balances the model checks and
the energy accounting. It contains no results; the flows, duties and costs come from the model and are in the generated
tables (see "Where the results are" at the end).

The baseline splits the seaweed ash into insoluble minerals and soluble NaCl/KCl, keeps an insoluble char of 0.15 g per g
of dry feed, removes the salts from the NaOH recycle in a crystallizer (XL1), washes the F2 cake and the F1 char cake with
the recycled condensate, dries and sells the CaCO3 cakes, recovers rare earths from the char (HCl leach, oxalate
precipitation, roast of the precipitate; default on), assumes that the leached char has a net price of 0, and credits the
Sargassum carbon of the solids in the LCA. Inputs are marked:
- **[ASSUMPTION]**: an engineering or user-defined input;
- **[EXP]**: an experimental input;
- **[LIT]**: a literature input;
- **[DERIVED]**: a hand calculation from other inputs.

Basis: 7,920 h/yr (330 d × 24 h).

Companion documents:
- `ATT_S1_S2_TEA.md`
- `ATT_S1_S2_LCA.md`
- `ATT_S1_S2_DESIGN_BASIS_AND_LIMITATIONS.md`

## 1. Scenarios and system boundaries

| | ATT S1 (`att_s1`) | ATT S2 (`att_s2`) |
|---|---|---|
| Location | Land-based plant | Existing bulk carrier, retrofitted |
| Process | ATT flowsheet below | **Identical** process, chemistry, capacity and yields |
| Added layer | — | Marine waste-heat recovery (WHR) from the main engine; floating CAPEX and labor factors |
| Inside the boundary | Presscake receipt → drying (D0) → ATT reactor (U2) → gas cooling, CO2 scrubbing (SCRUB/F3), drying, compression (U3K) → char split (RS1) → residue filtration (F1) → F1 washing (W1/F1R) → REE leach and oxalate precipitation (LC1) → roaster (RO1) → causticization (C1) → CaCO3 filtration (F2) → F2 washing (W2/F2R) → CaCO3 cake drying (D2, D3) → NaOH evaporation (EC1) and salt crystallizer (XL1) → recycle; wash-liquor and leachate recycles; purchased utilities; CaCO3 and REE sales; wastewater and solid disposal | Same, plus WHR equipment (economizer, recovery coolers, pumps) |
| Outside the boundary | Harvesting, collection, initial dewatering, transport, presscake production, vessel acquisition, propulsion fuel |

S1 and S2 use the same simulated process. Their gas yields, H2 output and material flows are identical. S2
differs only in its accounting layers: WHR heat supply, floating CAPEX/labor factors and operating hours.

## 2. Feedstock and experimental gas yields

### 2.1 Feed basis

| Quantity | Value | Basis |
|---|---|---|
| Moisture | 76.3 wt % | [LIT] NLR preprint, pressed solids, 23.7 % solids |
| **Dry feed** | **5,029.17 kg/h** (120.70 t/d) | [ASSUMPTION] SaBRe S5 waste-lime scale, fixed |
| Wet presscake | dry feed / (1 − moisture) | [DERIVED] |
| Ash | 32.07 wt % of the dry feed; split into insoluble Ash minerals, NaCl, KCl and REO | [LIT] NLR preprint, pressed solids (15 psi); the split is an expectation from typical seaweed major elements, not a measurement [ASSUMPTION] |
| **Dry ash-free (daf) feed** | dry feed × (1 − 0.3207) | [DERIVED], equal to the U2 internal value |
| D0 outlet moisture | 50 wt % | [ASSUMPTION] workbook 261005; press + D0 design |

### 2.2 Experimental gas yields (Ni-CatATT, Sargassum:NaOH = 1:1)

**Source.** Experimental workbook `ATT Inputs and Assumptions_261023.xlsx`:
- sheet "1. Gas Yield (Ni-ATT)", row 5;
- author Gyudae Sim, last modified 2026-10-24;
- SHA-256 `db8ff0f4…f949`, identical in `reference_data/` and in the user's Downloads.

**Conditions:**
- 0.25 g Ni-soaked Sargassum and 0.25 g NaOH;
- 500 °C with a 1 h hold;
- N2 at 25 mL/min and steam at 0.03 mL/min;
- 10 wt % Ni/ZrO2 catalyst downstream of the sample.

**Basis:** mmol of gas per g dry ash-free seaweed.

The 1:2 case (row 6) is **not** used.

| Gas | Workbook 261023 (1:1) | Rounded (Oct-2026 correspondence, as relayed) | Model YAML (`att.yaml reactor.cases.Ni-CatATT_1to1`) | Status |
|---|---:|---:|---:|---|
| H2 | 54.15 (D5) | ≈ 54.2 | 54.15 | Directly verified against the workbook; consistent with the rounded report |
| CH4 | 0.6 (E5) | ≈ 0.6 | 0.60 | Directly verified against the workbook; consistent with the rounded report |
| CO2 | 0.77 (G5) | ≈ 0.8 | 0.77 | Directly verified against the workbook; consistent with the rounded report |
| CO | 0 (F5) | not reported | 0.00 | The workbook value is 0. Whether this is a measured zero or a non-detect, and the detection limit, are **not documented**: unable to verify |

All values are in mmol/g daf.

Notes on the evidence:
- The workbook is the experimental team's **summary table**. It gives no replicates, uncertainty or raw GC data,
  so "directly verified" means verified against that table, not against raw chromatograms.
- The October 2026 correspondence is not available locally (no .msg/.eml file found). Its relayed values agree
  with the workbook after rounding to one decimal.
- The 1:2 case values were never used.

### 2.3 How the gas production is implemented and checked

The H2, CH4, CO2 and CO of the U2 outlet are the yields above times the daf feed; `test_att_independent_checks.py`
recomputes the H2 product by hand from the daf feed, the yield and the molar mass, and the composition of the product gas
(H2, the CH4 that passes, and the CO2 that the scrubber does not capture). The raw ATT gas is about 98 mol % H2 on a dry,
N2-free basis, consistent with the reported "≈ 98 % H2". There is no PSA: all of the U2 H2 is recovered.

Implementation trace (no discrepancy found):
- `att.yaml` (`baseline_case: Ni-CatATT_1to1`) → `scenarios._spec` → `ATTReactor.reported_gas_yield_mmol_per_g_daf`.
- In `units/_att.py`, `ATTReactor._run` computes `daf = Σ dry Sargassum solids − (Ash + NaCl + KCl + REO)` from its own inlet stream
  (water excluded), then `kmol/h = y [mmol/g] × daf [kg/h] / 1000`.
- The yields are never scaled: gas scale factor 1.0, `ignored_reported_gas_yields_mmol_per_g_daf: {}`.
- The 76.3 % moisture is used once, to build the wet feed. U2 excludes all inlet water (the D0 moisture and the recycle
  liquor water).
- No SaBRe S5 values (H2 70.52, CO2 22.68) and no 1:2 values appear in any code path. SaBRe's `dose()` override
  was removed.
- No PSA recovery factor is applied: `psa_enabled: false`, and there is no U3P unit.
- S1 and S2 call the same `scenarios.create`. Their U2 outputs are identical to machine precision.

**Conclusion: the ATT S1/S2 baseline gas yields are consistent with the available experimental data on the stated
daf basis.**

Conditions of that statement (see the design-basis document): the yields were measured on Ni-soaked raw seaweed
(ash 17.2 wt % dry) with an ex-situ Ni/ZrO2 catalyst and a steam co-feed. The model transfers them **per g daf** to
presscake (ash 32.07 %) and does not model or cost the Ni impregnation, the catalyst or the lab steam co-feed.

## 3. Process chemistry and recycle (key inputs)

| Item | Value | Class |
|---|---|---|
| U2 temperature | 500 °C | [EXP] workbook B13 / experiment |
| NaOH dose (gross, fresh + recycled) | 1.0 kg/kg dry feed; the gross dose includes the recycled NaOH | Experimental ratio confirmed 2026-11-06 on total dry seaweed |
| NaOH → Na2CO3 in U2 | 100 % | [EXP] workbook B15 (stated assumption) |
| Residual organic carbon | Lumped residue CH0.5O1.195 (0.590 g/g daf) in U2; RS1 keeps 0.15 g insoluble char per g dry feed (ash minerals, CharN, CharS and organic Char) and the rest is `att_residue_untracked` (no credit, no cost) | [ASSUMPTION] elemental-closure surrogate, not measured; char yield from the collaborator's mass balance |
| Causticization (C1) | 88 % conversion; Ca(OH)2:Na2CO3 = 1.1 mol/mol | [EXP] workbook B16–B17 ("commercial causticizing") and the CaCO3 experiment (88.3 %) |
| CO2 scrubber | 99 % capture with Ca(OH)2 (1.1× excess); filter F3 | [ASSUMPTION] preliminary |
| Liquor recycle | 95 % to EC1 (5 % purge); EC1 concentrates NaOH to 50 wt % | [ASSUMPTION] / workbook B19 |
| F2 washing | Condensate (the part the dissolver does not need) at 1.0 kg/kg original dry cake, 0.25 h, one ideal mixing stage plus refiltration (W2 MixTank + F2R rotary vacuum filter). All CaCO3/Ca(OH)2 retained; dissolved Na is diluted in the wash liquor, which is recycled to the dissolver D1 | [ASSUMPTION] engineering |
| F1 washing | Same ratio (1.0 kg/kg dry cake), the condensate left after the dissolver and the F2 wash (fresh water for the rest), W1 MixTank + F1R pressure filter at the 30 wt % F1 cake moisture, no dryer. The wash liquor joins the F1 filtrate (the carbonate solution to C1) | [ASSUMPTION] user decision 2026-11-02 |
| Lime source | Waste carbide lime of an acetylene plant, free and burden-free: a paste with 92 % Ca(OH)2, 4 % CaCO3, 4 % inert minerals (dry basis) and 40 wt % water. The Ca(OH)2 dose follows the stoichiometry | [ASSUMPTION] from literature ranges (`att.yaml waste_lime`) |
| Condensate use | The EC1, U3C and scrubber condensate is the dissolution water first (3 kg per kg of U2 Na2CO3, less the recycled F2 wash water), then the F2 wash water, then the F1 wash water. The REE leach takes its water next; the rest is wastewater | [ASSUMPTION] |
| CaCO3 cake drying | The F2 cake (D2) and the scrubber cake (D3) are dried from 25 to 1 wt % moisture in steam-heated drum dryers (same type, drum temperature and exhaust humidity as D0). No grinding or purification | [ASSUMPTION] user decision 2026-11-03; the moisture target is assumed |
| CaCO3 cakes and ATT residue | Both dried CaCO3 cakes are sold at 100 USD/t of CaCO3; the leached char cake (30 wt % moisture) has a net price of 0 (assumed to be taken as a sorbent) | [ASSUMPTION] |
| Ash split | Insoluble share 0.3838, NaCl 0.2377, KCl 0.3785 of the ash; the soluble salts dissolve with the Na2CO3 | [ASSUMPTION] illustrative major-element basis, not the collaborators' sample |
| Salt crystallizer (XL1) | Removes 99 % of the NaCl and KCl from the EC1 concentrate (vessel 2 h + solids centrifuge); the cake keeps 10 wt % liquor; disposed at 0.04 USD/kg | [ASSUMPTION] preliminary, no solubility data |
| REE recovery (LC1, RO1) | HCl 0.5 mmol/g char, 5 kg leach liquor/kg char, oxalic acid 0.042 mmol/g char (lab doses); product REO = 60 % of the REE of the initial wastewater (1.4 mg TREE/L at 2.5 g seaweed/L), capped by the oxalate stoichiometry (1.5 mol/mol REE); 1.31 wt % REO after the roast (900 °C, only the precipitate); the capture section is not modeled | [ASSUMPTION] / [EXP] lab doses |

## 4. Material balance (S1 = S2)

The model reports the mass flow of every stream, with its composition. The streams are:

- **Inputs:** the wet presscake; fresh NaOH (solid; a makeup of the gross dose); the carbide lime paste to C1 and to the
  scrubber (Ca(OH)2, CaCO3, inert minerals and water); 31 wt % HCl and oxalic acid for the REE recovery; fresh process
  water (zero in the baseline: the dissolution, wash and leach water is condensate); dryer air and roaster air.
- **Internal recycles:** the NaOH recycle from XL1; the F2 wash liquor to D1; the F1 wash liquor to C1 (with the F1
  filtrate); the spent leachate to D1; the condensate pool (EC1, U3C, scrubber), distributed to D1, the F2 wash, the F1
  wash and the REE leach.
- **Outputs:** the H2 product gas (H2, CH4, a little CO2); the F2 washed CaCO3 cake (dried in D2, sold) and the F3 scrubber
  CaCO3 cake (dried in D3, sold), each with its CaCO3 purity on a dry basis, calculated and never forced; the ATT residue
  (leached char cake, 30 wt % moisture, not dried); the REE product (roasted oxalate precipitate, with mineral filler); the
  salt cake (XL1); `att_residue_untracked` (RS1); the liquor purge; the excess condensate; the cake dryer exhaust; the
  gas-dryer water (U3D); the leach CO2 and the roaster exhaust (vented); and the off-flowsheet H2SO4 for the neutralization
  of the purge (pH 8.3).

**RS1 and the char.** U2 makes the lumped residue (ResidueCH + ResidueCHO). RS1 keeps the insoluble char at 0.15 g per g of
dry feed: the ash minerals (after the REO carve-out), CharN, CharS and organic Char. The remaining lumped residue is
`att_residue_untracked`. The atoms leaving never exceed the atoms entering, but the carbon balance is not closed on
measured sinks (user decision 2026-11-03).

**Washing.** The F2 wash lowers the sodium (NaOH + Na2CO3) of the cake and raises its CaCO3 purity toward the theoretical
maximum with the Ca(OH)2 and inert minerals retained; the F1 wash lowers the sodium of the char cake, and the recovered
sodium (mostly Na2CO3) is causticized in C1. The experimental ≈ 97 % purity (workbook sheet 2, 20 mL water + 5 g Na2CO3 +
3.49 g Ca(OH)2) is a different, clean lab system. The model purity is calculated, never forced.

**REE leach.** The leach liquor is 5 kg per kg of char solids; the HCl is neutralized by the Na2CO3 and NaOH of the cake
liquor (the CO2 is vented). The oxalate precipitate is roasted; the leached char and its unrecovered REO leave as the
residue.

**Balance checks.** The model checks, and the tests enforce:
- U2 C, H, O and electron closure and the U2 mass error (`test_att_s1_parameters.py`);
- the whole-flowsheet mass and element balance, from the feed and product streams only (`test_att_independent_checks.py`);
- the component and total balances of the W2/F2R and W1/F1R washing steps (`test_att_washing_integration.py`);
- the EC1 and NaOH loop balances (`test_att_ec1_naoh_evaporator.py`);
- the plant Na, Ca, K, Cl and carbon balances, which close (the carbon balance includes the lime's CaCO3 and
  `att_residue_untracked`).

The exported QC tables are listed in `results/validation/run_summary.md`. The lumped residue that enables the H/O/electron
closure is an assumed surrogate (see the design-basis document).

## 5. Energy balance (S1)

The model reports, per kg of dry feed and in kW:
- the U2 process heat (including the reaction enthalpy), which is **provisional** because it depends on the lumped-residue
  thermochemistry; the U2 heat delivered (with the 5 % loss), which is the natural-gas agent duty; and the U2 natural-gas
  fuel (LHV, burner efficiency 0.90);
- the LP-steam gross demand, by unit: EC1 (evaporates the NaOH liquor), D0, D2 and D3 (dryers), C1, U3D (dryer
  regeneration);
- the LP steam recovered by the heat-exchanger network (HXN), which matches 11 exchangers: D0, D2, D3, C1, EC1
  (evaporator, condenser), U3HX, the U3K intercooler, the U3D regeneration heater and cooler and the scrubber cooler. U2,
  RC1 and the REE roaster RO1 are not matched;
- the LP steam purchased, and the boiler natural gas for it (LHV, boiler efficiency 0.80);
- the roaster RO1 natural gas (heater duty), counted with the U2 gas in the LCA;
- the external heating before WHR (U2 plus purchased steam), which is the basis of the S2 reduction;
- the electricity of the unit models, and the electricity of the cooling tower and pumps (an estimate derived from the GWP
  line);
- the net heat removed by cooling water.

**[DERIVED] Energy intensity.** Total natural-gas fuel (U2 plus boiler) per kg H2 and the LHV of the H2 product are derived
from these. Drying (D0, D2 and D3) and the NaOH evaporation (EC1) dominate the steam demand; U2 dominates the direct fuel.
The REE chain adds little energy (the power of LC1 and RO1 and the gas of RO1).

## 6. S2 marine waste-heat recovery (75 % MCR reference)

**Reference vessel:** SPAR PYXIS. Main engine MAN B&W 5S60ME-C8.2, 8,050 kW rated, 6,037.5 kW shaft at 75 %.

Engine data are engineering estimates (no OEM part-load data). Existing onboard heat users are ignored, so the
available heat is an optimistic upper bound.

| Source | Medium | Temperatures |
|---|---|---|
| Exhaust gas | LP steam, 4 bar(a) | 240 °C down to ≥ 160 °C |
| Scavenge/charge air | HT hot water 95/85 °C | 160 °C |
| Jacket water (30 % recoverable) | LT hot water 80/70 °C | 85 °C |

The model computes, for each source, the gross heat, the recoverable heat, the heat delivered at the 0.9 effectiveness and
the heat utilized. The heat is allocated to the sinks with a 10 K minimum approach; the jacket-water loop finds no sink that
is cold enough.

The WHR offsets only purchased LP steam that remains after the S1 HXN, so heat is never counted twice. The U2
500 °C reaction heat is not eligible. The conceptual U2 feed preheater receives no heat. The WHR pumps add electricity.

**Engine-load cases:** 0.15, 0.50, 0.75 (reference) and 1.00 of the rated load. Below 50 % load (slow collection,
anchoring) no qualifying heat is assumed.

**Operating hours.** The S2 results are for 7,920 h/yr underway at 75 % MCR (idealized). The hourly balances are the
same at any operating hours; only the annual quantities scale.

## Where the results are

Generate them with the project interpreter; all go to the git-ignored `results/` folder:
- `python -m biorefineries.ATT.analyses.run all` (use `--skip-tests` to skip the unit tests): the 1 kg/h audit, the
  inventory (mass, element, water and energy balances, utilities), the TEA and LCA workbooks and the validation summary;
- `python -m biorefineries.ATT.analyses.comprehensive_report`: the S1, S2 and S3 report with `mass_balance.csv`,
  `energy_balance.csv` and `process_summary.csv`;
- `analyses/s2_marine.py`: the S2 WHR tables.
