# ATT S1/S2: process basis, material balance and energy balance

**Model state.** BioSTEAM 2.54.0. The baseline washes the F2 cake and the F1 residue cake with the recycled
condensate, dries and sells the CaCO3 cakes, assumes that the washed residue pays its disposal, and credits the Sargassum carbon of
the solids in the LCA. All values are simulation outputs of the committed model unless marked:
- **[ASSUMPTION]**: an engineering or user-defined input;
- **[EXP]**: an experimental input;
- **[DERIVED]**: a hand calculation from model outputs.

Basis: 7920 h/yr (330 d × 24 h).

Companion documents:
- `ATT_S1_S2_TEA_FINAL.md`
- `ATT_S1_S2_LCA_FINAL.md`
- `ATT_S1_S2_DESIGN_BASIS_AND_LIMITATIONS.md`

## 1. Scenarios and system boundaries

| | ATT S1 (`att_s1`) | ATT S2 (`att_s2`) |
|---|---|---|
| Location | Land-based plant | Existing bulk carrier, retrofitted |
| Process | ATT flowsheet below | **Identical** process, chemistry, capacity and yields |
| Added layer | — | Marine waste-heat recovery (WHR) from the main engine; floating CAPEX and labor factors |
| Inside the boundary | Presscake receipt → drying (D0) → ATT reactor (U2) → gas cooling, CO2 scrubbing (SCRUB/F3), drying, compression (U3K) → residue filtration (F1) → F1 washing (W1/F1R) → causticization (C1) → CaCO3 filtration (F2) → F2 washing (W2/F2R) → CaCO3 cake drying (D2, D3) → NaOH evaporation and recycle (EC1); wash-liquor recycles; purchased utilities; CaCO3 sales; wastewater and solid disposal | Same, plus WHR equipment (economizer, recovery coolers, pumps) |
| Outside the boundary | Harvesting, collection, initial dewatering, transport, presscake production, vessel acquisition, propulsion fuel |

S1 and S2 use the same simulated process. Their gas yields, H2 output and material flows are identical. S2
differs only in its accounting layers: WHR heat supply, floating CAPEX/labor factors and operating hours.

## 2. Feedstock and experimental gas yields

### 2.1 Feed basis

| Quantity | Value | Basis |
|---|---:|---|
| Wet presscake | 21,220.13 kg/h | DERIVED from dry feed / (1 − moisture) |
| Moisture | 76.3 wt % (16,190.96 kg/h) | [LIT] NLR preprint, pressed solids, 23.7 % solids |
| **Dry feed** | **5,029.17 kg/h** (120.70 t/d; 39,831 t/yr) | [ASSUMPTION] SaBRe S5 waste-lime scale, fixed |
| Ash | 32.07 wt % dry (1,612.86 kg/h) | [LIT] NLR preprint, pressed solids (15 psi) |
| **Dry ash-free (daf) feed** | **3,416.315 kg/h** = 5,029.17 × (1 − 0.3207) | DERIVED, equal to the U2 internal value |
| D0 outlet moisture | 50 wt % (D0 evaporates 11,161.8 kg/h of water) | [ASSUMPTION] workbook 261005; press + D0 design |

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

The 1:2 case (row 6: H2 63.24, CH4 2.21, CO 0.02, CO2 0.34) is **not** used.

| Gas | Workbook 261023 (1:1) | Rounded (Oct-2026 correspondence, as relayed) | Model YAML (`att.yaml reactor.cases.Ni-CatATT_1to1`) | Simulated U2 outlet | Difference | Status |
|---|---:|---:|---:|---:|---:|---|
| H2 | 54.15 (D5) | ≈ 54.2 | 54.15 | 54.150000 | 0 | Directly verified against the workbook; consistent with the rounded report |
| CH4 | 0.6 (E5) | ≈ 0.6 | 0.60 | 0.600000 | 0 | Directly verified against the workbook; consistent with the rounded report |
| CO2 | 0.77 (G5) | ≈ 0.8 | 0.77 | 0.770000 | 0 | Directly verified against the workbook; consistent with the rounded report |
| CO | 0 (F5) | not reported | 0.00 | 0 | 0 | The workbook value is 0. Whether this is a measured zero or a non-detect, and the detection limit, are **not documented**: unable to verify |

All values are in mmol/g daf.

Notes on the evidence:
- The workbook is the experimental team's **summary table**. It gives no replicates, uncertainty or raw GC data,
  so "directly verified" means verified against that table, not against raw chromatograms.
- The October 2026 correspondence is not available locally (no .msg/.eml file found). Its relayed values agree
  with the workbook after rounding to one decimal.
- The 1:2 case values were never used.

### 2.3 Gas production check

