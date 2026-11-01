# ATT S1/S2: life-cycle GWP100 (final)

**Model state.** Commit `468d957e`. The baseline is F2 washing on, with **conservative carbonate-storage
accounting** (`att_lca.yaml carbon_storage.carbonate_storage_accounting: conservative`). The inherited credit is
reported only as a labeled comparison.

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
| Ca(OH)2, waste lime | 0 (burden-free) | User scenario; limestone 0.91 is a sensitivity only |
| Natural gas, combustion | 0.056 kg CO2/MJ LHV | IPCC 2006 |
| Natural gas, upstream | 0.0066 kg CO2e/MJ | GREET |
| Burner / boiler efficiency | 0.90 / 0.80 | — |
| Electricity | 0.449 kg CO2e/kWh | GREET 2022 US mix, location placeholder |
| H2SO4 | 0.0445 kg CO2e/kg | GREET |
| Water supply / wastewater treatment | 0.46 / 0.38 kg CO2e/m3 | Zib et al. 2021 |
| Inert landfill | 0 | User decision 2026-10-17 |

## 2. S1 contributions (washing on, F2 + F3 sold, conservative)

| Contributor | kg CO2e/kg H2 | Share |
|---|---:|---:|
| Natural gas, U2 furnace: combustion | 7.988 | 36.6 % |
| Natural gas, LP-steam boiler: combustion | 6.273 | 28.7 % |
| NaOH makeup | 3.892 | 17.8 % |
| Electricity, process units | 1.758 | 8.0 % |
| Natural gas upstream, U2 | 0.941 | 4.3 % |
| Natural gas upstream, boiler | 0.739 | 3.4 % |
| Electricity, cooling tower | 0.142 | 0.6 % |
| H2SO4 neutralization (purge + F2 wash liquor) | 0.095 | 0.4 % |
| Process water (incl. F2 wash water) | 0.010 | < 0.1 % |
| Wastewater treatment | 0.009 | < 0.1 % |
| Ca(OH)2 (waste lime), landfill burden | 0 | — |
| Carbonate storage credit (nothing landfilled, everything sold) | 0 | — |
| **Total** | **21.848** | |

By stage:

| Stage | kg CO2e/kg H2 | Share |
|---|---:|---:|
| Onsite fuel combustion | 14.26 | 65 % |
| Chemical supply | 3.99 | 18 % |
| Electricity | 1.90 | 9 % |
| Natural gas supply chain | 1.68 | 8 % |

The footprint comes from natural-gas heat: the U2 reaction heat plus steam for drying and NaOH evaporation. NaOH
makeup is next.

**Washing contribution: +0.116188 kg CO2e/kg H2.**

| Washing component | kg CO2e/kg H2 |
|---|---:|
| H2SO4 neutralization | +0.064085 |
| Electricity | +0.035109 |
| Water | +0.008946 |
| Wastewater | +0.008048 |

Under inherited accounting the washing increment is +0.198737. The extra 0.082549 there is the loss of the
storage credit on Na2CO3 that washing removes from the cake.

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

| Stream | kg C/h | Form |
|---|---:|---|
| Feed | 1,577.07 | Organic |
| Ash/residue cake | 835.45 | Lumped residue 765.73 (not credited, provisional) + Na2CO3 69.72 |
| F2 CaCO3 cake | 672.98 | CaCO3 670.42 + Na2CO3 2.56 |
| F3 scrubber cake | 31.28 | CaCO3 |
| H2 product gas | 24.94 | CH4 + residual CO2 |
| F2 wash liquor | 8.40 | Dissolved Na2CO3 → neutralized to HCO3−, wastewater; never credited |
| Liquor purge | 4.02 | Dissolved carbonate, wastewater |

### 3.2 Carbonate formation is not long-term storage

**Formation** means CaCO3 exists in the cake. **Storage** needs the carbonate to stay out of the atmosphere for the
long term, which depends on where it goes.

- **Sold CaCO3.** The end use is unknown. In cement or lime kilns, and in any acid application, the CO2 is
  released. As a filler, retention depends on product life and end of life. **Conservative treatment: no storage
  credit and no substitution credit.**
