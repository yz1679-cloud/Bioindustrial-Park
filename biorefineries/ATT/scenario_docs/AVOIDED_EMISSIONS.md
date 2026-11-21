# Optional avoided-emission indicators

These are read-only environmental accounting extensions. They do not change
the flowsheet, stream characterization factors, process impacts, original LCA,
TEA or the existing carbonate/char storage credit. Main reported CI is original
CI minus GCC and potential REO displacement. A separate potential CI additionally subtracts
assumption-dependent beach-decomposition avoidance; it is not the default result.
Credits are positive reductions; the existing storage credit is negative and
already included in original CI. It must not be subtracted again.

Run from the repository root:

```text
python -m biorefineries.ATT.analyses.avoided_emissions
```

The command automatically creates `results/avoided_emissions/`. Its comprehensive
HTML, Markdown report, CSV/JSON tables, figure files and sensitivity outputs all
stay there, including when `ATT_PROJECT_RESULTS_DIR` is set. It does not run the
original exporters or modify other result folders. Re-running replaces its named
artifacts in place. The existing `**/results` Git-ignore rule covers the folder.
The comprehensive report and S3-figures commands now also default to this folder.
The combined command above regenerates both reports. The prior result folders
are retained without being overwritten.

Generated operating results are in
[the dedicated report](../results/avoided_emissions/avoided_emissions_report.md) and
[the comprehensive HTML](../results/avoided_emissions/ATT_S1_S2_S3_Comprehensive_Report.html).
The tables retain original CI alongside GCC/REO-adjusted main CI and potential CI
for S1/S2/S3 with REE On and Off. S2/S3 retain their existing WHR
adjustments and share the existing physical ATT production flows.

## Conventional GCC substitution

