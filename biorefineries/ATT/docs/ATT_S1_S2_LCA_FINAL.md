# ATT S1/S2: life-cycle GWP100 (final)

**Model state.** BioSTEAM 2.54.0. The baseline credits the **Sargassum carbon in the solids** as stored carbon: the
CaCO3 of the cakes (sold or landfilled) and the lumped residue (`att_lca.yaml carbon_storage.carbonate_storage_accounting:
inherited`, `credit_char_carbon: true`). The soluble Na2CO3 in the cakes (`credit_soluble_carbonate: false`) and the
CaCO3 of the waste lime are **not** credited. The CaCO3 cakes are dried to 1 wt % moisture (steam-heated drum dryers D2 and D3) before they are sold.
S2 results are for 7,920 h/yr underway.

## 1. Basis

| Item | Value |
|---|---|
| Functional unit | 1 kg of H2 contained in the product gas (98.89 mol % H2, 2 MPa); results in kg CO2e/kg H2 |
| Method | GWP100, IPCC AR6, using BioSTEAM characterization factors on the simulated system: `System.get_net_impact`, with contributions checked to sum to the total |
| Boundary | Gate-to-gate process plus cradle-to-gate supply of chemicals, fuel, electricity and water, wastewater treatment and landfill. **Excluded:** harvesting, collection, dewatering and transport of Sargassum (no fuel-use data), capital goods, vessel construction, propulsion fuel, H2 use |
| Allocation | None. CaCO3 leaves the system as a sold coproduct with no burden and **no substitution credit** |
| Biogenic carbon | Sargassum uptake and biogenic CO2 releases are not counted (0/0 convention). Only stored biogenic carbon may earn a credit (section 3). The CaCO3 of the carbide lime is not Sargassum carbon and is never credited |
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

## 2. S1 contributions

| Contributor | kg CO2e/kg H2 | Share of gross emissions |
|---|---:|---:|
| Natural gas, LP-steam boiler: combustion | 11.124 | 43.4 % |
| Natural gas, U2 furnace: combustion | 8.131 | 31.7 % |
| Electricity, process units | 2.264 | 8.8 % |
| NaOH makeup | 1.603 | 6.3 % |
| Natural gas upstream, boiler | 1.311 | 5.1 % |
| Natural gas upstream, U2 | 0.958 | 3.7 % |
| Electricity, cooling tower | 0.208 | 0.8 % |
| H2SO4 neutralization (purge) | 0.037 | 0.1 % |
| Wastewater treatment | 0.004 | < 0.1 % |
| Process water | 0 | — |
| Ca(OH)2 (waste lime), landfill burden | 0 | — |
| **Gross emissions** | **25.641** | 100 % |
| Biogenic carbon stored in the solids (credit) | −14.998 | |
| **Net GWP** | **10.643** | |

By stage (gross emissions):

| Stage | kg CO2e/kg H2 | Share |
|---|---:|---:|
| Onsite fuel combustion | 19.26 | 75 % |
| Natural gas supply chain | 2.27 | 9 % |
| Electricity | 2.47 | 10 % |
| Chemical supply | 1.64 | 6 % |

The footprint comes from natural-gas heat: the U2 reaction heat plus steam for drying and for evaporating the NaOH
liquor. The storage credit offsets 58 % of the gross emissions, so the net result depends on it (section 3).

**Washing and recycle (net GWP, kg CO2e/kg H2):**

| Configuration | Net GWP |
|---|---:|
| No washing | 10.10 |
| F2 wash, wash liquor recycled | 9.17 |
| + F1 wash (baseline) | 10.64 |

All rows include the CaCO3 cake dryers. The F2 wash and its recycle lower the GWP, since the recovered sodium cuts the
fresh NaOH. The F1 wash adds 1.48 kg CO2e/kg H2: its wash water (4.3 t/h) is evaporated again in EC1, whose duty rises
from 10.2 to 13.3 MW.

**CaCO3 cake drying (D2, D3):** the dryers add 1.66 kg CO2e/kg H2 (8.98 to 10.64). Almost all of it is the steam duty of the
dryers (1.99 MW, which needs about 2.5 MW LHV of boiler natural gas), plus 135 kW of electricity.

**Marine WHR contribution (S2): −1.362006 kg CO2e/kg H2.**

| WHR component | kg CO2e/kg H2 |
|---|---:|
| Avoided boiler natural gas (combustion + upstream) | −1.374081 |
| WHR pumps (electricity) | +0.012075 |

Exhaust-only WHR gives −0.787. S2 without WHR equals S1 (10.643), and S2 with all three sources is 9.281.

## 3. Carbon accounting

### 3.1 Carbon source and balance

The feed carbon is entirely organic (CHN carbon of the presscake). The NaOH carries no carbon. The carbide lime carries
a little non-Sargassum carbon: its CaCO3 (4 % of the dry lime, 30.5 kg C/h). In U2, part of the Sargassum carbon
becomes gas and part is fixed by NaOH as Na2CO3. C1 converts that Na2CO3 to CaCO3 (F2 cake). The scrubber fixes the gas
CO2 as CaCO3 (F3 cake). The carbonate carbon of the cakes is therefore **biogenic, from Sargassum**, plus the lime's own.

