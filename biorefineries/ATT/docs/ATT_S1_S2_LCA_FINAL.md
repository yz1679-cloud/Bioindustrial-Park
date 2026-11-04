# ATT S1/S2: life-cycle GWP100 (final)

**Model state.** BioSTEAM 2.54.0. The baseline credits the **Sargassum carbon in the solids** as stored carbon: the
CaCO3 of the cakes (sold or landfilled) and the organic char of the leached-char residue (`lca.yaml
carbon_storage`). The soluble Na2CO3 in the cakes and the CaCO3 of the waste lime are **not** credited. The CaCO3 cakes are dried to
1 wt % moisture (steam-heated drum dryers D2 and D3) before they are sold. The baseline includes the ash split, the char
split (0.15 g per g of dry feed), the salt crystallizer and the REE recovery (HCl leach, oxalate precipitation, roast;
default on, `ree_recovery=False` turns it off). S2 results are for 7,920 h/yr underway.

## 1. Basis

| Item | Value |
|---|---|
| Functional unit | 1 kg of H2 contained in the product gas (98.89 mol % H2, 2 MPa); results in kg CO2e/kg H2 |
| Method | GWP100, IPCC AR6, using BioSTEAM characterization factors on the simulated system: `System.get_net_impact`, with contributions checked to sum to the total |
| Boundary | Gate-to-gate process plus cradle-to-gate supply of chemicals, fuel, electricity and water, wastewater treatment and landfill. **Excluded:** harvesting, collection, dewatering and transport of Sargassum (no fuel-use data), capital goods, vessel construction, propulsion fuel, H2 use, the manufacture of the HCl and oxalic acid of the REE recovery (no factors in the register), the REE capture from acid mine drainage |
| Allocation | None. CaCO3 and the REE product leave the system as sold coproducts with no burden and **no substitution credit** |
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
| Natural gas, LP-steam boiler: combustion | 10.225 | 42.4 % |
| Natural gas, U2 furnace (and roaster RO1): combustion | 8.111 | 33.6 % |
| Electricity, process units | 1.906 | 7.9 % |
| NaOH makeup | 1.472 | 6.1 % |
| Natural gas upstream, boiler | 1.205 | 5.0 % |
| Natural gas upstream, U2 (and RO1) | 0.956 | 4.0 % |
| Electricity, cooling tower | 0.188 | 0.8 % |
| H2SO4 neutralization (purge) | 0.038 | 0.2 % |
| Wastewater treatment | 0.006 | < 0.1 % |
| Process water | 0 | — |
| Ca(OH)2 (waste lime), landfill burden | 0 | — |
| **Gross emissions** | **24.107** | 100 % |
| Biogenic carbon stored in the solids (credit) | −8.279 | |
| **Net GWP** | **15.828** | |

By stage (gross emissions):

| Stage | kg CO2e/kg H2 | Share |
|---|---:|---:|
| Onsite fuel combustion | 18.34 | 76 % |
| Natural gas supply chain | 2.16 | 9 % |
| Electricity | 2.09 | 9 % |
| Chemical supply | 1.51 | 6 % |

The footprint comes from natural-gas heat: the U2 reaction heat plus steam for drying and for evaporating the NaOH
liquor. The storage credit offsets 34 % of the gross emissions, so the net result depends on it (section 3).

**Washing, REE and the cake dryers (net GWP, kg CO2e/kg H2).** The first four rows are without the REE recovery:

| Configuration | Net GWP |
|---|---:|
| No washing | 16.52 |
| F2 wash, wash liquor recycled | 15.39 |
| + F1 wash | 15.71 |
| **+ REE recovery (baseline)** | **15.83** |
| Baseline without the CaCO3 cake dryers | 14.12 |

The F2 wash and its recycle lower the GWP, since the recovered sodium cuts the fresh NaOH (7,734 to 4,555 t/yr). The F1 wash
adds 0.32 kg CO2e/kg H2: its wash water is evaporated again in EC1. The REE recovery adds 0.12 (the power of the leach and
roaster, about 0.14, and the roaster gas, about 0.05, partly offset by other changes in the process) [DERIVED].