| Quantity | Independent calculation | Simulated | Status |
|---|---:|---:|---|
| Dry feed | 5,029.17 kg/h | 5,029.17 kg/h (U2 inlet, water excluded) | Match |
| daf feed | 5,029.17 × 0.6793 = 3,416.315 kg/h | 3,416.315181 kg/h | Match |
| H2 | 54.15 mol/kg × 3,416.315 kg/h = 184.993 kmol/h → × 2.01588 = **372.925 kg/h** | 372.924630 kg/h | Match |
| CH4 | 2.04979 kmol/h = 32.884 kg/h | 32.8837 kg/h | Match |
| CO2 | 2.63056 kmol/h = 115.77 kg/h | 2.63056 kmol/h | Match |
| CO | 0 | 0 | Match |
| Annual H2 | 372.925 × 7920 / 1000 = **2,953.563 t/yr** | 2,953.563072 t/yr | Match |
| Raw ATT gas, dry and N2-free | H2 / (H2 + CH4 + CO + CO2) = 54.15 / 55.52 = 97.53 mol % | 97.53 mol % | Consistent with the reported "≈ 98 % H2" |
| H2 product gas (after CO2 scrubbing and drying, 2 MPa) | — | 98.89 mol % H2, 1.10 % CH4, 0.014 % CO2 | No PSA; H2 recovery 100 % of the U2 H2 |

Implementation trace (no discrepancy found):
- `att.yaml` (`baseline_case: Ni-CatATT_1to1`) → `scenarios._spec` → `ATTReactor.reported_gas_yield_mmol_per_g_daf`.
- In `units/_att.py`, `ATTReactor._run` computes `daf = Σ dry Sargassum solids − Ash` from its own inlet stream
  (water excluded), then `kmol/h = y [mmol/g] × daf [kg/h] / 1000`.
- The yields are never scaled: gas scale factor 1.0, `ignored_reported_gas_yields_mmol_per_g_daf: {}`.
- The 76.3 % moisture is used once, to build the wet feed. U2 excludes all inlet water (10,058 kg/h: 50 % D0
  moisture plus recycle liquor water).
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
| NaOH dose (gross, fresh + recycled) | 1.0 kg/kg dry feed = 5,029.17 kg/h (1.472 kg/kg daf) | [ASSUMPTION] user decision 2026-10-31. The experiment's seaweed mass basis is not stated |
| NaOH → Na2CO3 in U2 | 100 % | [EXP] workbook B15 (stated assumption) |
| Residual organic carbon | Lumped residue CH0.5O1.195, 0.590 g/g daf (2,017 kg/h), 48.6 % of feed organic C | [ASSUMPTION] elemental-closure surrogate, not measured |
| Causticization (C1) | 88 % conversion; Ca(OH)2:Na2CO3 = 1.1 mol/mol | [EXP] workbook B16–B17 ("commercial causticizing") and the CaCO3 experiment (88.3 %) |
| CO2 scrubber | 99 % capture with Ca(OH)2 (1.1× excess); filter F3 | [ASSUMPTION] preliminary |
| Liquor recycle | 95 % to EC1 (5 % purge); EC1 concentrates NaOH to 50 wt % | [ASSUMPTION] / workbook B19 |
| F2 washing | Condensate (the part the dissolver does not need) at 1.0 kg/kg original dry cake, 0.25 h, one ideal mixing stage plus refiltration (W2 MixTank + F2R rotary vacuum filter). All CaCO3/Ca(OH)2 retained; dissolved Na is diluted in the wash liquor, which is recycled to the dissolver D1 | [ASSUMPTION] engineering |
| F1 washing | Same ratio (1.0 kg/kg dry cake), the condensate left after the dissolver and the F2 wash (fresh water for the rest), W1 MixTank + F1R pressure filter at the 30 wt % F1 cake moisture, no dryer. The wash liquor joins the F1 filtrate (the carbonate solution to C1) | [ASSUMPTION] user decision 2026-11-02 |
| Lime source | Waste carbide lime of an acetylene plant, free and burden-free: a paste with 92 % Ca(OH)2, 4 % CaCO3, 4 % inert minerals (dry basis) and 40 wt % water. The Ca(OH)2 dose follows the stoichiometry | [ASSUMPTION] from literature ranges (`att.yaml waste_lime`) |
| Condensate use | The EC1, U3C and scrubber condensate is the dissolution water first (3 kg per kg of U2 Na2CO3, less the recycled F2 wash water), then the F2 wash water, then the F1 wash water. The rest (2.5 t/h) is wastewater | [ASSUMPTION] |
| CaCO3 cake drying | The F2 cake (D2) and the scrubber cake (D3) are dried from 25 to 1 wt % moisture in steam-heated drum dryers (same type, drum temperature and exhaust humidity as D0). No grinding or purification | [ASSUMPTION] user decision 2026-11-03; the moisture target is assumed |
| CaCO3 cakes and ATT residue | Both dried CaCO3 cakes are sold at 100 USD/t of CaCO3; the washed F1 residue cake (30 wt % moisture) pays its own disposal (net 0) | [ASSUMPTION] |

