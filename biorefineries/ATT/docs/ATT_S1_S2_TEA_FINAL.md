# ATT S1/S2: techno-economic analysis (final)

**Model state.** BioSTEAM 2.54.0. Baseline assumptions:
- The waste lime is the carbide lime of an acetylene plant (a paste with CaCO3 and inert mineral impurities), free.
- The seaweed ash of the presscake is split into an insoluble part (Ca, Mg and trace minerals, which stay in the char) and a
  soluble part (all K and Na, modeled as KCl and NaCl). The soluble salts are removed from the NaOH recycle by a **salt
  crystallizer** (XL1) and disposed of.
- The insoluble char is set to 0.15 g per g of dry feed (RS1). The rest of the lumped U2 residue leaves as
  `att_residue_untracked` with no credit and no cost.
- Both CaCO3 cakes (F2 and F3) are **dried** to 1 wt % moisture (steam-heated drum dryers D2 and D3; the target is an
  assumption) and **sold** at 100 USD/t of CaCO3 (an assumption with no buyer); the non-CaCO3 mass is disposed.
- The F2 cake and the F1 char cake are washed (1 kg water per kg of dry cake) with the condensate the dissolver does not
  need. The F2 wash liquor is recycled to the dissolver and the F1 wash liquor to the carbonate solution of C1.
- **REE recovery is on** (default since 2026-11-03; `ree_recovery=False` turns it off): the washed char cake is leached
  with HCl, the rare earths are precipitated as oxalate and roasted, and the product is sold on its REO content
  (35 USD/kg REO, an assumption). The leached char is the residue product and has a **net price of 0** (assumed to be
  taken as a sorbent, no buyer).

S2 results are for 7,920 h/yr underway. MSP is the minimum H2 selling price in USD per kg of contained H2 (NPV = 0 at
a 10 % IRR). The carbon accounting paired with it is described in `ATT_S1_S2_LCA_FINAL.md`.

## 1. Production and financial basis

| Item | Value | Class |
|---|---|---|
| H2 | 372.925 kg/h; 2,953.56 t/yr at 7,920 h | Simulation (gas yields verified, see the process document) |
| H2 delivery | 98.89 mol % H2 at 2 MPa, no PSA. MSP is per kg of contained H2; CH4 in the product earns no credit | Model / [ASSUMPTION] |
| Financial method | SaBReTEA DCF: IRR 10 %, 2026–2046, MACRS-7, 21 % income tax, 40/60 construction, 60 % debt at 8 % over 10 yr, working capital 5 % of FCI, 3-month startup | Inherited SaBRe/BioSTEAM |
| Capital convention | FCI = installed equipment cost (no separate indirect costs); CEPCI 596.2 (2020 USD) | Inherited SaBRe; ATT cost year |
| Fixed operating cost | 4 % of FCI per yr (labor, maintenance, overhead) | Inherited SaBRe |
| Prices | NaOH 0.35 USD/kg; waste Ca(OH)2 0 (fresh lime 0.28 USD/kg, not used); H2SO4 0.0948 USD/kg; process water 0.000441 USD/kg; solid disposal 0.04 USD/kg wet; wastewater 0.004 USD/kg; natural gas 4.36 USD/GJ (LHV); LP steam 0.2378 USD/kmol; electricity 0.0782 USD/kWh | `tea.yaml`, BioSTEAM defaults |
| REE chemicals and product | HCl (31 wt %) 0.20 USD/kg; oxalic acid 0.60 USD/kg; REO 35 USD/kg of contained REO (range 2–151) | [ASSUMPTION] `tea.yaml` |
| CaCO3 sales | 100 USD/t of CaCO3 component, F2 and F3 cakes (unverified) | [ASSUMPTION] |
| CaCO3 drying | Cakes dried from 25 to 1 wt % moisture; no grinding, purification or handling cost | [ASSUMPTION] |
| ATT residue | Net price 0 (`prices.att_char`): the leached char is assumed to be taken as a sorbent | [ASSUMPTION] |
| Salt cake | Disposed at the solid-waste price (0.04 USD/kg wet) | [ASSUMPTION] |
| Feedstock | 0 USD/t (collection and transport outside the boundary) | [ASSUMPTION] |

## 2. S1 capital and operating costs

**Capital (installed, MUSD):**

