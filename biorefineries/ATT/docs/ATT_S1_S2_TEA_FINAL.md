# ATT S1/S2: techno-economic analysis (final)

**Model state.** Commit `468d957e`. The baseline is F2 washing on. "Optimistic sales" means the CaCO3 of the F2
and F3 cakes is sold at 100 USD/t. "Conservative sales" means no F2 sales: the whole F2 cake is disposed, and F3
is still sold.

MSP is the minimum H2 selling price in USD per kg of contained H2 (NPV = 0 at a 10 % IRR). Each table states which
CaCO3 disposition it uses. MSP and GWP are only paired when they share the same disposition (see
`ATT_S1_S2_LCA_FINAL.md`).

## 1. Production and financial basis

| Item | Value | Class |
|---|---|---|
| H2 | 372.925 kg/h; 2,953.56 t/yr at 7,920 h (984.52 t/yr at 2,640 h) | Simulation (gas yields verified, see the process document) |
| H2 delivery | 98.89 mol % H2 at 2 MPa, no PSA. MSP is per kg of contained H2; CH4 in the product earns no credit | Model / [ASSUMPTION] |
| Financial method | SaBReTEA DCF: IRR 10 %, 2026–2046, MACRS-7, 21 % income tax, 40/60 construction, 60 % debt at 8 % over 10 yr, working capital 5 % of FCI, 3-month startup | Inherited SaBRe/BioSTEAM |
| Capital convention | FCI = installed equipment cost (no separate indirect costs); CEPCI 596.2 (2020 USD) | Inherited SaBRe; ATT cost year |
| Fixed operating cost | 4 % of FCI per yr (labor, maintenance, overhead) | Inherited SaBRe |
| Prices | NaOH 0.35 USD/kg; waste Ca(OH)2 0; H2SO4 0.0948 USD/kg; process water 0.000441 USD/kg; solid disposal 0.04 USD/kg wet; wastewater 0.004 USD/kg; natural gas 4.36 USD/GJ (LHV); LP steam 0.2378 USD/kmol; electricity 0.0782 USD/kWh | `att_tea.yaml`, `tea.yaml`, BioSTEAM defaults |
| Feedstock | 0 USD/t (collection and transport outside the boundary) | [ASSUMPTION] |

**DCF note (inherited, intentionally kept).** BioSTEAM 2.53.11, which the original SaBRe model inherits, deducts
the whole loan payment, principal included, from taxable income. It is kept here for consistency with SaBRe, not
as a claim that principal is tax-deductible. An independent recalculation with the alternative tax treatment
estimated:

| Case | Current model MSP | Alternative tax treatment |
|---|---:|---:|
| S1 | 3.029244 | 3.050088 |
| S2 with WHR, 7,920 h | 3.204215 | 3.232048 |
| S2 with WHR, 2,640 h | 5.136015 | 5.219512 |

These were estimated before F2 washing was added (washing off). The effect is +0.02 to +0.08 USD/kg H2.

## 2. S1 capital and operating costs (washing on, optimistic sales)

**Capital (installed, MUSD):**

| Area | Installed |
|---|---:|
| ATT reactor U2 | 2.35 |
| Residue filtration F1 | 2.30 |
| Feed drying D0 | 2.21 |
| H2 compression U3K | 1.14 |
| Gas cooling and drying | 1.13 |
| NaOH evaporation EC1 | 1.12 |
| CaCO3 filtration F2 | 0.69 |
| **F2 washing W2 + F2R** | **0.58** |
| CO2 scrubber and F3 | 0.37 |
| Causticization C1 | 0.34 |
| Residue cooling RC1 | 0.25 |
| **FCI** | **12.475** |
| Working capital | 0.624 |
| **TCI** | **13.099** |

**Annual operating cost, net of CaCO3 revenue (MUSD/yr):**

| Group | Cost |
|---|---:|
| NaOH makeup | 3.59 |
| Ash/residue cake disposal | 1.95 |
| U2 natural gas | 1.84 |
| LP steam | 1.63 |
| CaCO3-cake disposal (non-CaCO3 mass) | 1.12 |
| Electricity | 0.90 |
| H2SO4 neutralization | 0.60 |
| Fixed operating cost | 0.50 |
| Wastewater | 0.29 |
| Cooling water | 0.10 |
| Process water | 0.03 |
| Ca(OH)2 (waste lime) | 0 |
| **CaCO3 sales** | **−4.63** |
| **Net** | **7.92** |

**S1 MSP breakdown (USD/kg H2, levelized at NPV = 0):**