## 4. Material balance (S1 = S2)

| Stream | kg/h | t/yr | Composition / note |
|---|---:|---:|---|
| **Inputs** | | | |
| Presscake (wet) | 21,220.13 | 168,063 | 5,029.17 kg/h dry |
| Fresh NaOH (solid) | 533.66 | 4,226.6 | Makeup = 10.6 % of the gross dose |
| Carbide lime paste to C1 | 10,189.6 | 80,701.8 | Ca(OH)2 5,624.67, CaCO3 244.55, inert minerals 244.55, water 4,075.85 |
| Carbide lime paste to the scrubber | 384.52 | 3,045.4 | Ca(OH)2 212.25, CaCO3 9.23, inert minerals 9.23, water 153.81 |
| Total Ca(OH)2 | 5,836.92 | **46,228.4** | Within the 92.5 kt/yr waste-lime supply (Ca(OH)2 basis) |
| Fresh process water (dissolution, scrubber makeup, F2 and F1 wash) | 0 | 0 | The wash and dissolution water is condensate |
| Dryer air (D0 ≈ 54,700; D2 ≈ 12,400; D3 ≈ 470) | ≈ 67,560 | — | Ambient |
| **Internal recycles** | | | |
| NaOH recycle from EC1 | 10,279.31 | — | NaOH 4,495.51 (**35,604.6 t/yr**), Na2CO3 754.63, water 5,029.17; effective NaOH recovery 89.4 % |
| F2 wash liquor to D1 | 8,863.23 | 70,196.8 | NaOH 379.27, Na2CO3 63.66, water 8,420.30 |
| F1 wash liquor to C1 (with the F1 filtrate) | 5,039.75 | 39,914.8 | NaOH 23.30, Na2CO3 459.60, water 4,556.85 |
| Condensate pool (EC1, U3C, scrubber) | 28,995.5 | — | To D1 13,833.8; to the F2 wash 8,272.7; to the F1 wash 4,349.9; excess 2,539.2 |
| **Outputs** | | | |
| H2 product gas | 406.97 | — | H2 372.925 (**2,953.56 t/yr**), CH4 32.884, CO2 1.158 |
| F2 washed CaCO3 cake (dried in D2, sold) | 7,908.81 | 62,637.8 | CaCO3 6,322.95 (50,077.7 t/yr), Ca(OH)2 1,124.93, inert minerals 244.55, NaOH 117.56, Na2CO3 19.73, water 79.09 (1 wt %; D2 evaporates 2,530.8 kg/h); **80.756 %** CaCO3 dry basis |
| F3 scrubber CaCO3 cake (dried in D3, sold) | 301.42 | 2,387.2 | CaCO3 269.88 (2,137.5 t/yr), Ca(OH)2 19.30, inert minerals 9.23, water 3.01 (D3 evaporates 96.5 kg/h); **90.441 %** CaCO3 dry basis |
| Total CaCO3 sold | 6,592.83 | **52,215.2** | Includes the CaCO3 of the lime (253.8 kg/h); solids fully retained (an assumption) |
| ATT residue (washed F1 cake) | 5,524.29 | 43,752.4 | Ash 1,612.85, lumped residue 2,017.00, CharN/CharS 61.52, Na2CO3 167.15, NaOH 8.47, water 1,657.29 (30 wt %); not dried |
| Liquor purge | 1,589.57 | 12,589.4 | NaOH 236.61, Na2CO3 39.72, water 1,313.25 |
| Excess condensate | 2,539.18 | 20,110.3 | Wastewater (clean water) |
| Cake dryer exhaust (D2 + D3) | 15,499.3 | 122,754 | Air 12,872.1 and water vapor 2,627.3; no GHG |
| Gas-dryer water (U3D) | 268.62 | 2,127.5 | Wastewater |
| H2SO4 for neutralization (purge, pH 8.3) | 308.5 | 2,443 | Off-flowsheet reagent |

**Washing performance:**
- F2: sodium (NaOH + Na2CO3) in the cake falls from 580.2 to 137.3 kg/h (−76.3 %). CaCO3 purity rises from 76.432 %
  to 80.756 % (dry basis). The theoretical maximum with the Ca(OH)2 and inert minerals retained is ≈ 82.20 %.
- F1: sodium in the residue cake falls from 658.5 to 175.6 kg/h (−73.3 %), and the recovered sodium (mostly Na2CO3) is
  causticized in C1.
- The experimental ≈ 97 % purity (workbook sheet 2, 20 mL water + 5 g Na2CO3 + 3.49 g Ca(OH)2) is a different,
  clean lab system. The model purity is calculated, never forced.