| Area | Installed |
|---|---:|
| ATT reactor U2 | 2.37 |
| Feed drying D0 | 2.21 |
| NaOH evaporation EC1 | 1.50 |
| H2 compression U3K | 1.14 |
| Gas cooling and drying | 1.12 |
| **CaCO3 cake drying D2 + D3** | **1.03** |
| **REE leach and oxalate precipitation LC1** | **0.91** |
| CaCO3 filtration F2 | 0.78 |
| Residue filtration F1 | 0.72 |
| **F1 washing W1 + F1R** | **0.66** |
| **F2 washing W2 + F2R** | **0.62** |
| Causticization C1 | 0.45 |
| CO2 scrubber and F3 | 0.37 |
| **REE oxalate roaster RO1** | **0.37** |
| Residue cooling RC1 | 0.25 |
| **Salt crystallizer XL1** | **0.24** |
| Heat exchanger network HXN | 0.04 |
| **FCI** | **14.786** |
| Working capital | 0.739 |
| **TCI** | **15.525** |

**Annual operating cost (MUSD/yr):**

| Group | Cost |
|---|---:|
| LP steam | 2.65 |
| U2 natural gas | 1.86 |
| NaOH makeup | 1.36 |
| Electricity | 0.98 |
| Fixed operating cost | 0.59 |
| CaCO3-cake disposal (non-CaCO3 mass, F2 + F3) | 0.54 |
| Salt cake disposal | 0.33 |
| H2SO4 neutralization (purge) | 0.24 |
| Wastewater (excess condensate, purge, dryer water) | 0.18 |
| Cooling water | 0.13 |
| REE reagents (HCl, oxalic acid) | 0.08 |
| Process water | 0 |
| Ca(OH)2 (waste lime) | 0 |
| ATT residue disposal (net) | 0 |
| **REE product sales** | **−0.55** |
| **CaCO3 sales** | **−5.33** |
| **Net** | **3.075** |

**S1 MSP breakdown (USD/kg H2, levelized at NPV = 0):**

| Component | USD/kg H2 | Share |
|---|---:|---:|
| Utilities (LP steam 0.90, natural gas 0.63, electricity 0.33, cooling water 0.05) | 1.91 | 113 % |
| Capital-related (capital, debt service, tax) | 0.65 | 38 % |
| Waste treatment and disposal (CaCO3 cakes 0.18, salt cake 0.11, H2SO4 0.08, wastewater 0.06) | 0.44 | 26 % |
| Materials (NaOH 0.46, REE reagents 0.03) | 0.49 | 29 % |
| Fixed operating cost | 0.20 | 12 % |
| **REE product sales** | **−0.19** | −11 % |
| **CaCO3 sales** | **−1.80** | −107 % |
| **MSP** | **1.690** | |

The process is dominated by operating costs, and mainly by heat: steam and natural gas are 1.53 USD/kg. The CaCO3
revenue offsets most of the costs, so the MSP depends on its price (section 4).

## 3. F2 and F1 washing (S1)

These rows are the process **without** REE recovery (`ree_recovery=False`), so that the washing steps can be compared
alone; the last row adds the REE recovery (baseline). All rows include the cake dryers, the ash split, the char split
and the salt crystallizer.

| Configuration | MSP (USD/kg H2) | Net GWP (kg CO2e/kg H2) | FCI (MUSD) | AOC (MUSD/yr) | Fresh NaOH (t/yr) |
|---|---:|---:|---:|---:|---:|
| No washing, residue disposed | 2.260 | 16.52 | 12.11 | 5.11 | 7,734 |
| F2 wash, wash liquor recycled | 1.879 | 15.39 | 12.73 | 3.90 | 4,555 |
| + F1 wash, residue disposed | 1.874 | 15.71 | 13.50 | 3.79 | 3,957 |
| + residue net price 0 | 1.752 | 15.71 | 13.50 | 3.43 | 3,957 |
| **+ REE recovery (baseline)** | **1.690** | 15.83 | 14.79 | 3.08 | 3,883 |

| Item | Value |
|---|---|
| Wash ratio | 1 kg water per kg of dry cake, both washes; one ideal mixed stage (0.25 h) and refiltration at the cake moisture |
| Wash water | Condensate left after the dissolver (and, for F1, after the F2 wash); fresh water only as a top-up (0 in S1 and S2) |
| Wash liquors | F2: 9.5 t/h to the dissolver D1. F1: 1.1 t/h joined with the F1 filtrate and sent to C1 |
| F2 equipment | W2 MixTank installed 0.051 MUSD; F2R rotary vacuum filter installed 0.572 MUSD, 32.9 kW |
| F1 equipment | W1 MixTank installed 0.016 MUSD; F1R pressure filter installed 0.645 MUSD, 51.9 kW |

**Interpretation.**
- The F2 wash and the recycle of its liquor lower the MSP by 0.38 USD/kg H2: the recovered sodium cuts the fresh NaOH
  from 7,734 to 4,555 t/yr.
