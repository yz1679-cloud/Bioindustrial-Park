# ATT S1/S2: techno-economic analysis (final)

**Model state.** BioSTEAM 2.54.0. The baseline is F2 washing on. The CaCO3 cakes of F2 and F3 are disposed, with no
CaCO3 sales.

MSP is the minimum H2 selling price in USD per kg of contained H2 (NPV = 0 at a 10 % IRR). The carbon accounting
paired with it is described in `ATT_S1_S2_LCA_FINAL.md`.

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

## 2. S1 capital and operating costs (washing on)

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

**Annual operating cost (MUSD/yr):**

| Group | Cost |
|---|---:|
| NaOH makeup | 3.59 |
| CaCO3-cake disposal (F2 + F3) | 2.98 |
| Ash/residue cake disposal | 1.95 |
| U2 natural gas | 1.84 |
| LP steam | 1.58 |
| Electricity | 0.90 |
| H2SO4 neutralization | 0.60 |
| Fixed operating cost | 0.50 |
| Wastewater | 0.29 |
| Cooling water | 0.10 |
| Process water | 0.03 |
| Ca(OH)2 (waste lime) | 0 |
| **Total** | **14.35** |

**S1 MSP breakdown (USD/kg H2, levelized at NPV = 0):**

| Component | USD/kg H2 | Share |
|---|---:|---:|
| Waste treatment and disposal (CaCO3 cakes 1.01, residue cake 0.66) | 1.97 | 36 % |
| Utilities | 1.49 | 28 % |
| Materials (almost all NaOH: 1.22) | 1.23 | 23 % |
| Capital-related (capital, debt service, tax) | 0.55 | 10 % |
| Fixed operating cost | 0.17 | 3 % |
| **MSP** | **5.407** | |

The process is dominated by operating costs. Capital is only 10 % of MSP, so the result is driven by disposal, fuel
and steam, and NaOH makeup.

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
| **MSP** | **+0.200 USD/kg H2** (S1). S2 with the same washing: +0.212 at 7,920 h, +0.301 at 2,640 h |

Washing is a reference sensitivity on the economics. It improves the modeled F2 cake purity (77.0 → 82.5 %), but the
cake is disposed, so no value is attached to that improvement.

## 4. CaCO3 cakes

Both cakes leave the plant as wet solids and are disposed at 0.04 USD/kg wet. There are no CaCO3 sales.

| | F2 washed cake | F3 scrubber cake |
|---|---:|---:|
| Wet / dry mass | 9,023.87 / 6,767.90 kg/h | 373.26 / 279.95 kg/h |
| CaCO3 component | 5,586.57 kg/h (44,245.6 t/yr) | 260.65 kg/h (2,064.4 t/yr) |
| CaCO3 purity, dry basis | 82.545 % | 93.107 % |
| Disposal cost | 2,858,762 USD/yr | 118,250 USD/yr |

The plant makes 15.7 kg of CaCO3 per kg of H2. The two cakes cost 1.01 USD/kg H2 to dispose (19 % of the MSP).

## 5. Final MSP comparison (USD/kg H2, washing on)

| Case | Hours | H2 (t/yr) | FCI (MUSD) | AOC (MUSD/yr) | MSP |
|---|---:|---:|---:|---:|---:|
| S1 | 7,920 | 2,953.56 | 12.475 | 14.352 | **5.406569** |
| S2 floating, no WHR | 7,920 | 2,953.56 | 15.594 | 14.664 | 5.649927 |
| S2 floating, exhaust WHR only | 7,920 | 2,953.56 | 16.176 | 14.493 | 5.617637 |
| **S2 floating, all WHR** | 7,920 | 2,953.56 | 16.602 | 14.365 | **5.592894** |
| S2 floating, no WHR | 2,640 | 984.52 | 15.594 | 5.429 | 7.569346 |
| S2 floating, exhaust WHR only | 2,640 | 984.52 | 16.176 | 5.379 | 7.595910 |
| **S2 floating, all WHR** | 2,640 | 984.52 | 16.602 | 5.342 | **7.614238** |

Reference only, washing off:

| Case | MSP |
|---|---:|
| S1 | 5.206415 |
| S2 no WHR, 7,920 h | 5.438419 |
| S2 WHR, 7,920 h | 5.381386 |
| S2 no WHR, 2,640 h | 7.268294 |
| S2 WHR, 2,640 h | 7.313186 |

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
- WHR cuts purchased energy by 0.319 MUSD/yr (4.414 → 4.095 MUSD/yr).

## 6. Interpretation

1. **S1 vs S2 (7,920 h).** Floating operation adds +0.243 USD/kg (5.407 → 5.650): +3.1 MUSD CAPEX from the 1.25
   factor and +0.25 MUSD/yr labor. All three WHR sources recover 0.057 USD/kg of it (5.593). S2 stays ≈ 3 %
   above S1. The marine penalty is small because capital is a small share of MSP.
2. **WHR on vs off.** At 7,920 h the 1.0 MUSD of WHR equipment is repaid by 0.32 MUSD/yr of avoided steam.
   At 2,640 h the saving falls to one-third, and WHR **raises** MSP by 0.045 USD/kg. Exhaust-only recovery has
   the better capital efficiency.
3. **Operating hours.** At 2,640 h:
   - fixed costs (CAPEX recovery, labor, FOC) are spread over one-third of the H2;
   - MSP rises from 5.59 to 7.61 USD/kg;
   - 5,280 h gives 6.10.

   For a ship-based plant, the realistic number of ATT operating hours is the largest S2-specific economic
   driver.
4. **CaCO3 cake disposal.** The two cakes are 1.01 USD/kg H2 of the MSP, the largest cost after NaOH makeup,
   larger than the S2 floating factors or WHR. It depends on the disposal price (0.04 USD/kg wet), which is an
   assumption.
5. **Other drivers:**
   - NaOH makeup is 1.22 USD/kg H2, from a 25.8 % makeup rate.
   - Fuel and steam together are 1.16 USD/kg.
   - Residue-cake disposal is 0.66 USD/kg.
   - Equipment cost-year sensitivity: CEPCI 800 (≈ 2024) instead of 596.2 raises the S1 MSP by 0.245.

**S2 floating-factor sensitivity (all WHR, 7,920 h; MSP in USD/kg H2):**

| Parameter | Low | High |
|---|---:|---:|
| CAPEX multiplier 1.10 / 1.40 | 5.498 | 5.687 |
| Labor multiplier 1 / 2 | 5.507 | 5.593 |
| WHR CAPEX × 0.5 / × 2 | 5.567 | 5.644 |
| WHR CAPEX at the IMO lower bound for power WHRS (5.2 MUSD) | — | 5.805 |
| No scavenge-air recovery | — | 5.621 |
| Engine load 0.5 / 1.0 | 5.642 | 5.516 |

Boundary reminders:
- No vessel acquisition, harvesting, collection or transport cost.
- No CH4 credit.
- No REE recovery.
- Prices are not escalated across years.