**Balance status (all PASS):**
- U2 C, H, O and electron closure: residuals ≤ 1e-13 mmol/g daf.
- U2 mass error 3.0e-9.
- Plant Na, Ca and carbon balances close (carbon: 1,607.53 kg C/h in = out, including the lime's CaCO3).
- The component and total checks on the W2/F2R and W1/F1R washing steps pass. The exported QC tables have 324 PASS and
  0 FAIL.

The lumped residue that enables the H/O/electron closure is an assumed surrogate (see the design-basis document).

## 5. Energy balance (S1)

| Item | kW | MJ/kg dry | Note |
|---|---:|---:|---|
| U2 process heat (incl. reaction enthalpy) | 12,893 | 9.229 | Provisional: depends on the lumped-residue thermochemistry |
| U2 heat delivered (incl. 5 % loss) = natural gas agent duty | 13,537 | 9.69 | |
| U2 natural gas fuel (LHV, burner 0.90) | 15,042 | 10.77 | |
| LP steam, gross demand (D0 9,289; EC1 13,263; D2 1,909; C1 1,517; U3D 112; D3 78) | 26,168 | — | EC1 evaporates 19.9 t/h of water; the cake dryers D2 and D3 add 1,987 kW |
| LP steam recovered by the heat-exchanger network (HXN) | −9,392 | — | Unchanged by the cake dryers |
| **LP steam purchased** | **16,776** | 12.01 | |
| Boiler natural gas for that steam (LHV, boiler 0.80) | 20,970 | 15.01 | |
| **External heating before WHR** (U2 + purchased steam) | **30,313** | — | Basis of the S2 reduction |
| Electricity, unit models (U3K 678, F1 282, F1R 251, D0 410, D2 121, F2 77, F2R 32, D3 14, other 17) | 1,880 | 0.374 kWh/kg | |
| Electricity, cooling tower and pumps (estimate) | 176 | 0.035 kWh/kg | |
| Cooling water, net heat removed | 15,747 | 11.27 | |

**[DERIVED] Energy intensity:**
- Total natural gas fuel is ≈ 36.0 MW LHV, or 348 MJ per kg H2.
- The H2 product carries 12.43 MW LHV.
- Drying (D0, D2 and D3) and NaOH evaporation (EC1) dominate the steam demand. The wash waters add to the EC1 load.
  U2 dominates direct fuel.

## 6. S2 marine waste-heat recovery (75 % MCR reference)

**Reference vessel:** SPAR PYXIS. Main engine MAN B&W 5S60ME-C8.2, 8,050 kW rated, 6,037.5 kW shaft at 75 %.

Engine data are engineering estimates (no OEM part-load data). Existing onboard heat users are ignored, so the
available heat is an optimistic upper bound.

| Source | Medium | Gross kW | Recoverable kW | Delivered kW (η 0.9) | Utilized kW |
|---|---|---:|---:|---:|---:|
| Exhaust gas (240 → ≥ 160 °C) | LP steam, 4 bar(a) | 3,115.4 | 1,159.2 | 1,043.3 | 1,043.3 |
| Scavenge/charge air (160 °C) | HT hot water 95/85 °C | 1,591.3 | 862.0 | 775.8 | 775.8 |
| Jacket water (85 °C; 30 % recoverable) | LT hot water 80/70 °C | 636.8 | 191.0 | 171.9 | 38.8 |
| **Total** | | 5,343.5 | 2,212.2 | 1,991.0 | **1,857.8** |

Allocation with a 10 K minimum approach:

| Source → sink | kW |
|---|---:|
| Scavenge → D0 | 775.8 |
| Exhaust → D0 | 1,043.3 |
| Jacket → U3D | 38.8 |

The WHR offsets only purchased LP steam that remains after the S1 HXN, so heat is never counted twice. The U2
500 °C reaction heat is not eligible. The conceptual U2 feed preheater receives 0 kW.

| Result | Value |
|---|---:|
| Useful recovered heat | **1,857.8 kW** |
| External heating | 30,313 → 28,455 kW (**−6.13 %**) |
| Purchased LP steam | −11.1 % (avoided boiler fuel ≈ 2,322 kW LHV) |
| WHR pumps | +10.8 kW electricity |

Engine-load sensitivity (WHR operating with ATT):

| Engine load | Utilized heat | External heat reduction |
|---|---:|---:|
| 0.15 | 0 kW | 0 % |
| 0.50 | 846 kW | 2.8 % |
| 0.75 | 1,858 kW | 6.1 % |
| 1.00 | 3,362 kW | 11.1 % |

Below 50 % load (slow collection, anchoring) no qualifying heat is assumed.

**Operating hours.** The S2 results are for 7,920 h/yr underway at 75 % MCR (idealized). The hourly balances are the
same at any operating hours; only the annual quantities scale.
