# ATT S1/S2: life-cycle GWP100 (final)

**Model state.** BioSTEAM 2.54.0. The baseline is F2 washing on, with a storage credit for **all carbon in landfilled
solids**: the CaCO3, the Na2CO3 and the lumped residue (`att_lca.yaml carbon_storage.carbonate_storage_accounting:
inherited`, `credit_char_carbon: true`). The CaCO3 cakes are disposed (no CaCO3 sales).

## 1. Basis

| Item | Value |
|---|---|
| Functional unit | 1 kg of H2 contained in the product gas (98.89 mol % H2, 2 MPa); results in kg CO2e/kg H2 |
| Method | GWP100, IPCC AR6, using BioSTEAM characterization factors on the simulated system: `System.get_net_impact`, with contributions checked to sum to the total |
| Boundary | Gate-to-gate process plus cradle-to-gate supply of chemicals, fuel, electricity and water, wastewater treatment and landfill. **Excluded:** harvesting, collection, dewatering and transport of Sargassum (no fuel-use data), capital goods, vessel construction, propulsion fuel, H2 use |
| Allocation | None. CaCO3 leaves the system with no burden and **no substitution credit** |
| Biogenic carbon | Sargassum uptake and biogenic CO2 releases are not counted (0/0 convention). Only permanently stored biogenic carbon may earn a credit (section 3) |
| S2 | Incremental: S1 LCA + WHR effect (avoided boiler fuel for the displaced LP steam, plus WHR pump electricity). Recovered waste heat carries no burden because it comes from propulsion that happens anyway. Not a ship life-cycle assessment |

Emission factors:

| Factor | Value | Source |
|---|---|---|
| NaOH | 1.12 kg CO2e/kg | Collaborators' table |
| Ca(OH)2, waste lime | 0 (burden-free) | User scenario; fresh limestone lime would be 0.91 (not used) |
| Natural gas, combustion | 0.056 kg CO2/MJ LHV | IPCC 2006 |
| Natural gas, upstream | 0.0066 kg CO2e/MJ | GREET |
| Burner / boiler efficiency | 0.90 / 0.80 | — |
| Electricity | 0.449 kg CO2e/kWh | GREET 2022 US mix, location placeholder |
| H2SO4 | 0.0445 kg CO2e/kg | GREET |
| Water supply / wastewater treatment | 0.46 / 0.38 kg CO2e/m3 | Zib et al. 2021 |
| Inert landfill | 0 | User decision 2026-10-17 |

## 2. S1 contributions (washing on)

| Contributor | kg CO2e/kg H2 | Share of gross emissions |
|---|---:|---:|
| Natural gas, U2 furnace: combustion | 7.988 | 36.9 % |
| Natural gas, LP-steam boiler: combustion | 6.079 | 28.1 % |
| NaOH makeup | 3.892 | 18.0 % |
| Electricity, process units | 1.758 | 8.1 % |
| Natural gas upstream, U2 | 0.941 | 4.4 % |
| Natural gas upstream, boiler | 0.716 | 3.3 % |
| Electricity, cooling tower | 0.138 | 0.6 % |
| H2SO4 neutralization (purge + F2 wash liquor) | 0.095 | 0.4 % |
| Process water (incl. F2 wash water) | 0.010 | < 0.1 % |
| Wastewater treatment | 0.009 | < 0.1 % |
| Ca(OH)2 (waste lime), landfill burden | 0 | — |
| **Gross emissions** | **21.627** | 100 % |
| Biogenic carbon stored in landfilled solids (credit) | −15.128 | |
| **Net GWP** | **6.499** | |

By stage (gross emissions):

| Stage | kg CO2e/kg H2 | Share |
|---|---:|---:|
| Onsite fuel combustion | 14.07 | 65 % |
| Chemical supply | 3.99 | 18 % |
| Electricity | 1.90 | 9 % |
| Natural gas supply chain | 1.66 | 8 % |

The footprint comes from natural-gas heat: the U2 reaction heat plus steam for drying and NaOH evaporation. NaOH
makeup is next. The storage credit offsets 70 % of the gross emissions, so the net result depends on it (section 3).

**Washing contribution: +0.198737 kg CO2e/kg H2** (net GWP, washing on minus off).

| Washing component | kg CO2e/kg H2 |
|---|---:|
| H2SO4 neutralization | +0.064085 |
| Electricity | +0.035109 |
| Water | +0.008946 |
| Wastewater | +0.008048 |
| Lost storage credit (the Na2CO3 that washing removes from the cake) | +0.082549 |

**Marine WHR contribution: −1.390406 kg CO2e/kg H2.**

| WHR component | kg CO2e/kg H2 |
|---|---:|
| Avoided boiler natural gas (combustion + upstream) | −1.403381 |
| WHR pumps (electricity) | +0.012975 |

