# ATT S1/S2: design basis, evidence classification and limitations

**Scope.** Engineering-screening study of two process scenarios:
- **ATT S1:** baseline.
- **ATT S2:** the same process on an existing, retrofitted vessel with marine waste-heat recovery.

Washing on/off is a sensitivity case within these two scenarios, not an additional scenario.

**Model state.** BioSTEAM 2.54.0. Configuration files:
- `data/att.yaml`
- `data/att_tea.yaml`
- `data/att_lca.yaml`
- `data/marine_whr.yaml`
- `data/marine_tea.yaml`
- `data/feedstock.yaml`
- `data/tea.yaml`

**Evidence classes:**
- **EXP:** experimental measurement.
- **LIT:** source-reported literature data.
- **SABRE:** existing SaBRe inherited assumption.
- **ENG:** engineering estimate.
- **USER:** user-defined scenario assumption.
- **DER:** derived model result.

## 1. Evidence table

| Parameter | Value | Source | Class | Limitation |
|---|---|---|---|---|
| **Gas yields, Ni-CatATT 1:1** | H2 54.15; CH4 0.60; CO 0; CO2 0.77 mmol/g daf | Workbook `ATT Inputs and Assumptions_261023.xlsx` (G. Sim, modified 2026-10-24, SHA-256 db8ff0f4…f949), sheet "1. Gas Yield (Ni-ATT)", D5–G5. Oct-2026 correspondence (as relayed, not available locally): ≈ 54.2 / 0.6 / 0.8, ≈ 98 % H2 dry, N2-free | EXP | Single summary values: no replicates, uncertainty or raw GC data. Verified against the workbook table, not raw data. CO = 0 has no stated detection limit, so measured zero vs non-detect is unknown. Earlier workbook 261005 reported different runs (0.5 g + 1 g NaOH, N2 50 mL/min), superseded |
| Gas-yield experimental conditions | 0.25 g Ni-soaked Sargassum + 0.25 g NaOH; 500 °C, 1 h; N2 25 mL/min; steam 0.03 mL/min; 10 wt % Ni/ZrO2 downstream | Workbook 261023 A7 | EXP | **Not represented in the model:** no Ni impregnation, no Ni/ZrO2 catalyst (cost, lifetime, regeneration) and no steam co-feed. In 261005, plain ATT gave H2 39.6 vs 66.7 mmol/g daf with Ni + catalyst, so the yields depend strongly on these conditions. Milligram-scale batch run extrapolated to continuous industrial operation |
| Yield transfer basis | Per g daf, from experimental seaweed (ash 17.2 wt % dry, workbook B6) to presscake (ash 32.07 %) | `att.yaml` `gas_yield_basis` | USER / DER | Modeling assumption. A per-g-dry transfer would give 44.84 vs 36.78 mmol H2/g dry, i.e. +21.9 % H2. Whether the presscake (with water-soluble alginate/mannitol partly removed) behaves like raw seaweed per g daf is untested |
| Daf conversion | daf = dry × (1 − 0.3207) = 3,416.315 kg/h; gas kmol/h = y × daf / 1000 | `units/_att.py` `ATTReactor._run` | DER | Verified: moisture applied once, ash applied once, no PSA factor; simulated = hand calculation to machine precision |
| H2 output | 372.925 kg/h; 2,953.563 t/yr (7,920 h) | Simulation | DER | All per-kg-H2 results scale with the yield basis above |
| Dry feed capacity | 5,029.17 kg/h (120.7 t/d) | SaBRe S5 waste-lime scale | SABRE / USER | Fixed. Annual and scale-economy results only; per-kg results depend weakly on it |
| Presscake moisture, ash, composition | 76.3 %; ash 32.07 % dry; CHN 31.36/3.88/1.16 % | Wiatrowski et al. 2026 preprint (NLR), pressed solids 15 psi | LIT | One sample; Sargassum composition varies seasonally and regionally |
| D0 outlet moisture | 50 wt % | Workbook 261005 B12 ("assumed") and user design | ENG / USER | Sets the D0 steam demand (≈ 50 % of gross steam) |
| U2 temperature | 500 °C | Experiment | EXP | — |
| NaOH dose | 1.0 kg/kg dry (gross, incl. recycle) | User decision 2026-10-31; the workbook "1 g/g" states no mass basis | USER | NaOH makeup is 1.22 USD/kg H2 and 3.89 kg CO2e/kg H2. The experimental seaweed basis (wet/dry/daf) is unconfirmed |
| NaOH → Na2CO3 in U2 | 100 % | Workbook B15 | EXP (stated) / ENG | Not separately measured |
| Residual organic carbon | Lumped residue CH0.5O1.195 (H/C = 0.5 assumed; O solved), 0.59 g/g daf; Hf by Channiwala–Parikh; Cp 1 J/g/K | `att.yaml` `material_balance` | ENG | **Structural assumption** from elemental closure, not a measured char. It sets the U2 heat duty (9.07 MJ/kg dry), the residue disposal (0.66 USD/kg H2), part of the natural-gas GWP, and half of the storage credit (7.5 of 15.1 kg CO2e/kg H2) |
| Causticization | 88 % conversion, Ca(OH)2:Na2CO3 = 1.1 mol/mol, 3 kg water/kg Na2CO3 | Workbook B16–B18 ("commercial causticizing"); CaCO3 experiment conversion 88.3 % | LIT / EXP | Lab CaCO3 experiment used clean Na2CO3 |
| Lime | Waste carbide Ca(OH)2, free and burden-free; 42.6 kt/yr used vs 92.5 kt/yr supply | User scenario | USER | Availability, transport and impurities not assessed; limestone lime (0.91 kg CO2e/kg) would add ≈ 13 kg CO2e/kg H2 |
| NaOH recycle | 95 % liquor recycle; EC1 to 50 wt % NaOH; effective recovery 74.2 % | `att.yaml`; workbook B19 | ENG / DER | EC1 constants tuned on the SaBRe S5 liquor |
| CO2 scrubber | 99 % capture, 1.1× Ca(OH)2 | `att.yaml` | ENG | No vendor data |
| H2 product | No PSA; 98.89 mol % H2 at 2 MPa; MSP per kg contained H2 | `att.yaml` `gas_treatment` | USER / ENG | 1.1 % CH4 left in the product; end-use specification undefined |
| F2 washing | 1 kg water/kg original dry cake, 25 °C, 0.25 h, one ideal stage + F2R refiltration (native BioSTEAM MixTank / RotaryVacuumFilter); solids fully retained; no wash-liquor recycle | `att.yaml downstream.f2_washing` | ENG | Ideal dilution, no solubility or kinetics; 100 % CaCO3 recovery assumed |
| CaCO3 purity | F2 82.545 %, F3 93.107 % dry basis (model); lab ≈ 97 % | Model; workbook sheet 2 | DER / EXP | The lab value is a clean Na2CO3 + Ca(OH)2 system, not the industrial cake, so the bases are not comparable. Model purity is not forced |
| CaCO3 cakes | F2 and F3 cakes disposed at 0.04 USD/kg wet; no CaCO3 sales | `att_tea.yaml caco3_sales` (`enabled: false`) | USER | Disposal price assumed. 82.5 % cake is not PCC; no buyer or specification |
| Carbon storage | All carbon in landfilled solids credited (CaCO3, Na2CO3, lumped residue); dissolved carbonate in wastewater not | `att_lca.yaml carbonate_storage_accounting: inherited`, `credit_char_carbon: true` | USER / ENG | Landfill permanence assumed; residue composition assumed; Na2CO3 is soluble; no verified removal |
| Emission factors | NaOH 1.12; natural gas 0.056 + 0.0066 per MJ; electricity 0.449 per kWh; H2SO4 0.0445 | Collaborators' table; IPCC 2006; GREET | LIT | Electricity is a location placeholder |
| Financial basis | IRR 10 %, 20 yr, MACRS-7, 21 % tax, 60 % debt at 8 %/10 yr, FOC 4 % FCI, FCI = installed cost, CEPCI 596.2 | `tea.yaml`; `att_tea.yaml` cost_year | SABRE | No indirect capital |
| Reference vessel / engine | SPAR PYXIS; MAN B&W 5S60ME-C8.2, 8,050 kW; 75 % MCR; exhaust 240 °C, 8 kg/kWh; min outlet 160 °C | `marine_whr.yaml`; public vessel data | LIT / ENG | No OEM part-load data; existing onboard heat users ignored (optimistic); space, stability and class not assessed |
| WHR equipment | 1.008 MUSD (BioSTEAM HX correlations as proxies, placeholders for drum and controls) | `marine_whr.py` | ENG | Screening-level costs; scavenge-air interface needs OEM approval |
| Floating factors | CAPEX × 1.25 (sensitivity 1.10–1.40); labor × 2.0 (S1 labor = 50 % of FOC) | `marine_tea.yaml` | USER | No marine cost data |
| Operating hours | 7,920 h (S1; S2 Mode A, idealized); 2,640 h (S2 Mode B: 8 h/d transit) | `tea.yaml`; `marine_whr.yaml` | USER | Realistic shipboard ATT hours unknown |
| Excluded | Harvesting, collection, transport, vessel acquisition, propulsion fuel, REE recovery, CH4 credit | — | USER | Partial boundary for both TEA and LCA |

