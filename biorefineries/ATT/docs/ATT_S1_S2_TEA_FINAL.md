# ATT S1/S2: techno-economic analysis (final)

**Model state.** BioSTEAM 2.54.0. Baseline assumptions:
- The waste lime is the carbide lime of an acetylene plant (a paste with CaCO3 and inert mineral impurities), free.
- Both CaCO3 cakes (F2 and F3) are **sold** at 100 USD/t of CaCO3 (an assumption with no buyer); the non-CaCO3 mass is disposed.
- The F2 cake and the F1 ash/residue cake are washed (1 kg water per kg of dry cake) with the condensate the dissolver
  does not need. The F2 wash liquor is recycled to the dissolver and the F1 wash liquor to the carbonate solution of C1.
- The washed ATT residue (30 wt % moisture, not dried) is **assumed to pay for its own disposal**, so its net cost is 0.

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
| Prices | NaOH 0.35 USD/kg; waste Ca(OH)2 0 (fresh lime 0.28 USD/kg, not used); H2SO4 0.0948 USD/kg; process water 0.000441 USD/kg; solid disposal 0.04 USD/kg wet; wastewater 0.004 USD/kg; natural gas 4.36 USD/GJ (LHV); LP steam 0.2378 USD/kmol; electricity 0.0782 USD/kWh | `att_tea.yaml`, `tea.yaml`, BioSTEAM defaults |
| CaCO3 sales | 100 USD/t of CaCO3 component, F2 and F3 cakes (unverified) | [ASSUMPTION] |
| ATT residue | Net disposal cost 0 when washed (`residue_sale`) | [ASSUMPTION] |
| Feedstock | 0 USD/t (collection and transport outside the boundary) | [ASSUMPTION] |

## 2. S1 capital and operating costs

**Capital (installed, MUSD):**

| Area | Installed |
|---|---:|
| ATT reactor U2 | 2.38 |
| Residue filtration F1 | 2.31 |
| Feed drying D0 | 2.21 |
| **F1 washing W1 + F1R** | **2.15** |
| NaOH evaporation EC1 | 1.63 |
| H2 compression U3K | 1.14 |
| Gas cooling and drying | 1.13 |
| CaCO3 filtration F2 | 0.79 |
| **F2 washing W2 + F2R** | **0.61** |
| Causticization C1 | 0.47 |
| CO2 scrubber and F3 | 0.37 |
| Residue cooling RC1 | 0.25 |
| **FCI** | **15.441** |
| Working capital | 0.772 |
| **TCI** | **16.213** |

**Annual operating cost (MUSD/yr):**

| Group | Cost |
|---|---:|
| LP steam | 2.59 |
| U2 natural gas | 1.87 |
| NaOH makeup | 1.48 |
| CaCO3-cake disposal (non-CaCO3 mass, F2 + F3) | 1.34 |
| Electricity | 1.08 |
| Fixed operating cost | 0.62 |
| H2SO4 neutralization (purge) | 0.23 |
| Cooling water | 0.15 |
| Wastewater (excess condensate, purge, dryer water) | 0.14 |
| Process water | 0 |
| Ca(OH)2 (waste lime) | 0 |
| ATT residue disposal (net) | 0 |
| **CaCO3 sales** | **−5.22** |
| **Net** | **4.28** |

**S1 MSP breakdown (USD/kg H2, levelized at NPV = 0):**

| Component | USD/kg H2 | Share |
|---|---:|---:|
| Utilities (LP steam 0.88, natural gas 0.63, electricity 0.37, cooling water 0.05) | 1.93 | 91 % |
| Capital-related (capital, debt service, tax) | 0.68 | 32 % |
| Waste treatment and disposal (CaCO3 cakes 0.46, H2SO4 0.08, wastewater 0.05) | 0.58 | 27 % |
| Materials (almost all NaOH: 0.50) | 0.50 | 24 % |
| Fixed operating cost | 0.21 | 10 % |
| **CaCO3 sales** | **−1.77** | −83 % |
| **MSP** | **2.127** | |

The process is dominated by operating costs, and mainly by heat: steam and natural gas are 1.51 USD/kg. The CaCO3
revenue offsets most of the costs, so the MSP depends on its price (section 4).

## 3. F2 and F1 washing (S1)