| Component | USD/kg H2 | Share |
|---|---:|---:|
| Utilities | 1.51 | 47 % |
| Waste treatment and disposal | 1.34 | 42 % |
| Materials (almost all NaOH: 1.22) | 1.23 | 38 % |
| Capital-related (capital, debt service, tax) | 0.55 | 17 % |
| Fixed operating cost | 0.17 | 5 % |
| CaCO3 revenue | **−1.57** | −49 % |
| **MSP** | **3.229** | |

The process is dominated by operating costs. Capital is only 17 % of MSP, so the result is driven by NaOH makeup,
fuel and steam, disposal, and the CaCO3 credit.

## 3. F2 washing increment (washing on minus off; S1)

| Item | Value |
|---|---:|
| Equipment | W2 MixTank: 3.850 m3, 0.25 h, purchase 27,819 USD, installed 45,901 USD, 0.38 kW. F2R rotary vacuum filter: 13.864 m2, purchase 251,644 USD, installed 536,101 USD, 28.78 kW |
| **FCI** | **+0.582 MUSD** |
| Fresh wash water | +25,331 USD/yr |
| Wash-liquor wastewater | +250,220 USD/yr |
| H2SO4 neutralization | +403,497 USD/yr |
| Electricity | +18,060 USD/yr |
| Fixed operating cost | +23,280 USD/yr |
| Lower F2-cake disposal (less sodium mass) | −204,645 USD/yr |
| **Net annual cost** | **+515,743 USD/yr** |
| **MSP** | **+0.200 USD/kg H2** for every case and disposition |

Washing is a reference sensitivity on the economics. It improves the modeled F2 purity (77.0 → 82.5 %), but no
market value is attached to that improvement because the price is per kg of CaCO3 component.

## 4. CaCO3 sales accounting

| | F2 washed cake | F3 scrubber cake |
|---|---:|---:|
| Wet / dry mass | 9,023.87 / 6,767.90 kg/h | 373.26 / 279.95 kg/h |
| CaCO3 component | 5,586.57 kg/h (44,245.6 t/yr) | 260.65 kg/h (2,064.4 t/yr) |
| CaCO3 purity, dry basis | 82.545 % | 93.107 % |
| Saleable fraction, optimistic / conservative | 1.0 / **0** | 1.0 / 1.0 |
| Physical disposition | The whole wet cake leaves the plant | The whole wet cake leaves the plant |
| Pricing basis | 100 USD per t of CaCO3 component (unverified, optimistic) | Same |
| Revenue, optimistic | 4,424,562 USD/yr | 206,436 USD/yr |
| Avoided disposal (sold CaCO3 not landfilled at 0.04 USD/kg) | 1,769,825 USD/yr | 82,575 USD/yr |
| Remaining disposal (moisture, Ca(OH)2, Na salts) | 1,088,937 USD/yr | 35,675 USD/yr |
| Conservative (F2 not sold) | Revenue 0; whole cake disposed: 2,858,762 USD/yr | Unchanged |

**Accounting interpretation.** No unit separates CaCO3 from the cake. The revenue/disposal split is a **net cake
price**: the CaCO3 content × 100 USD/t, minus 0.04 USD/kg × the non-CaCO3 mass. That is 0.0467 USD/kg wet F2 cake,
equivalent to a buyer discount for moisture and impurities. It is booked once, on the stream price (no double
counting).

There is no product specification, buyer or verified price:
- 82.5 % CaCO3 with 15 % Ca(OH)2 and residual sodium is **not** high-purity PCC.
- The lab ≈ 97 % purity was measured on a different, clean system.

The optimistic case is therefore an upper bound, and no F2 sales is the conservative bound.

**CaCO3 price sensitivity (S1, both cakes sold, washing on):**

| CaCO3 price | MSP (USD/kg H2) |
|---|---:|
| 0 USD/t (taken away at no cost) | 4.797 |
| 100 USD/t | 3.229 |
| 315 USD/t (approximate public industrial reference, unverified for this product) | −0.142 |
| No sales; both cakes disposed | 5.425 |

Each 100 USD/t of CaCO3 price moves the S1 MSP by ≈ 1.57 USD/kg H2. This is because the plant makes **15.7 kg of
CaCO3 per kg of H2**.

## 5. Final MSP comparison (USD/kg H2, washing on)