Plant carbon balance (kg C/h; in = out = 1,607.53):

| Stream | kg C/h | Form | Credited |
|---|---:|---|---|
| Feed | 1,577.07 | Organic | |
| Waste-lime CaCO3 (C1 lime 29.35, scrubber lime 1.11) | 30.46 | Carbonate, not Sargassum | |
| Ash/residue cake | 784.67 | Lumped residue 765.73 + Na2CO3 18.94 | Residue yes, Na2CO3 no |
| F2 CaCO3 cake | 761.03 | CaCO3 758.80 (29.35 from the lime) + Na2CO3 2.24 | CaCO3 yes (Sargassum part), Na2CO3 no |
| F3 scrubber cake | 32.39 | CaCO3 (1.11 from the lime) | Yes (Sargassum part) |
| H2 product gas | 24.94 | CH4 + residual CO2 | No (emitted) |
| Liquor purge | 4.50 | Dissolved carbonate, wastewater | No |

The wash liquors are internal recycles.

### 3.2 Storage credit

The Sargassum carbon of the CaCO3 and of the residue is credited at 44.01/12.011 kg CO2 per kg C: 1,526.46 kg C/h,
which is −14.998 kg CO2e/kg H2.

| Credited form | kg C/h | kg CO2e/kg H2 |
|---|---:|---:|
| Lumped residue (ATT char) | 765.73 | −7.523 |
| CaCO3, F2 cake (sold; Sargassum part) | 729.45 | −7.167 |
| CaCO3, F3 cake (sold; Sargassum part) | 31.28 | −0.307 |
| **Total** | **1,526.46** | **−14.998** |

Not credited:

| Carbon | kg C/h | kg CO2e/kg H2 |
|---|---:|---:|
| Soluble Na2CO3 in the ash cake and the F2 cake (leachable) | 21.18 | 0.208 |
| CaCO3 of the carbide lime (not Sargassum carbon) | 30.46 | 0.299 |
| Dissolved carbonate of the purge (wastewater) | 4.50 | 0.044 |

- **CaCO3** is insoluble and stable if landfilled. The baseline sells it, so its fate is outside the plant: calcination
  or acid use would release the CO2. The credit assumes that sold CaCO3 stays out of the atmosphere, which is a user
  decision (2026-11-01), not an established fact.
- **The lumped residue** is credited as landfilled carbon. Its composition (CH0.5O1.195) is assumed, not measured, and
  its permanence is unknown. It is half of the credit.
- **Soluble Na2CO3** has no basis for permanence and is not credited.

This is a storage assumption, not verified carbon removal. The gross emissions without any credit are 24.218
kg CO2e/kg H2.

## 4. Results (kg CO2e/kg H2)

| Case | Net GWP | Gross emissions (no storage credit) |
|---|---:|---:|
| **S1** | **10.643** | 25.641 |
| **S2 with WHR** (7,920 h) | **9.281** | 24.279 |
| S2 exhaust WHR only | 9.856 | |
| S2 without WHR | 10.643 | 25.641 |
| Storage credit in the result | −14.998 | |

**Notes outside the net result:**
- *Avoided beach decomposition.* If the Sargassum would otherwise rot on the beach, IPCC 2006 defaults give an extra
  −13.70 kg CO2e/kg H2 of avoided CH4. This depends on the counterfactual and is reported as a note only. With it,
  S1 would be −3.06.

## 5. Interpretation

1. **Pairing.** The net GWP of 10.64 (S1) pairs with the MSP of 2.03; S2 with WHR pairs 9.28 with 2.29
   (`ATT_S1_S2_TEA_FINAL.md`).
2. **Main levers.**
   - U2 and boiler natural gas make up ≈ 84 % of the gross emissions (combustion plus upstream).
   - Heat electrification or renewable heat would act on the largest share.
   - WHR removes 5.3 % of the gross emissions (S2).
   - NaOH makeup is 6.3 %.
   - The CaCO3 dryers are 1.66 kg CO2e/kg H2 (6 %).
3. **No carbon-removal claim.** The process does not establish verified net carbon removal. The storage credit
   (58 % of the gross emissions) rests on the fate of the sold CaCO3 and on landfill permanence of the residue, whose
   composition is assumed.
4. **Washing.** The F1 wash raises the GWP by 1.5 kg CO2e/kg H2 and lowers the fresh NaOH by 40 %; its MSP benefit
   depends on the assumed disposal-free residue (`ATT_S1_S2_TEA_FINAL.md`).
5. **Partial boundary.** Collection and transport are excluded, so the results understate the cradle-to-gate
   footprint. Each kg of marine fuel per wet tonne of presscake adds ≈ 0.18 kg CO2e/kg H2 (21.22 wet t/h × 3.2 kg
   CO2/kg fuel / 372.9 kg H2/h; fuel upstream excluded).
6. **Location.** The electricity factor (US average) is a placeholder. The plant uses 5.50 kWh/kg H2, so the
   range 0.3–0.9 kg CO2e/kWh changes S1 by about −0.8 to +2.5 kg CO2e/kg H2.