| Configuration | MSP (USD/kg H2) | Net GWP (kg CO2e/kg H2) | FCI (MUSD) | AOC (MUSD/yr) | Fresh NaOH (t/yr) |
|---|---:|---:|---:|---:|---:|
| No washing, residue disposed | 3.126 | 8.87 | 12.24 | 7.65 | 9,758 |
| F2 wash, wash liquor recycled | 2.796 | 7.85 | 12.88 | 6.59 | 7,065 |
| + F1 wash, residue disposed | 2.720 | 9.22 | 15.44 | 6.03 | 4,227 |
| **+ residue pays its disposal (baseline)** | **2.127** | 9.22 | 15.44 | 4.28 | 4,227 |

| Item | Value |
|---|---|
| Wash ratio | 1 kg water per kg of dry cake, both washes; one ideal mixed stage (0.25 h) and refiltration at the cake moisture |
| Wash water | Condensate left after the dissolver (and, for F1, after the F2 wash); fresh water only as a top-up (0 in S1 and S2) |
| Wash liquors | F2: 8.9 t/h to the dissolver D1. F1: 5.0 t/h joined with the F1 filtrate and sent to C1 |
| F2 equipment | W2 MixTank 4.44 m3, installed 49,447 USD; F2R rotary vacuum filter 170.2 m2, installed 562,606 USD, 31.7 kW |
| F1 equipment | W1 MixTank 2.55 m3, installed 37,010 USD; F1R pressure filter (5,524 kg/h retentate), purchase 1.227 MUSD, installed 2.115 MUSD, 250.6 kW |

**Interpretation.**
- The F2 wash and the recycle of its liquor lower the MSP by 0.33 USD/kg H2: the recovered sodium cuts the fresh NaOH
  from 9,758 to 7,065 t/yr.
- The F1 wash recovers more sodium (fresh NaOH 4,227 t/yr), but the pressure filter F1R costs 2.1 MUSD installed and the
  added wash water must be evaporated in EC1. With the residue still disposed it lowers the MSP by only 0.08 USD/kg
  and raises the GWP by 1.37 kg CO2e/kg H2.
- Most of the MSP reduction in the last row (0.59 USD/kg H2) comes from the **assumption** that the washed residue pays
  its disposal: 5,524 kg/h × 0.04 USD/kg × 7,920 h = 1.75 MUSD/yr. There is no buyer or specification for it.

## 4. CaCO3 cakes and the ATT residue

| | F2 cake | F3 scrubber cake |
|---|---:|---:|
| Wet / dry mass | 10,439.6 / 7,829.7 kg/h | 397.9 / 298.4 kg/h |
| CaCO3 component | 6,322.95 kg/h (50,079 t/yr) | 269.88 kg/h (2,137 t/yr) |
| CaCO3 purity, dry basis | 80.756 % | 90.441 % |
| Revenue at 100 USD/t | 5,007,774 USD/yr | 213,745 USD/yr |
| Disposal of the non-CaCO3 mass | 1,304,164 USD/yr | 40,548 USD/yr |

The CaCO3 of the cakes comes from the causticization, the CO2 scrubber and the CaCO3 (4 % of the dry lime) of the
carbide lime. The plant makes 17.7 kg of CaCO3 per kg of H2.

**Accounting interpretation.** No unit separates CaCO3 from the cake. The revenue/disposal split is a **net cake
price**: the CaCO3 content × 100 USD/t, minus 0.04 USD/kg × the non-CaCO3 mass (moisture, unreacted Ca(OH)2, inert
minerals and sodium). It is booked once, on the stream price. There is no product specification, buyer or verified
price: a 80.8 % CaCO3 cake with unreacted Ca(OH)2 is **not** high-purity PCC, and the lab ≈ 97 % purity was
measured on a different, clean system. The sales case is therefore an upper bound.

**CaCO3 price sensitivity (S1):**

| CaCO3 price | MSP (USD/kg H2) |
|---|---:|
| No sales; both cakes disposed | 4.603 |
| 0 USD/t (taken away, non-CaCO3 mass disposed) | 3.895 |
| 100 USD/t (baseline) | 2.127 |
| 315 USD/t (approximate public industrial reference, unverified for this product) | −1.674 |

Each 100 USD/t of CaCO3 price moves the S1 MSP by ≈ 1.77 USD/kg H2.

**ATT residue.** The F1 cake is 5,524 kg/h wet at 30 wt % moisture (about 3,870 kg/h dry, 30,600 dry t/yr). Its
disposal at 0.04 USD/kg wet would cost 1.75 MUSD/yr (0.59 USD/kg H2). The baseline assumes the washed residue pays this
cost (net 0), for example as a sorbent or soil material. The assumption is switched off with
`att_tea.yaml residue_sale.enabled: false`.

