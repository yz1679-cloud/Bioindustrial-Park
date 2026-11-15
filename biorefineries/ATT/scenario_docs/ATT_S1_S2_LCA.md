# ATT S1/S2: life-cycle GWP100, basis and assumptions

This document records how the GWP is defined and which assumptions it rests on. It contains no results; the numbers come
from the model and are in the generated report and tables (see "Where the results are" at the end).

**Baseline.** The baseline credits the **Sargassum carbon in the solids** as stored carbon: the CaCO3 of the cakes (sold or
landfilled) and the organic char of the leached-char residue (`lca.yaml carbon_storage`). The soluble Na2CO3 in the cakes
and the CaCO3 of the waste lime are **not** credited. The CaCO3 cakes are dried to 1 wt % moisture (steam-heated drum
dryers D2 and D3) before they are sold. The baseline includes the ash split, the char split (0.15 g per g of dry feed), the
salt crystallizer and the REE recovery (HCl leach, oxalate precipitation, roast; default on, `ree_recovery=False` turns it
off). S2 is evaluated for 7,920 h/yr underway.

## 1. Basis

| Item | Value |
|---|---|
| Functional unit | 1 kg of H2 contained in the product gas (H2-rich gas, 2 MPa); results in kg CO2e/kg H2 |
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
| Natural gas, upstream | 0.0098 kg CO2e/MJ | Argonne GREET-based U.S. average |
| Burner / boiler efficiency | 0.90 / 0.80 | — |
| Electricity | 0.449 kg CO2e/kWh | GREET 2022 US mix, location placeholder |
| H2SO4 | 0.0445 kg CO2e/kg | GREET |
| Water supply / wastewater treatment | 0.46 / 0.38 kg CO2e/m3 | Zib et al. 2021 |
| Inert landfill | 0 | User decision 2026-10-17 |

## 2. Contributions

The GWP is reported as the sum of these contributors, each in kg CO2e/kg H2: natural gas of the LP-steam boiler
(combustion and upstream), natural gas of the U2 furnace and the REE roaster RO1 (combustion and upstream), electricity of
the process units and of the cooling tower, NaOH makeup, H2SO4 for the purge neutralization, wastewater treatment, process
water and the landfill burden of the waste lime (both zero in the baseline), and the credit for the biogenic carbon stored
in the solids. The gross emissions are the sum without the storage credit. The stages are the onsite fuel combustion, the
natural gas supply chain, electricity and chemical supply.

**REE recovery.** The recovery adds the power of the leach and roaster and the roaster gas, partly offset by other changes
in the process. The LCA misses the manufacture of the HCl and the oxalic acid, so its true effect is larger than reported.

**Marine WHR contribution (S2).** The recovered heat avoids the boiler natural gas of the displaced LP steam (combustion
and upstream) and adds the electricity of the WHR pumps. S2 without WHR equals S1.

## 3. Carbon accounting

### 3.1 Carbon source and balance

The feed carbon is entirely organic (CHN carbon of the presscake). The NaOH carries no carbon. The carbide lime carries
a little non-Sargassum carbon: its CaCO3 (4 % of the dry lime). In U2, part of the Sargassum carbon becomes gas, part is
fixed by NaOH as Na2CO3, and the rest is the lumped residue. C1 converts the Na2CO3 to CaCO3 (F2 cake). The scrubber fixes
the gas CO2 as CaCO3 (F3 cake). RS1 keeps 0.15 g of char per g of dry feed (the ash minerals, CharN, CharS and the organic
char) and sends the rest of the lumped residue to `att_residue_untracked`. The carbonate carbon of the cakes is
**biogenic, from Sargassum**, plus the lime's own.

The model closes the plant carbon balance (carbon in = carbon out) over these streams:

| Stream | Form | Credited |
|---|---|---|
| Feed | Organic | |
| Waste-lime CaCO3 (C1 lime, scrubber lime) | Carbonate, not Sargassum | |
| Oxalic acid (REE precipitation) | Organic, not Sargassum | |
| F2 CaCO3 cake | CaCO3 (part from the lime) + Na2CO3 | CaCO3 yes (Sargassum part), Na2CO3 no |
| F3 scrubber cake | CaCO3 (part from the lime) | Yes (Sargassum part) |
| Leached-char residue | Organic char + Na2CO3 | Char yes, Na2CO3 no |
| `att_residue_untracked` | Lumped residue beyond the char (no measured sink) | **No** (no credit, no emission counted) |
| H2 product gas | CH4 + residual CO2 | No (emitted) |
| Liquor purge | Dissolved carbonate, wastewater | No |
| Salt cake | Na2CO3 | No |
| Leach CO2 | CO2 of the carbonate that neutralizes the HCl (biogenic) | No (emitted) |
| Roaster exhaust | CO2 of the oxalate | No (emitted) |
| REE product | Na2CO3 | No |

The wash liquors are internal recycles.

### 3.2 Storage credit

The Sargassum carbon of the CaCO3 and of the char is credited at 44.01/12.011 kg CO2 per kg C. It is made of the organic
char of the residue, the Sargassum part of the CaCO3 of the F2 cake and the Sargassum part of the CaCO3 of the F3 cake.

Not credited: the soluble Na2CO3 in the residue, the F2 cake and the salt cake (leachable); the CaCO3 of the carbide lime
(not Sargassum carbon); the dissolved carbonate of the purge (wastewater); and `att_residue_untracked` (no measured sink,
counted neither as emission nor as stored).

- **CaCO3** is insoluble and stable if landfilled. The baseline sells it, so its fate is outside the plant: calcination
  or acid use would release the CO2. The credit assumes that sold CaCO3 stays out of the atmosphere, which is a user
  decision (2026-11-01), not an established fact. It is by far the largest part of the credit.
- **The char** is credited as landfilled carbon, but it is a small part of the credit: the char yield (0.15 g/g dry feed)
  is a collaborator's figure, and the residual lumped carbon is not tracked. The earlier baseline credited the whole
  lumped residue.
- **Soluble Na2CO3** has no basis for permanence and is not credited.

This is a storage assumption, not verified carbon removal.

## 4. Cases and notes outside the net result

The cases are S1, S2 with WHR (7,920 h) and S2 without WHR (equal to S1), each with and without the REE recovery. The
gross emissions without any storage credit are reported beside the net result.

- *Avoided beach decomposition.* If the Sargassum would otherwise rot on the beach, IPCC 2006 defaults give an extra
  avoided CH4. This depends on the counterfactual and is reported as a note only, not in the net result.
- *Untracked organics.* If the carbon of `att_residue_untracked` were emitted as fossil-equivalent CO2 it would add to the
  GWP; under the biogenic 0/0 convention it adds nothing.

## 5. How to read the results

1. **Pairing.** The net GWP of a case pairs with its MSP in `ATT_S1_S2_TEA.md`.
2. **Main levers.** The footprint comes from natural-gas heat: the U2 reaction heat plus the steam for drying and for
   evaporating the NaOH liquor. Heat electrification or renewable heat would act on the largest share; WHR (S2) and the
   NaOH makeup are smaller levers.
3. **No carbon-removal claim.** The process does not establish verified net carbon removal. The storage credit rests mostly
   on the fate of the sold CaCO3 and on the unmeasured char.
4. **REE recovery.** The LCA misses the manufacture of the HCl and oxalic acid, so the true increase is larger than reported.
5. **Partial boundary.** Collection and transport are excluded (no data), so the results understate the cradle-to-gate
   footprint.
6. **Location.** The electricity factor (US average) is a placeholder; a factor in the range 0.3–0.9 kg CO2e/kWh changes the
   result by an amount proportional to the plant's electricity use per kg H2.

## Where the results are

Generate them with the project interpreter; all go to the git-ignored `results/` folder:
- `python -m biorefineries.ATT.analyses.comprehensive_report`: the HTML report and `lca_breakdown.csv`,
  `carbon_flows.csv` and `elemental_balances.csv`;
- `python -m biorefineries.ATT.analyses.run lca`: the GWP workbooks of the S1 case.