- The F1 wash recovers more sodium (fresh NaOH 3,957 t/yr), but it adds 0.76 MUSD of FCI and its wash water must be
  evaporated in EC1. With the residue still disposed it lowers the MSP by only 0.005 USD/kg and raises the GWP by
  0.32 kg CO2e/kg H2.
- The step to a net price of 0 for the residue (−0.12 USD/kg H2) comes from the **assumption**: without it, the
  1,144 kg/h of wet char cake × 0.04 USD/kg × 7,920 h would cost 0.36 MUSD/yr. There is no buyer or specification.
- The REE recovery lowers the MSP by 0.062 USD/kg H2 at 35 USD/kg REO (section 5).

## 4. CaCO3 cakes and the ATT residue

| | F2 cake | F3 scrubber cake |
|---|---:|---:|
| Wet (dried, 1 wt % moisture) / dry mass | 8,119.6 / 8,038.4 kg/h | 301.4 / 298.4 kg/h |
| CaCO3 component | 6,456.08 kg/h (51,131 t/yr) | 269.88 kg/h (2,137 t/yr) |
| CaCO3 purity, dry basis | 80.315 % | 90.441 % |
| Revenue at 100 USD/t | 5,113,217 USD/yr | 213,745 USD/yr |
| Disposal of the non-CaCO3 mass | 527,014 USD/yr | 9,991 USD/yr |

The CaCO3 of the cakes comes from the causticization, the CO2 scrubber and the CaCO3 (4 % of the dry lime) of the
carbide lime. The plant makes 18.0 kg of CaCO3 per kg of H2.

**Drying (D2, D3).** The filter cakes (25 wt % moisture) are dried to 1 wt % in two steam-heated drum dryers of the
D0 type: D2 evaporates 2,598 kg/h (1.96 MW of steam duty, 0.82 MUSD installed, 123 kW) and D3 evaporates 96 kg/h
(0.08 MW, 0.22 MUSD, 14 kW). The target moisture is an assumption; there is no filler specification, grinding or
purification. The HXN covers all of the dryer steam duty. The dryers add 1.03 MUSD to the FCI and 0.09 MUSD/yr of electricity.
The S1 MSP nevertheless falls from 1.768 (no dryers) to 1.690, because the disposal charge (0.04 USD/kg wet) is applied
to all non-CaCO3 mass of the sold cakes, including their water. Drying removes 2.7 t/h of it, which is worth
0.85 MUSD/yr (0.29 USD/kg H2). Without that charge the dryers would raise the MSP by about 0.2 USD/kg H2 [DERIVED].

**Accounting interpretation.** No unit separates CaCO3 from the cake. The revenue/disposal split is a **net cake
price**: the CaCO3 content × 100 USD/t, minus 0.04 USD/kg × the non-CaCO3 mass (moisture, unreacted Ca(OH)2, inert
minerals, sodium and the K and Na chlorides). It is booked once, on the stream price. There is no product specification,
buyer or verified price: an 80.3 % CaCO3 cake with unreacted Ca(OH)2 is **not** high-purity PCC, and the lab ≈ 97 % purity
was measured on a different, clean system. The sales case is therefore an upper bound.

**CaCO3 price sensitivity (S1):**

| CaCO3 price | MSP (USD/kg H2) |
|---|---:|
| No sales; both cakes disposed | 4.215 |
| 0 USD/t (taken away, non-CaCO3 mass disposed) | 3.494 |
| 100 USD/t (baseline) | 1.690 |
| 315 USD/t (approximate public industrial reference, unverified for this product) | −2.188 |

Each 100 USD/t of CaCO3 price moves the S1 MSP by ≈ 1.80 USD/kg H2.

**ATT residue (leached char).** The cake is 872 kg/h wet at 30 wt % moisture (611 kg/h dry, 4,840 dry t/yr; 466.5 kg/h of
ash minerals, 78.2 kg/h of organic char, 61.5 kg/h of CharN and CharS, and the 2.4 kg/h of REO that was not recovered).
Its disposal at 0.04 USD/kg wet would cost 0.28 MUSD/yr (0.09 USD/kg H2). The baseline assumes the residue has a net price of 0, for
example as a sorbent. Setting `tea.yaml prices.att_char` to -0.04 (the disposal fee) gives an S1
MSP of 1.784.

**Salt cake.** The crystallizer XL1 (0.24 MUSD installed, 9 kW) removes 99 % of the NaCl and KCl from the EC1 concentrate:
1,040 kg/h of salt cake (373 NaCl, 564 KCl, 46 NaOH, 8 Na2CO3, 50 water), disposed at 0.04 USD/kg (0.33 MUSD/yr,
0.11 USD/kg H2). The chloride contents of the seaweed are not measured.