## 2. Gas-yield verification summary

| Gas | Verdict |
|---|---|
| H2, CH4, CO2 | **Pass.** Model = workbook 261023 (1:1) = simulated U2 output. Consistent with the rounded October 2026 report |
| CO | **Insufficient evidence on the measurement status.** Model = workbook value (0), but non-detect vs measured zero is undocumented. A CO yield like the 1:2 case's 0.02 mmol/g daf would be negligible (0.07 kmol/h) |
| Implementation | **Pass:** daf basis, units, no overrides, no SaBRe S5 or 1:2 values, S1 = S2 |
| Annual H2 | **Pass:** 2,953.563 t/yr, both calculated and simulated |

**The ATT S1/S2 baseline gas yields are consistent with the available experimental data on the stated daf basis.**

This verification covers consistency with the reported experimental summary. Representativeness at industrial
scale (sections 1 and 3) is a separate issue.

## 3. Uncertainties that materially affect the results

| # | Uncertainty | Effect on results |
|---|---|---|
| 1 | **CaCO3 cake disposal.** The disposal price (0.04 USD/kg wet) is assumed; no buyer or specification for the 82.5 % (F2) / 93.1 % (F3) cake | The two cakes cost **1.01 USD/kg H2** of the S1 MSP of 5.41 (15.7 kg CaCO3/kg H2) |
| 2 | **Carbon storage accounting** | S1 GWP 6.50 net vs 21.63 without the storage credit (−15.13: residue −7.52, CaCO3 −6.89, Na2CO3 −0.71). Storage is not verified removal |
| 3 | **Transfer of the experimental yields** (catalyst, Ni soaking, steam co-feed, lab scale, single run; per-g-daf transfer to higher-ash presscake; NaOH dose basis) | Every per-kg-H2 result scales roughly with 1/H2 yield. A per-dry transfer would mean +21.9 % H2. Catalyst and Ni costs are absent from the TEA and LCA |
| 4 | **S2 operating hours** | S2 MSP 5.59 (7,920 h) → 6.10 (5,280 h) → 7.61 (2,640 h). At 2,640 h, WHR no longer pays back |
| 5 | **Lumped residue thermochemistry** | U2 duty 9.07 MJ/kg dry drives ≈ 8.9 kg CO2e/kg H2 and 0.62 USD/kg of fuel cost. Residue-cake disposal is 0.66 USD/kg H2 |
| 6 | **Marine retrofit and WHR screening** | Floating CAPEX 1.10–1.40 ⇒ S2 MSP 5.50–5.69. WHR −1.39 kg CO2e/kg H2 is an upper bound (onboard users ignored, no OEM data) |

Smaller items do not change the conclusions: EC1 constants, scrubber performance, cost year (CEPCI 800 adds
+0.25 USD/kg), the electricity factor (±0.6–1.9 kg CO2e/kg H2), and collection-transport fuel.

## 4. Status

The engineering-screening S1/S2 model is complete and reproducible:
- 129 tests pass;
- the full `run_att_all` pipeline completes (8/8 steps);
- 266 QC checks pass, with 0 FAIL;
- gas yields are verified as above.

Results are **provisional screening estimates**. Before publication-grade claims, they need:
1. experimental confirmation of the yield basis (replicates, CO detection limit, presscake vs raw seaweed, the
   catalyst and Ni requirement and their cost);
2. CaCO3 product characterization and a market outlet.