## 5. Final MSP comparison (USD/kg H2, 7,920 h/yr)

| Case | H2 (t/yr) | FCI (MUSD) | AOC (MUSD/yr) | MSP | Net GWP (kg CO2e/kg H2) |
|---|---:|---:|---:|---:|---:|
| S1 | 2,953.56 | 15.441 | 4.282 | **2.127** | 9.22 |
| S2 floating, no WHR | 2,953.56 | 19.301 | 4.668 | 2.429 | 9.22 |
| S2 floating, exhaust WHR only | 2,953.56 | 19.883 | 4.498 | 2.396 | 8.43 |
| **S2 floating, all WHR** | 2,953.56 | 20.309 | 4.370 | **2.372** | 7.83 |

S2 (all WHR) with other residue assumptions:

| Case | MSP |
|---|---:|
| Baseline (washed residue pays its disposal) | 2.372 |
| F1 wash, residue disposed at 0.04 USD/kg wet | 2.964 |
| No F1 wash, residue disposed | 2.990 |

**S2 cost structure (all WHR):**
- Process CAPEX = 1.25 × S1 FCI = 19.301 MUSD; WHR equipment adds 1.008 MUSD after the multiplier.
- WHR equipment, installed:

| Item | USD |
|---|---:|
| Economizer | 246,980 |
| Steam drum / interface (placeholder) | 150,000 |
| Charge-air cooler | 198,398 |
| Jacket-water heat exchanger | 68,324 |
| Pumps | 56,381 |
| Piping and controls allowance | 288,033 |

- Labor = 2 × the S1 labor. The S1 labor is taken as 50 % of the S1 FOC (0.309 → 0.618 MUSD/yr).
- WHR cuts purchased energy by 0.319 MUSD/yr (5.691 → 5.372 MUSD/yr).

## 6. Interpretation

1. **S1 vs S2.** Floating operation adds +0.245 USD/kg with all WHR (2.127 → 2.372; +0.302 without WHR). The 1.25 CAPEX
   factor (+3.9 MUSD) accounts for about 0.20 of it and the doubled labor (+0.31 MUSD/yr) for about 0.11. All three WHR
   sources recover 0.057 USD/kg. S2 stays ≈ 12 % above S1.
2. **WHR.** The 1.0 MUSD of WHR equipment is repaid by 0.32 MUSD/yr of avoided steam. Each MUSD of WHR equipment lowers
   the MSP by about 0.057 USD/kg, for the exhaust-only and the full set alike. The operating hours matter: the S2
   results are at 7,920 h/yr underway, and fewer hours spread the fixed costs over less H2.
3. **CaCO3 sales.** The revenue is −1.77 USD/kg H2 of the MSP, the largest single item and an unverified one. Without
   sales the S1 MSP is 4.60. Unless a buyer and specification for the cake are confirmed, quote the no-sales value beside it.
4. **ATT residue.** Assuming that the washed residue pays its disposal lowers the MSP by 0.59 USD/kg. Without it, S1
   is 2.72 (S2 all WHR 2.96).
5. **Other drivers:**
   - NaOH makeup is 0.50 USD/kg H2, from a 10.6 % makeup rate (4,227 of 39,831 t/yr of gross NaOH).
   - Fuel and steam together are 1.51 USD/kg.
   - Equipment cost-year sensitivity: CEPCI 800 (≈ 2024) instead of 596.2 raises the S1 MSP by 0.30.

**S2 floating-factor sensitivity (all WHR; MSP in USD/kg H2):**

| Parameter | Low | High |
|---|---:|---:|
| CAPEX multiplier 1.10 / 1.40 | 2.254 | 2.489 |
| Labor multiplier 1 / 2 | 2.266 | 2.372 |
| WHR CAPEX × 0.5 / × 2 | 2.346 | 2.423 |
| WHR CAPEX at the IMO lower bound for power WHRS (5.2 MUSD) | — | 2.584 |
| No scavenge-air recovery | — | 2.400 |
| Engine load 0.5 / 1.0 | 2.421 | 2.308 |

Boundary reminders:
- No vessel acquisition, harvesting, collection or transport cost.
- No CH4 credit.
- No REE recovery.
- Prices are not escalated across years.