- **Landfilled CaCO3** (only in the conservative-sales case, where the F2 cake is disposed). CaCO3 is insoluble and
  generally stable in a landfill, so it is credited at 44.01/12.011 kg CO2 per kg C, with permanence assumed. This
  is reported as a separate line. It is a storage assumption, not verified carbon removal.
- **Soluble Na2CO3** in landfilled solids (cake moisture, ash cake). It is leachable, with no basis for permanence,
  so it is not credited.

Accounting is tied to the TEA disposition: one helper (`lca.caco3_saleable_fraction`) gives the sold share to both
the TEA and the LCA. Every kg of CaCO3 carbon is either sold (revenue, no credit) or landfilled (credit, no
revenue), never both. This is enforced by a regression test.

**Inherited accounting** (comparison only) credited all non-residue carbon of the cakes, sold or not: 773.98 kg C/h,
−7.6046 kg CO2e/kg H2. Of that, sold CaCO3 is −6.894 and soluble Na2CO3 is −0.710. It treats sold CaCO3 as
landfilled, so the same material earns revenue and a storage credit. It is **not** used for conclusions.

## 4. Results (kg CO2e/kg H2, washing on)

Each column keeps the same CaCO3 disposition as the TEA case it is paired with.

| Case | Conservative, F2 + F3 sold (pairs with optimistic MSP) | Conservative, F2 not sold (pairs with conservative MSP) | Inherited credit (comparison only) |
|---|---:|---:|---:|
| **S1** | **21.847577** | **15.260492** | 14.243019 |
| **S2 with WHR** (7,920 or 2,640 h) | **20.457170** | **13.870086** | 12.852612 |
| S2 without WHR | 21.847577 | 15.260492 | 14.243019 |
| Storage credit in the result | 0 | −6.587084 (landfilled F2 CaCO3) | −7.604558 |

In the "F2 not sold" column:
- the whole F2 cake is landfilled, as in the TEA (2.86 MUSD/yr disposal), and its CaCO3 (670.42 kg C/h) is
  credited;
- F3 is still sold and not credited;
- soluble carbonate is not credited.

Reference only, washing off:

| Case | Conservative, sold | Conservative, F2 not sold | Inherited |
|---|---:|---:|---:|
| S1 | 21.731389 | 15.144304 | 14.044282 |
| S2 with WHR | 20.340983 | 13.753898 | 12.653875 |

**Notes outside the net result:**
- *Avoided beach decomposition.* If the Sargassum would otherwise rot on the beach, IPCC 2006 defaults give an extra
  −13.70 kg CO2e/kg H2 of avoided CH4. This depends on the counterfactual and is reported as a note only.
- *Provisional residue.* Crediting the carbon of the lumped residue (not measured, permanence unknown) would lower
  S1 to 14.32 (sold) or 7.74 (F2 not sold). It is not used.

## 5. Interpretation

1. **Pairing.** The defensible pairs are:
   - optimistic sales: MSP 3.23 with GWP 21.85 (S1); MSP 3.42 with GWP 20.46 (S2 WHR, 7,920 h);
   - conservative sales: MSP 5.33 with GWP 15.26 (S1); MSP 5.51 with GWP 13.87 (S2).

   Selling the CaCO3 improves the economics but gives up the landfill-storage claim. That is a real
   economic–climate trade-off, not an artifact. Never combine the optimistic MSP with the inherited or
   landfilled-credit GWP.
2. **Main levers.**
   - U2 and boiler natural gas make up ≈ 73 % of the total (combustion plus upstream).
   - Heat electrification or renewable heat would act on the largest share.
   - WHR removes 6.4 % (S2).
   - NaOH makeup is 18 %.
3. **No carbon-removal claim.** The process does not establish verified net carbon removal. Any storage credit
   rests on the landfill permanence of CaCO3, and only for material that is actually landfilled.
4. **Partial boundary.** Collection and transport are excluded, so the results understate the cradle-to-gate
   footprint. Each kg of marine fuel per wet tonne of presscake adds ≈ 0.18 kg CO2e/kg H2 (21.22 wet t/h × 3.2 kg
   CO2/kg fuel / 372.9 kg H2/h; fuel upstream excluded).
5. **Location.** The electricity factor (US average) is a placeholder. The plant uses 4.23 kWh/kg H2, so the
   range 0.3–0.9 kg CO2e/kWh changes S1 by about −0.6 to +1.9 kg CO2e/kg H2.
