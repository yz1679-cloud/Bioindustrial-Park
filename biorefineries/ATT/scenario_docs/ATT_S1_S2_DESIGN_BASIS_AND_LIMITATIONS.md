# ATT S1/S2: design basis, evidence classification and limitations

**Scope.** Engineering-screening study of two process scenarios:
- **ATT S1:** baseline.
- **ATT S2:** the same process on an existing, retrofitted vessel with marine waste-heat recovery.

The washes (F2 and F1) and the cake drying are part of the flowsheet. CaCO3 sales and the carbon-credit rule are settings within
these two scenarios, not additional scenarios.

This document records the inputs, their evidence and their limitations. It contains no results; the numbers come from the
model and are in the generated report and tables. Configuration files:
- `data/att.yaml`
- `data/tea.yaml`
- `data/lca.yaml`
- `data/marine_whr.yaml`
- `data/marine_tea.yaml`
- `data/feedstock.yaml`

**Evidence classes:**
- **EXP:** experimental measurement.
- **LIT:** source-reported literature data.
- **SABRE:** existing SaBRe inherited assumption.
- **ENG:** engineering estimate.
- **USER:** user-defined scenario assumption.
- **DER:** derived from other inputs.

## 1. Evidence table

| Parameter | Value | Source | Class | Limitation |
|---|---|---|---|---|
| **Gas yields, Ni-CatATT 1:1** | H2 54.15; CH4 0.60; CO 0; CO2 0.77 mmol/g daf | Workbook `ATT Inputs and Assumptions_261023.xlsx` (G. Sim, modified 2026-10-24, SHA-256 db8ff0f4…f949), sheet "1. Gas Yield (Ni-ATT)", D5–G5. Oct-2026 correspondence (as relayed, not available locally): ≈ 54.2 / 0.6 / 0.8, ≈ 98 % H2 dry, N2-free | EXP | Single summary values: no replicates, uncertainty or raw GC data. Verified against the workbook table, not raw data. CO = 0 has no stated detection limit, so measured zero vs non-detect is unknown. Earlier workbook 261005 reported different runs (0.5 g + 1 g NaOH, N2 50 mL/min), superseded |
| Gas-yield experimental conditions | 0.25 g Ni-soaked Sargassum + 0.25 g NaOH; 500 °C, 1 h; N2 25 mL/min; steam 0.03 mL/min; 10 wt % Ni/ZrO2 downstream | Workbook 261023 A7 | EXP | **Not represented in the model:** no Ni impregnation, no Ni/ZrO2 catalyst (cost, lifetime, regeneration) and no steam co-feed. In 261005, plain ATT gave H2 39.6 vs 66.7 mmol/g daf with Ni + catalyst, so the yields depend strongly on these conditions. Milligram-scale batch run extrapolated to continuous industrial operation |
| Yield transfer basis | Per g daf, from experimental seaweed (ash 17.2 wt % dry, workbook B6) to presscake (ash 32.07 %) | `att.yaml` `gas_yield_basis` | USER / DER | Modeling assumption. A per-g-dry transfer would give 44.84 vs 36.78 mmol H2/g dry, i.e. +21.9 % H2. Whether the presscake (with water-soluble alginate/mannitol partly removed) behaves like raw seaweed per g daf is untested |
| Daf conversion | daf = dry × (1 − 0.3207); gas kmol/h = y × daf / 1000 | `units/_att.py` `ATTReactor._run` | DER | Verified: moisture applied once, ash applied once, no PSA factor; simulated = hand calculation to machine precision |
| H2 output | Yield × daf feed × molar mass of H2, over the operating hours | Simulation | DER | All per-kg-H2 results scale with the yield basis above |
| Dry feed capacity | 5,029.17 kg/h (120.7 t/d) | SaBRe S5 waste-lime scale | SABRE / USER | Fixed. Annual and scale-economy results only; per-kg results depend weakly on it |
| Presscake moisture, ash, composition | 76.3 %; ash 32.07 % dry; CHN 31.36/3.88/1.16 % | Wiatrowski et al. 2026 preprint (NLR), pressed solids 15 psi | LIT | One sample; Sargassum composition varies seasonally and regionally |
| D0 outlet moisture | 50 wt % | Workbook 261005 B12 ("assumed") and user design | ENG / USER | Sets the D0 steam demand, a large share of the gross steam |
| U2 temperature | 500 °C | Experiment | EXP | — |
| NaOH dose | 1.0 kg/kg dry (gross, incl. recycle) | User decision 2026-10-31; the workbook "1 g/g" states no mass basis | USER | The NaOH makeup is a cost and GWP item. The experimental seaweed basis (wet/dry/daf) is unconfirmed |
| NaOH → Na2CO3 in U2 | 100 % | Workbook B15 | EXP (stated) / ENG | Not separately measured |
| Residual organic carbon | Lumped residue CH0.5O1.195 (H/C = 0.5 assumed; O solved), 0.59 g/g daf; Hf by Channiwala–Parikh; Cp 1 J/g/K | `att.yaml` `material_balance` | ENG | **Structural assumption** from elemental closure, not a measured char. It sets the U2 heat duty and part of the natural-gas GWP. RS1 keeps only the char (see below); the char earns a small part of the storage credit |
| Causticization | 88 % conversion, Ca(OH)2:Na2CO3 = 1.1 mol/mol, 3 kg water/kg Na2CO3 | Workbook B16–B18 ("commercial causticizing"); CaCO3 experiment conversion 88.3 % | LIT / EXP | Lab CaCO3 experiment used clean Na2CO3 |
| Lime | Waste carbide lime of an acetylene plant, free and burden-free: a paste with 92 % Ca(OH)2, 4 % CaCO3, 4 % inert minerals (dry basis), 40 wt % water; the Ca(OH)2 used is compared with a 92.5 kt/yr supply | `att.yaml waste_lime`; literature ranges (dried acetylene-plant sludge 95 % Ca(OH)2, 2 % CaCO3, 1.3 % SiO2; EIGA Doc 143/25 for the paste water) | USER / LIT | The split and the water content are choices inside the reported ranges (EIGA's slurry table reports 16–22 % CaCO3). The inert minerals are lumped, with SiO2 properties, and do not dissolve. Trace metals (Cu, Mn, Ni, Ba, Cr), chloride, sulfate and ammonium are not modeled. Availability and transport not assessed; fresh limestone lime (0.91 kg CO2e/kg) would add a large GWP |
| NaOH recycle | 95 % liquor recycle; EC1 to 50 wt % NaOH | `att.yaml`; workbook B19 | ENG / DER | EC1 constants tuned on the SaBRe S5 liquor |
| CO2 scrubber | 99 % capture, 1.1× Ca(OH)2 | `att.yaml` | ENG | No vendor data |
| H2 product | No PSA; H2-rich gas at 2 MPa; MSP per kg contained H2 | `att.yaml` `gas_treatment` | USER / ENG | About 1 % CH4 is left in the product; end-use specification undefined |
| Ash split | Insoluble 0.3838, NaCl 0.2377, KCl 0.3785 of the seaweed ash (the insoluble Ash minerals stay in the char; K and Na dissolve as KCl and NaCl) | `att.yaml feed_preparation.ash_split` | USER / ENG | **Illustrative, not measured:** based on typical seaweed major-element contents the user shared (not the collaborators' sample); chloride as the counter-anion is assumed; S, P, Si, Al and Fe as soluble species are not modeled |
| Insoluble char | 0.15 g per g of dry feed (Ash minerals + CharN/CharS + organic Char); the rest of the lumped residue goes to `att_residue_untracked` with no credit and no cost | `att.yaml downstream.char` (RS1) | USER (collaborator's mass balance, 0.126–0.169) | The carbon balance is not closed on measured sinks (atoms out do not exceed atoms in). U2's heat duty is not re-derived for the smaller char |
| Salt crystallizer | XL1 removes 99 % of the NaCl and KCl from the EC1 concentrate; the cake keeps 10 wt % liquor; disposed at 0.04 USD/kg | `att.yaml downstream.salt_crystallizer` | ENG | PRELIMINARY: vessel and solids centrifuge (BioSTEAM defaults), no solubility data for NaCl/KCl in 50 wt % NaOH |
| REE recovery | Switch on by default. HCl leach (0.5 mmol/g char, 5 kg liquor/kg char), oxalate precipitation (0.042 mmol/g char), roast of only the precipitate at 900 °C; product REO = 60 % of the REE of the initial wastewater (1.4 mg TREE/L at 2.5 g seaweed/L), capped by the oxalate stoichiometry; 1.31 wt % REO with mineral filler from the char Ash; REO sold at 35 USD/kg | `att.yaml downstream.ree_recovery`; `tea.yaml prices.REO` | USER / ENG / EXP (lab doses) | **Assumptions:** the seaweed already carries 737 ppm TREE (the capture section is not modeled or costed); the 60 % recovery is the collaborators' overall Nd recovery from a 0.01 M run, applied to the dilute case; no buyer for a 1.3 wt % REO solid; dissolved Fe, Al, Mn, Ca and Mg of the leach are not tracked; the roaster is a K1 kiln correlation; HCl and oxalic acid are not in the LCA |
| F2 washing | 1 kg water/kg original dry cake, the condensate the dissolver does not need (fresh water only as a top-up), 0.25 h, one ideal stage + F2R refiltration (native BioSTEAM MixTank / RotaryVacuumFilter); solids fully retained; the wash liquor is recycled to the dissolver | `att.yaml downstream.f2_washing` | ENG | Ideal dilution, no solubility or kinetics; 100 % CaCO3 recovery assumed |
| F1 washing | Same ratio for the ATT residue cake (W1 MixTank + F1R pressure filter, 30 wt % moisture, no dryer); the wash liquor is combined with the carbonate solution to C1 | `att.yaml downstream.f1_washing` | ENG / USER | Ideal dilution; the wash water is evaporated again in EC1 |
| CaCO3 purity | Calculated for the F2 and F3 cakes (dry basis), never forced; lab ≈ 97 % | Model; workbook sheet 2 | DER / EXP | The lab value is a clean Na2CO3 + Ca(OH)2 system, not the industrial cake, so the bases are not comparable |
| CaCO3 cake drying | The F2 and scrubber cakes are dried from 25 to 1 wt % moisture in steam-heated drum dryers (D2, D3; D0 type, same drum temperature and exhaust humidity); no grinding or purification | `att.yaml downstream.caco3_drying` | USER / ENG | **The 1 wt % target is an assumption**: no filler specification or buyer. The disposal charge is on the wet mass, so drying the cakes removes charged cake water |
| CaCO3 cakes | Both dried cakes sold at 100 USD/t of CaCO3 component (the lime's CaCO3 included); the non-CaCO3 mass is disposed at 0.04 USD/kg wet | `tea.yaml caco3_sales` | USER | **Optimistic, unverified:** no buyer or specification; a cake with unreacted Ca(OH)2 is not PCC |
| ATT residue | The leached char cake (30 wt % moisture, not dried) has a net price of 0, assumed to be taken as a sorbent | `tea.yaml prices.att_char` | USER | **No buyer, specification or measured properties.** Composition assumed (ash minerals and a CH0.5O0.1 char), possibly alkaline, arsenic and other metals not assessed. The assumption lowers the MSP compared with disposal at the fee |
| Carbon storage | The Sargassum carbon of the solids is credited: the CaCO3 of the cakes (sold or landfilled) and the organic char of the residue. Soluble Na2CO3, the lime's CaCO3 and dissolved carbonate in wastewater are not | `lca.yaml carbon_storage` | USER / ENG | The fate of sold CaCO3 is outside the plant; residue composition assumed; no verified removal |
| Emission factors | NaOH 1.12; natural gas 0.056 + 0.0098 per MJ; electricity 0.449 per kWh; H2SO4 0.0445 | Collaborators' table; IPCC 2006; GREET | LIT | Electricity is a location placeholder |
| Financial basis | IRR 10 %, 20 yr, MACRS-7, 21 % tax, 60 % debt at 8 %/10 yr, FOC 4 % FCI, FCI = installed cost, CEPCI 596.2 | `tea.yaml` (financial, cost_year) | SABRE | No indirect capital |
| Reference vessel / engine | SPAR PYXIS; MAN B&W 5S60ME-C8.2, 8,050 kW; 75 % MCR; exhaust 240 °C, 8 kg/kWh; min outlet 160 °C | `marine_whr.yaml`; public vessel data | LIT / ENG | No OEM part-load data; existing onboard heat users ignored (optimistic); space, stability and class not assessed |
| WHR equipment | BioSTEAM HX correlations as proxies, placeholders for drum and controls | `marine_whr.py` | ENG | Screening-level costs; scavenge-air interface needs OEM approval |
| Floating factors | CAPEX × 1.25 (sensitivity 1.10–1.40); labor × 2.0 (S1 labor = 50 % of FOC) | `marine_tea.yaml` | USER | No marine cost data |
| Operating hours | 7,920 h (S1 and S2, underway, idealized) | `tea.yaml`; `marine_whr.yaml` | USER | Realistic shipboard ATT hours unknown |
| Excluded | Harvesting, collection, transport, vessel acquisition, propulsion fuel, REE capture from acid mine drainage, CH4 credit | — | USER | Partial boundary for both TEA and LCA |

## 2. Gas-yield verification summary

| Gas | Verdict |
|---|---|
| H2, CH4, CO2 | **Pass.** Model = workbook 261023 (1:1) = simulated U2 output. Consistent with the rounded October 2026 report |
| CO | **Insufficient evidence on the measurement status.** Model = workbook value (0), but non-detect vs measured zero is undocumented. A CO yield like the 1:2 case's 0.02 mmol/g daf would be negligible |
| Implementation | **Pass:** daf basis, units, no overrides, no SaBRe S5 or 1:2 values, S1 = S2 |
| Annual H2 | **Pass:** calculated by hand and simulated agree (`test_att_independent_checks.py`) |

**The ATT S1/S2 baseline gas yields are consistent with the available experimental data on the stated daf basis.**

This verification covers consistency with the reported experimental summary. Representativeness at industrial
scale (sections 1 and 3) is a separate issue.

## 3. Uncertainties that materially affect the results

| # | Uncertainty | Effect on results |
|---|---|---|
| 1 | **CaCO3 sales and cake quality.** No buyer, specification or verified price for the F2 and F3 cakes | The CaCO3 revenue is the largest credit of the MSP; the MSP moves linearly with the CaCO3 price, and the no-sales MSP is far higher than the baseline. Quote the no-sales case beside the baseline |
| 2 | **Carbon storage accounting** | The net GWP with the storage credit differs strongly from the gross emissions without it. The soluble Na2CO3, the lime's CaCO3 and the untracked organics are not credited. Storage is not verified removal |
| 3 | **Transfer of the experimental yields** (catalyst, Ni soaking, steam co-feed, lab scale, single run; per-g-daf transfer to higher-ash presscake; NaOH dose basis) | Every per-kg-H2 result scales roughly with 1/H2 yield. A per-dry transfer would mean +21.9 % H2. Catalyst and Ni costs are absent from the TEA and LCA |
| 4 | **ATT residue has a net price of 0** | Lowers the MSP compared with disposing of the leached char at 0.04 USD/kg wet; the F1 wash adds capital |
| 5 | **Lumped residue thermochemistry** | The U2 duty drives most of the natural-gas GWP and fuel cost |
| 6 | **Marine retrofit and WHR screening** (S2 at 7,920 h/yr underway) | The floating CAPEX multiplier (1.10–1.40) moves the S2 MSP. The WHR benefit is an upper bound (onboard users ignored, no OEM data) |
| 7 | **REE recovery** (60 % of the wastewater REE, 1.31 wt % REO, 35 USD/kg REO; capture section not modeled) | Whether it lowers or raises the MSP depends on the REO price; the model reports a break-even price. Dissolved metals of the leach are not tracked and the LCA omits the HCl and oxalic acid production |

Smaller items do not change the conclusions: EC1 constants, scrubber performance, the electricity factor, and collection-transport fuel.

## 4. Status

The engineering-screening S1/S2 model is complete and reproducible: the test suite (`test/`) and the full
`analyses/run.py all` pipeline pass, and the QC checks of the pipeline report no failure. Results are **provisional
screening estimates**. Before publication-grade claims, they need:
1. experimental confirmation of the yield basis (replicates, CO detection limit, presscake vs raw seaweed, the
   catalyst and Ni requirement and their cost);
2. CaCO3 product characterization (including the moisture and purity a buyer would require) and a market outlet;
3. characterization of the ATT residue (carbon, ash, pH, conductivity, porosity, metals including arsenic) and a buyer;
4. measured seaweed ash composition (including chloride), char yield and carbon sinks, and the REE leach and oxalate
   steps (extraction, selectivity against Ca, Mg, Fe and Al, the grade a refiner would accept) with a REO buyer.