## 5. REE recovery

The seaweed is assumed to carry 737 ppm TREE already (the Sargassum of the lab, soaked in acid mine drainage). The
capture section (soak tank, screen, press) is **not modeled or costed**.

| Item | Value |
|---|---|
| REE basis | Wastewater 1.4 mg TREE/L at 2.5 g dry seaweed/L; REO/TREE factor 1.169; product REO = 60 % of the REE of the initial wastewater (1.98 of 3.29 kg/h REO), capped by the oxalate stoichiometry (85 % of the REE of the char) |
| Reagents (lab doses per g of char) | 31 wt % HCl 44.6 kg/h (0.2 USD/kg); oxalic acid 2.87 kg/h (0.6 USD/kg); 0.08 MUSD/yr |
| Product | 150.8 kg/h of roasted oxalate precipitate with mineral filler from the char Ash, 1.31 wt % REO (1,194 t/yr); 15.6 t/yr of REO |
| Equipment | LC1 0.91 MUSD (leach and oxalate tanks, filters), 60 kW; RO1 0.37 MUSD (roaster, only the precipitate), 57 kW and 70 kW of natural gas |
| Revenue at 35 USD/kg REO | 0.55 MUSD/yr (0.185 USD/kg H2) |
| MSP effect | 1.752 (off) → 1.690 (on): −0.062 USD/kg H2; GWP +0.12 kg CO2e/kg H2; FCI +1.29 MUSD |

**S1 MSP by REO price (USD/kg H2):**

| REO price (USD/kg) | 2 | 35 (baseline) | 65 | 97 | 151 |
|---|---:|---:|---:|---:|---:|
| MSP | 1.865 | 1.690 | 1.531 | 1.362 | 1.076 |

The MSP falls by 0.0053 USD/kg H2 per USD/kg REO. REE recovery is better than not recovering above **23.2 USD/kg REO**
(S1) and **27.9 USD/kg REO** (S2 Mode A, all WHR; the 1.25 capex factor makes the added equipment dearer). A 1.3 wt % REO
solid would not fetch these prices without a buyer and a grade that suits a refiner.