**CaCO3 cake drying (D2, D3):** the dryers add 1.70 kg CO2e/kg H2 (14.12 to 15.83), through steam (2.04 MW of duty before
heat integration) and 137 kW of electricity.

**Marine WHR contribution (S2): −1.362006 kg CO2e/kg H2.**

| WHR component | kg CO2e/kg H2 |
|---|---:|
| Avoided boiler natural gas (combustion + upstream) | −1.374081 |
| WHR pumps (electricity) | +0.012075 |

Exhaust-only WHR gives −0.787. S2 without WHR equals S1 (15.828), and S2 with all three sources is 14.466.

## 3. Carbon accounting

### 3.1 Carbon source and balance

The feed carbon is entirely organic (CHN carbon of the presscake). The NaOH carries no carbon. The carbide lime carries
a little non-Sargassum carbon: its CaCO3 (4 % of the dry lime, 31.1 kg C/h). In U2, part of the Sargassum carbon
becomes gas, part is fixed by NaOH as Na2CO3, and the rest is the lumped residue. C1 converts the Na2CO3 to CaCO3 (F2
cake). The scrubber fixes the gas CO2 as CaCO3 (F3 cake). RS1 keeps 0.15 g of char per g of dry feed (the Ash minerals,
CharN, CharS and 78.2 kg/h of organic Char) and sends the rest of the lumped residue to `att_residue_untracked`. The
carbonate carbon of the cakes is **biogenic, from Sargassum**, plus the lime's own.

Plant carbon balance (kg C/h; in = out = 1,608.90):

| Stream | kg C/h | Form | Credited |
|---|---:|---|---|
| Feed | 1,577.07 | Organic | |
| Waste-lime CaCO3 (C1 lime 29.97, scrubber lime 1.11) | 31.07 | Carbonate, not Sargassum | |
| Oxalic acid (REE precipitation) | 0.77 | Organic, not Sargassum | |
| F2 CaCO3 cake | 777.29 | CaCO3 774.77 (29.97 from the lime) + Na2CO3 2.52 | CaCO3 yes (Sargassum part), Na2CO3 no |
| F3 scrubber cake | 32.39 | CaCO3 (1.11 from the lime) | Yes (Sargassum part) |
| Leached-char residue | 66.62 | Organic char 66.52 + Na2CO3 0.10 | Char yes, Na2CO3 no |
| `att_residue_untracked` | 699.21 | Lumped residue beyond the char (no measured sink) | **No** (no credit, no emission counted) |
| H2 product gas | 24.94 | CH4 + residual CO2 | No (emitted) |
| Liquor purge | 4.54 | Dissolved carbonate, wastewater | No |
| Salt cake | 0.86 | Na2CO3 | No |
| Leach CO2 | 2.28 | CO2 of the carbonate that neutralizes the HCl (biogenic) | No (emitted) |
| Roaster exhaust | 0.77 | CO2 of the oxalate | No (emitted) |
| REE product | 0.02 | Na2CO3 | No |

The wash liquors are internal recycles.

### 3.2 Storage credit

The Sargassum carbon of the CaCO3 and of the char is credited at 44.01/12.011 kg CO2 per kg C: 842.60 kg C/h,
which is −8.279 kg CO2e/kg H2.

| Credited form | kg C/h | kg CO2e/kg H2 |
|---|---:|---:|
| Organic char of the residue | 66.52 | −0.654 |
| CaCO3, F2 cake (sold; Sargassum part) | 744.80 | −7.318 |
| CaCO3, F3 cake (sold; Sargassum part) | 31.28 | −0.307 |
| **Total** | **842.60** | **−8.279** |

Not credited:

| Carbon | kg C/h | kg CO2e/kg H2 |
|---|---:|---:|
| Soluble Na2CO3 in the residue, F2 cake and salt cake (leachable) | 3.48 | 0.034 |
| CaCO3 of the carbide lime (not Sargassum carbon) | 31.07 | 0.305 |
| Dissolved carbonate of the purge (wastewater) | 4.54 | 0.045 |
| `att_residue_untracked` (no measured sink; counted neither as emission nor as stored) | 699.21 | 6.87 |

- **CaCO3** is insoluble and stable if landfilled. The baseline sells it, so its fate is outside the plant: calcination
  or acid use would release the CO2. The credit assumes that sold CaCO3 stays out of the atmosphere, which is a user
  decision (2026-11-01), not an established fact. It is 95 % of the credit.
- **The char** is credited as landfilled carbon, but it is now only 0.654 kg CO2e/kg H2: the char yield (0.15 g/g dry
  feed) is a collaborator's figure, and the residual lumped carbon is not tracked. The earlier baseline credited the
  whole lumped residue (−7.5 kg CO2e/kg H2).
- **Soluble Na2CO3** has no basis for permanence and is not credited.

This is a storage assumption, not verified carbon removal. The gross emissions without any credit are 24.107
kg CO2e/kg H2.

## 4. Results (kg CO2e/kg H2)

| Case | Net GWP | Gross emissions (no storage credit) |
|---|---:|---:|
| **S1** | **15.828** | 24.107 |
| **S2 with WHR** (7,920 h) | **14.466** | 22.745 |
| S2 without WHR | 15.828 | 24.107 |
| Storage credit in the result | −8.279 | |
| S1 without the REE recovery | 15.708 | |

**Notes outside the net result:**
- *Avoided beach decomposition.* If the Sargassum would otherwise rot on the beach, IPCC 2006 defaults give an extra
  −13.70 kg CO2e/kg H2 of avoided CH4. This depends on the counterfactual and is reported as a note only. With it,
  S1 would be 2.13.
- *Untracked organics.* If the 699 kg C/h of `att_residue_untracked` were emitted as fossil-equivalent CO2 it would add
  6.9 kg CO2e/kg H2; under the biogenic 0/0 convention it adds nothing.

## 5. Interpretation

1. **Pairing.** The net GWP of 15.83 (S1) pairs with the MSP of 1.69; S2 with WHR pairs 14.47 with 1.92
   (`ATT_S1_S2_TEA_FINAL.md`).
2. **Main levers.**
   - U2 and boiler natural gas make up ≈ 85 % of the gross emissions (combustion plus upstream).
   - Heat electrification or renewable heat would act on the largest share.
   - WHR removes 5.6 % of the gross emissions (S2).
   - NaOH makeup is 6.1 %.
   - The CaCO3 dryers are 1.70 kg CO2e/kg H2 (7 %).
3. **No carbon-removal claim.** The process does not establish verified net carbon removal. The storage credit
   (34 % of the gross emissions) rests mostly on the fate of the sold CaCO3 and on the unmeasured char.
4. **Washing.** The F1 wash raises the GWP by 0.3 kg CO2e/kg H2 and lowers the fresh NaOH by 13 %; its MSP benefit
   depends on the assumed disposal-free residue (`ATT_S1_S2_TEA_FINAL.md`).
5. **REE recovery.** It adds 0.12 kg CO2e/kg H2 here, but the LCA misses the manufacture of the HCl (44.6 kg/h of 31 %
   solution) and oxalic acid (2.9 kg/h), so the true increase is larger.
6. **Partial boundary.** Collection and transport are excluded, so the results understate the cradle-to-gate
   footprint. Each kg of marine fuel per wet tonne of presscake adds ≈ 0.18 kg CO2e/kg H2 (21.22 wet t/h × 3.2 kg
   CO2/kg fuel / 372.9 kg H2/h; fuel upstream excluded).
7. **Location.** The electricity factor (US average) is a placeholder. The plant uses 4.66 kWh/kg H2, so the
   range 0.3–0.9 kg CO2e/kWh changes S1 by about −0.7 to +2.1 kg CO2e/kg H2.