Exhaust-only WHR gives −0.787. Because both are per-kg-H2 rates, the WHR effect is the same at 7,920 h and
2,640 h.

## 3. Carbonate carbon accounting

### 3.1 Carbon source and balance

The feed carbon is entirely organic (CHN carbon of the presscake). The feed contains no carbonate, and the waste
lime and NaOH contain no carbon. In U2, part of the Sargassum carbon becomes gas and part is fixed by NaOH as
Na2CO3. C1 converts that Na2CO3 to CaCO3 (F2 cake). The scrubber fixes the gas CO2 as CaCO3 (F3 cake). All
carbonate carbon is therefore **biogenic, from Sargassum**.

Plant carbon balance (kg C/h; in = out = 1,577.07):

| Stream | kg C/h | Form | Credited |
|---|---:|---|---|
| Feed | 1,577.07 | Organic | |
| Ash/residue cake | 835.45 | Lumped residue 765.73 + Na2CO3 69.72 | Yes |
| F2 CaCO3 cake | 672.98 | CaCO3 670.42 + Na2CO3 2.56 | Yes |
| F3 scrubber cake | 31.28 | CaCO3 | Yes |
| H2 product gas | 24.94 | CH4 + residual CO2 | No (emitted) |
| F2 wash liquor | 8.40 | Dissolved Na2CO3 → neutralized to HCO3−, wastewater | No |
| Liquor purge | 4.02 | Dissolved carbonate, wastewater | No |

### 3.2 Storage credit

All carbon in the landfilled solids is credited at 44.01/12.011 kg CO2 per kg C: 1,539.71 kg C/h, which is
−15.128 kg CO2e/kg H2.

| Landfilled form | kg C/h | kg CO2e/kg H2 |
|---|---:|---:|
| Lumped residue (ATT char) | 765.73 | −7.523 |
| CaCO3, F2 cake | 670.42 | −6.587 |
| CaCO3, F3 cake | 31.28 | −0.307 |
| Na2CO3 in the ash cake and F2 cake | 72.28 | −0.710 |
| **Total** | **1,539.71** | **−15.128** |

- **CaCO3** is insoluble and generally stable in a landfill, so permanence is assumed.
- **The lumped residue** is credited as landfilled carbon. Its composition (CH0.5O1.195) is assumed, not measured, and
  its permanence is unknown. It is half of the credit.
- **Na2CO3** in the landfilled solids is soluble and leachable, so its permanence is also an assumption.
- **Dissolved carbonate** in the wash liquor and the purge goes to wastewater and is not credited.

This is a storage assumption, not verified carbon removal. The gross emissions without any credit are 21.627
kg CO2e/kg H2.

## 4. Results (kg CO2e/kg H2, washing on)

| Case | Net GWP | Gross emissions (no storage credit) |
|---|---:|---:|
| **S1** | **6.498662** | 21.626737 |
| **S2 with WHR** (7,920 or 2,640 h) | **5.108256** | 20.236331 |
| S2 exhaust WHR only | 5.711723 | |
| S2 without WHR | 6.498662 | 21.626737 |
| Storage credit in the result | −15.128075 | |

Reference only, washing off:

| Case | Net GWP |
|---|---:|
| S1 | 6.299926 |
| S2 with WHR | 4.909519 |

**Notes outside the net result:**
- *Avoided beach decomposition.* If the Sargassum would otherwise rot on the beach, IPCC 2006 defaults give an extra
  −13.70 kg CO2e/kg H2 of avoided CH4. This depends on the counterfactual and is reported as a note only. With it,
  S1 would be −7.20.

## 5. Interpretation

1. **Pairing.** The net GWP of 6.50 (S1) pairs with the MSP of 5.41; S2 with WHR at 7,920 h pairs 5.11 with 5.59
   (`ATT_S1_S2_TEA_FINAL.md`).
2. **Main levers.**
   - U2 and boiler natural gas make up ≈ 73 % of the gross emissions (combustion plus upstream).
   - Heat electrification or renewable heat would act on the largest share.
   - WHR removes 6.4 % of the gross emissions (S2).
   - NaOH makeup is 18 %.
3. **No carbon-removal claim.** The process does not establish verified net carbon removal. The storage credit
   (70 % of the gross emissions) rests on landfill permanence, and half of it on an assumed residue composition.
4. **Partial boundary.** Collection and transport are excluded, so the results understate the cradle-to-gate
   footprint. Each kg of marine fuel per wet tonne of presscake adds ≈ 0.18 kg CO2e/kg H2 (21.22 wet t/h × 3.2 kg
   CO2/kg fuel / 372.9 kg H2/h; fuel upstream excluded).
5. **Location.** The electricity factor (US average) is a placeholder. The plant uses 4.23 kWh/kg H2, so the
   range 0.3–0.9 kg CO2e/kWh changes S1 by about −0.6 to +1.9 kg CO2e/kg H2.