**REO grade sensitivity (the collaborators' 98 wt % case).** If the seaweed is soaked in a concentrated REE solution, the
product can reach 98 wt % REO (their 0.01 M Nd run gave 98.8 % Nd2O3). The sensitivity (`analyses/ree_sensitivity.py`,
`results/tables/att_ree_grade_sensitivity.csv`) changes **only the grade**: the REO mass of the product stays at 1.98 kg/h
(60 % of the REE of the dilute wastewater) and the mineral filler that dilutes it shrinks. A larger REE loading of the
seaweed (more REO per kg of char) is **not** modeled.

| REO grade (wt %) | 1.31 (baseline) | 5 | 20 | 50 | 98 |
|---|---:|---:|---:|---:|---:|
| Product (kg/h) | 150.8 | 39.5 | 9.9 | 4.0 | 2.0 |
| RO1 roaster (MUSD) | 0.367 | 0.166 | 0.078 | 0.053 | 0.042 |
| LC1 (MUSD) | 0.908 | 0.793 | 0.750 | 0.739 | 0.735 |
| S1 MSP at 35 USD/kg REO | 1.690 | 1.661 | 1.650 | 1.647 | 1.646 |
| S2 MSP at 35 USD/kg REO (all WHR) | 1.918 | 1.883 | 1.869 | 1.865 | 1.864 |
| S1 break-even REO price (USD/kg) | 23.2 | 17.8 | 15.7 | 15.1 | 14.8 |
| S2 break-even REO price (USD/kg) | 27.9 | 21.4 | 18.8 | 18.0 | 17.8 |

At 98 % the S1 MSP is 0.044 USD/kg H2 below the baseline grade at the same price (the roaster and the oxalate filter shrink; the
revenue is the same because the product is sold on its REO content). The MSP at 98 % for 65 / 97 / 151 USD/kg REO is
1.487 / 1.317 / 1.031 (S1) and 1.705 / 1.535 / 1.249 (S2). Whether a 98 % product would fetch more than the 35 USD/kg of the
mixed concentrate is an assumption, which is why the price is swept.

## 6. Final MSP comparison (USD/kg H2, 7,920 h/yr)

| Case | H2 (t/yr) | FCI (MUSD) | AOC (MUSD/yr) | MSP | Net GWP (kg CO2e/kg H2) |
|---|---:|---:|---:|---:|---:|
| S1 | 2,953.56 | 14.786 | 3.075 | **1.690** | 15.83 |
| S2 floating, no WHR | 2,953.56 | 18.482 | 3.445 | 1.978 | 15.83 |
| **S2 floating, all WHR** | 2,953.56 | 19.372 | 3.150 | **1.918** | 14.47 |

S2 (all WHR) with the other residue assumption (leached char disposed at 0.04 USD/kg wet): MSP ≈ 2.011 [DERIVED:
the same +0.094 USD/kg H2 as in S1].

S1 and S2 **without REE recovery** (the previous baseline): S1 1.752; S2 no WHR 2.016; S2 all WHR 1.955.

**S2 cost structure (all WHR):**
- Process CAPEX = 1.25 × S1 FCI = 18.482 MUSD; WHR equipment adds 0.890 MUSD after the multiplier.
- WHR equipment, installed:

| Item | USD |
|---|---:|
| Economizer | 246,980 |
| Steam drum / interface (placeholder) | 150,000 |
| Charge-air cooler | 198,398 |
| Pumps | 40,176 |
| Piping and controls allowance | 254,221 |

The jacket-water loop (80/70 °C) finds no sink that is cold enough, so its exchanger and pump are not bought.

- Labor = 2 × the S1 labor. The S1 labor is taken as 50 % of the S1 FOC (0.296 → 0.591 MUSD/yr).
- WHR cuts purchased energy by 0.313 MUSD/yr (5.629 → 5.317 MUSD/yr).

## 7. Interpretation

1. **S1 vs S2.** Floating operation adds +0.228 USD/kg with all WHR (1.690 → 1.918; +0.289 without WHR). The 1.25 CAPEX
   factor (+3.70 MUSD) accounts for about 0.19 of the +0.289 and the doubled labor (+0.30 MUSD/yr) for about 0.10. The WHR
   (exhaust and scavenge air; the jacket-water loop finds no sink) recovers 0.061 USD/kg. S2 stays ≈ 13 % above S1.
   With the S1 capital and labor (multipliers 1.0, WHR equipment still added) S2 would be 1.629, 0.061 below S1.
2. **WHR.** The 0.89 MUSD of WHR equipment is repaid by 0.31 MUSD/yr of avoided steam. Each MUSD of WHR equipment lowers
   the MSP by about 0.055 USD/kg for the exhaust-only set (0.58 MUSD) and 0.068 USD/kg for the full set. The operating hours matter: the S2
   results are at 7,920 h/yr underway, and fewer hours spread the fixed costs over less H2.
3. **CaCO3 sales.** The revenue is −1.80 USD/kg H2 of the MSP, the largest single item and an unverified one. Without
   sales the S1 MSP is 4.22. Unless a buyer and specification for the cake are confirmed, quote the no-sales value beside it.
4. **ATT residue.** Assuming that the leached char has a net price of 0 lowers the MSP by 0.09 USD/kg. Without it, S1
   is 1.78 (S2 all WHR ≈ 2.01).
5. **REE recovery.** It lowers the MSP only above 23 USD/kg REO (S1) and 28 USD/kg REO (S2). At 2 USD/kg REO the S1 MSP
   is 1.865, 0.11 higher than without the recovery. The price, the 60 % recovery, the 1.31 wt % grade and the buyer are assumptions.
6. **Other drivers:**
   - NaOH makeup is 0.46 USD/kg H2, from a 9.7 % makeup rate (3,883 of 39,831 t/yr of gross NaOH).
   - Fuel and steam together are 1.53 USD/kg.
   - CaCO3 drying lowers the S1 MSP by 0.08 USD/kg only through the disposal charge on the cake water (section 4).

**S2 floating-factor sensitivity (all WHR; MSP in USD/kg H2):**

| Parameter | Low | High |
|---|---:|---:|
| CAPEX multiplier 1.10 / 1.40 | 1.806 | 2.030 |
| Labor multiplier 1 / 2 | 1.816 | 1.918 |
| WHR CAPEX × 0.5 / × 2 | 1.895 | 1.963 |
| WHR CAPEX at the IMO lower bound for power WHRS (5.2 MUSD) | — | 2.136 |
| No scavenge-air recovery | — | 1.946 |
| Engine load 0.5 / 1.0 | 1.967 | 1.841 |

Boundary reminders:
- No vessel acquisition, harvesting, collection or transport cost.
- No CH4 credit.
- The REE capture from the acid mine drainage is not modeled or costed.
- The dissolved metals of the HCl leach (Fe, Al, Mn, Ca, Mg and others) are not tracked through the recycle.
- Prices are not escalated across years.