| Case | Hours | H2 (t/yr) | FCI (MUSD) | Net AOC (MUSD/yr) | MSP, F2 + F3 sold | MSP, F2 not sold |
|---|---:|---:|---:|---:|---:|---:|
| S1 land | 7,920 | 2,953.56 | 12.475 | 7.921 | **3.229398** | **5.326657** |
| S2 floating, no WHR | 7,920 | 2,953.56 | 15.594 | 8.233 | 3.472756 | 5.570015 |
| S2 floating, exhaust WHR only | 7,920 | 2,953.56 | 16.176 | 8.063 | 3.440466 | — |
| **S2 floating, all WHR** | 7,920 | 2,953.56 | 16.602 | 7.935 | **3.415723** | **5.512982** |
| S2 floating, no WHR | 2,640 | 984.52 | 15.594 | 3.285 | 5.392175 | 7.489434 |
| **S2 floating, all WHR** | 2,640 | 984.52 | 16.602 | 3.199 | **5.437067** | **7.534326** |

Reference only, washing off with F2 + F3 sold:

| Case | MSP |
|---|---:|
| S1 | 3.029244 |
| S2 no WHR, 7,920 h | 3.261249 |
| S2 WHR, 7,920 h | 3.204215 |
| S2 no WHR, 2,640 h | 5.091124 |
| S2 WHR, 2,640 h | 5.136015 |

**S2 cost structure (all WHR, 7,920 h):**
- Process CAPEX = 1.25 × S1 FCI = 15.594 MUSD; WHR equipment adds 1.008 MUSD after the multiplier.
- WHR equipment, installed:

| Item | USD |
|---|---:|
| Economizer | 246,980 |
| Steam drum / interface (placeholder) | 150,000 |
| Charge-air cooler | 198,398 |
| Jacket-water heat exchanger | 68,324 |
| Pumps | 56,381 |
| Piping and controls allowance | 288,033 |

- Labor = 2 × the S1 labor. The S1 labor is taken as 50 % of the S1 FOC (0.250 → 0.499 MUSD/yr).
- WHR cuts purchased energy by 0.319 MUSD/yr (4.467 → 4.148 MUSD/yr).

## 6. Interpretation

1. **S1 vs S2 (7,920 h).** Floating operation adds +0.243 USD/kg (3.229 → 3.473): +3.1 MUSD CAPEX from the 1.25
   factor and +0.25 MUSD/yr labor. All three WHR sources recover 0.057 USD/kg of it (3.416). S2 stays ≈ 6 %
   above S1. The marine penalty is small because capital is a small share of MSP.
2. **WHR on vs off.** At 7,920 h the 1.0 MUSD of WHR equipment is repaid by 0.32 MUSD/yr of avoided steam.
   At 2,640 h the saving falls to one-third, and WHR **raises** MSP by 0.045 USD/kg. Exhaust-only recovery has
   the better capital efficiency.
3. **Operating hours.** At 2,640 h:
   - fixed costs (CAPEX recovery, labor, FOC) are spread over one-third of the H2;
   - MSP rises from 3.42 to 5.44 USD/kg;
   - 5,280 h gives 3.92.

   For a ship-based plant, the realistic number of ATT operating hours is the largest S2-specific economic
   driver.
4. **CaCO3 sales.** F2 sales are worth 2.10 USD/kg H2 (3.229 vs 5.327). That is the largest single uncertainty,
   larger than the floating factors or WHR. Unless a buyer and specification for the 82.5 % cake are confirmed,
   the conservative MSP of 5.33 (S1) or 5.51 (S2 at 7,920 h) should be quoted beside the optimistic value.
5. **Other drivers:**
   - NaOH makeup is 1.22 USD/kg H2, from a 25.8 % makeup rate.
   - Fuel and steam together are 1.17 USD/kg.
   - Residue-cake disposal is 0.66 USD/kg.
   - Equipment cost-year sensitivity: CEPCI 800 (≈ 2024) instead of 596.2 raises the S1 MSP by 0.245.

**S2 floating-factor sensitivity (all WHR, 7,920 h; MSP in USD/kg H2):**

| Parameter | Low | High |
|---|---:|---:|
| CAPEX multiplier 1.10 / 1.40 | 3.321 | 3.510 |
| Labor multiplier 1 / 2 | 3.330 | 3.416 |
| WHR CAPEX × 0.5 / × 2 | 3.390 | 3.467 |
| WHR CAPEX at the IMO lower bound for power WHRS (5.2 MUSD) | — | 3.628 |
| No scavenge-air recovery | — | 3.444 |
| Engine load 0.5 / 1.0 | 3.465 | 3.357 |

Boundary reminders:
- No vessel acquisition, harvesting, collection or transport cost.
- No CH4 credit.
- No REE recovery.
- Prices are not escalated across years.