The input factor is **0.0125 kg CO2e/kg pure CaCO3**, converted from 12.5 kg CO2e
per declared metric tonne. Source: [Lafarge Granulats (2026), Ground Calcium
Carbonate, EPD-IES-0031144:001](https://www.environdec.com/library/epd31144),
GWP-total, A1-A3 cradle-to-gate, version 19 August 2026.

The calculation reads `imass['CaCO3']` from both final product cakes,
`caco3_cake` and `scrubber_cake`, and multiplies the sum by the factor once.
It includes carried-in waste-lime carbonate in these sold components. Total
mixed-product mass, water and other impurities receive no displacement credit.
Existing storage retains its separate exclusion of waste-lime carbon.
Equivalent substitution is assumed; product-quality equivalence, treatment to
achieve that quality, and market displacement are not established.

## Potential conventional mixed REO substitution

The configurable screening factor is **21.08 kg CO2e/kg contained REO**, with
substitution fraction **1.0** (hypothetical 100% displacement). Source:
[Wan, C., Zhou, D., and Xue, B. (2022), Processes 10(7), 1354](https://doi.org/10.3390/pr10071354),
Table 4, reporting a 95% confidence interval of **17.8–24.3 kg CO2e/kg REO**.
The paper's reference output is 1 kg mixed rare earth oxide product; Section 2.3
describes a 92% REO product. Its boundary spans ionic-clay mining/in situ ammonium
salt leaching, carbonate production and oxidation roasting in southern China.
The authors call the inventory door-to-door (B2B); equipment, infrastructure
and waste disposal are excluded. This is a regional process proxy, not a
universal conventional REO burden or a harmonized ATT substitution study.

As explicitly specified for this screening calculation, the published factor
is applied directly per kg modeled contained REO, without dividing by 0.92.
That mapping retains a reference-product purity qualification: the paper's
mixed product and ATT's low-grade mineral/salt residue are not equivalent
commercial products. No direct commercial substitution has been demonstrated.
Further separation, upgrading, their yields and environmental burdens remain
unresolved and are excluded; no upgrading process is invented here.

The calculation reads only `ree_product.imass['REO']` from a boundary product,
never total product-stream mass. REE Off has no such product and receives zero.
Both factor and fraction are in `data/lca.yaml`,
`lca.avoided_emissions.avoided_reo_production_emissions`. The credit is a separate
positive reduction in the reporting LCA ledger alongside GCC, never a stream
price, TEA revenue or a second system impact. Main CI subtracts it once;
potential CI uses the same main result before the separate methane reduction.
The original uncredited ATT CI remains available for comparisons.

The active recovery is performance-specified. Incoming TREE is assumed enriched
seaweed loading (737 ppm dry basis), represented from the inlet onward as an
inert oxide-equivalent component with REO/TREE = 1.169. The recovery target is
60% of the separate wastewater reference (1.4 mg TREE/L at 2.5 g dry seaweed/L),
capped by available char REO and oxalate stoichiometry. It is not 60% of the
incoming enriched-feed TREE. Transfer of that recovery to dilute feed is an
assumption. The configured 1.31 wt% REO grade is imposed by mineral filler;
existing documentation flags the experimental TREE versus REO assay basis.
Element-specific REE composition and oxidation reactions are absent. Oxygen
is already included in the inlet oxide-equivalent mass carved from Ash; no
additional oxide oxygen is taken from roaster air. Conservation can therefore
be verified for the REO pseudo-component and its configured TREE equivalent,
not for individual rare earth elements or experimentally measured oxidation.
These process assumptions are preserved. Numerical audit and unit balances are
in [the generated audit](../results/ree_recovery/ree_mass_balance_report.md).

## Beach decomposition

The counterfactual is the actual ATT presscake left to decompose on a beach.
The active `nlr_pressed` chemical composition is unchanged. The calculation
sums CHONS atom inventories from the process biomass pseudo-components and
normalizes to carbon. It excludes inlet water and inorganic Ash, NaCl, KCl
and REO. Protein sulfur is included; no unrelated sulfur assay is substituted.
Atomic masses come from the same elements library as ThermoSTEAM molecular
weights. The pre-existing carbon-fate ledger retains its rounded carbon atomic
mass to preserve baseline accounting.

Original organic matter is allocated between anaerobic fraction `f` and aerobic
fraction `1-f`. Reference `f = 0.40` is an assumed screening allocation, not an
experimentally established beach-wide ratio. Allocation occurs before applying
biodegradability or mineralization.

For organic formula CaHbOcNdSe, Boyle coefficients are:

```text
y_CH4 = a/2 + b/8 - c/4 - 3d/8 - e/4
y_CO2 = a/2 - b/8 + c/4 + 3d/8 + e/4
CH4 produced = formula kmol * f * BI_an * y_CH4 * MW_CH4
anaerobic CO2 = formula kmol * f * BI_an * y_CO2 * MW_CO2
aerobic CO2 = organic C mass * (1-f) * MF_aer * MW_CO2 / AW_C
atmospheric CH4 = CH4 produced * methane realization
additional methane climate impact = atmospheric CH4 * GWP100
```

Boyle stoichiometry is reproduced by
[Achinas and Euverink (2016)](https://doi.org/10.1016/j.reffit.2016.08.001) and
[Bueno et al. (2023), Eq. 1](https://doi.org/10.3390/su15076254). The previous
Bueno mixture factor is superseded and is not an input to this model.

Anaerobic BI is the unweighted mean of 0.17, 0.29 and 0.37 from
[Milledge et al. (2020), Table 11](https://doi.org/10.3390/en13061523), giving
0.27666666666666667. These are methane-potential-based indices from different
Sargassum species. Applying the same BI to anaerobic CO2 is an approximation.
The anaerobic BI parameter is applied once within the anaerobic pathway.

Aerobic mineralization is assumed to be **0.2766666667**, matching the
anaerobic-derived mean BI numerically. Transferring this 27.67% BI to aerobic
mineralization is a modeling assumption, **not an independently validated
aerobic biodegradability value**. The factors remain separately configurable:
varying anaerobic BI does not change the aerobic factor. Original organic
matter is allocated first, then each pathway's factor is applied once.
Fully aerobic decomposition produces no methane in this model.

The aerobic sensitivity includes the revised reference and retains 0.30, 0.40
and 0.50 as comparison values. The retained values were initially informed by
analogous kelp research, [Boldreel et al. (2023), MEPS 709](https://doi.org/10.3354/meps14285);
they neither validate the new reference nor define a measured Sargassum
beach-specific range or calibrated uncertainty interval.

Reference methane realization is 1.0. It represents the net fraction of modeled
CH4 production reaching the atmosphere, aggregating suppression, oxidation or
retention. Full realization is not a verified field emission rate. Unrealized
methane is not automatically reclassified as atmospheric CO2.

Non-fossil methane GWP100 is 25.3, attributed to the
[IPCC AR6 WGI errata, 7 October 2025](https://www.ipcc.ch/report/ar6/wg1/downloads/report/IPCC_AR6_WGI_Errata.pdf),
p. 3, corrected Table 7.15. Baseline inventory factors are unchanged. Biogenic
CO2 is reported separately as modeled formation, with no climate credit. In
waterlogged environments, inorganic-carbon formation need not equal direct
atmospheric CO2 release.

The carbon ledger retains unmineralized organic carbon explicitly. Methane
and CO2 formation cannot consume more carbon than allocated to each pathway.
No legacy IPCC equation, GWP-minus-CO2 subtraction, or raw-feed moisture
conversion enters the new indicator. Existing storage remains counted once
in original CI. Combining storage and methane avoidance still requires
compatible carbon-fate, product-fate and permanence evidence; this implementation
does not establish that consequential claim.

## Configuration, normalization and verification

`data/lca.yaml`, `lca.avoided_emissions`, holds independent GCC/REO/decomposition
switches and decomposition parameters. Decomposition defaults to disabled;
main reported CI includes GCC and configured REO displacement and excludes decomposition. Named potential
cases explicitly enable the additional methane indicator. Disabling all three
credits in the diagnostic API returns original CI.

Gas masses and methane climate impact are normalized using actual inlet wet
mass, inlet dry mass and scenario H2 component production. Outputs use tonnes
wet ATT presscake, tonnes dry Sargassum and kg H2. The decomposition scenario
does not use fresh-feed equivalents. Existing energy-only reference-basis
figures retain their original conversions and operating values.

One-at-a-time sensitivities vary:

- Anaerobic fraction: 0, 0.2, 0.4, 0.6, 0.8, 1.
- Anaerobic BI: 0.17, its reference mean, 0.37.
- Aerobic mineralization: 0.2766666667 (reference), 0.30, 0.40, 0.50.
- Atmospheric methane realization: 0, 0.1, 0.5, 1.

Every sweep holds the remaining parameters fixed. Physical biogenic CO2 and
methane climate impact use distinct quantities and axes. Generated data and
figures are in [the sensitivity CSV](../results/avoided_emissions/avoided_emissions_sensitivity.csv)
and [the sensitivity figure](../results/avoided_emissions/potential_decomposition_sensitivity.pdf).
Operating results belong in these generated artifacts, not this document.

Figure 2B retains the main GCC/REO-adjusted environmental breakdown. Figure 2C and
the additional comparison/waterfall charts use only the mechanistic methane
indicator. GCC is included consistently in main and potential comparisons;
existing carbonate/char storage is never subtracted again. Historical IPCC
calculations remain in baseline analysis code for compatibility and are not
combined with this scenario. The comprehensive report's optional comparison
uses the new mechanistic indicator.

Regenerate the stable comprehensive HTML and S3 figure book from the repository
root, or with that root on PYTHONPATH:

```text
python -m biorefineries.ATT.analyses.comprehensive_report
python -m biorefineries.ATT.analyses.s3_figures
```

Tests pin the reported reference and enforce elemental/carbon balance, pathway
allocation, independent mineralization, atmospheric methane accounting and
functional-unit conversions. The invariance test compares process streams,
enthalpies, utilities, TEA, original CI and existing storage before and after
calculating the indicator. Existing baseline pins are retained unchanged.
