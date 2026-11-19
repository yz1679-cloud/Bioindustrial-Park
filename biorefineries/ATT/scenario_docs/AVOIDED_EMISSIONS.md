# Optional avoided-emission indicators

These are read-only environmental accounting extensions. They do not change
the flowsheet, stream characterization factors, process impacts, original LCA,
TEA or the existing carbonate/char storage credit. Main reported CI is original
CI minus GCC displacement. A separate potential CI additionally subtracts
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
The tables retain original CI alongside GCC-adjusted main CI and potential CI
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

## Beach decomposition

Source: [Bueno et al. (2023), Sustainability 15(7), 6254](https://doi.org/10.3390/su15076254),
Tables 2-3 and section 3.2. The Brazilian mixture is 50% S. fluitans, 15% S. natans I
and 35% S. natans VIII. The wet-raw Table 3 inputs, in that order, are CH4
7.02, 4.37 and 10.1 g/kg, and CO2 20.4, 12.2 and 31.7 g/kg. Weighted factors
are calculated from those inputs, rather than inserted as an ATT operating result.

Reference raw moisture is 87.5%. The reference CH4 GWP100 is the user-requested
28. The optional sensitivity is 25.3, non-fossil methane, from [IPCC AR6 WGI
errata, version 7 October 2025](https://www.ipcc.ch/report/ar6/wg1/downloads/report/IPCC_AR6_WGI_Errata.pdf),
p. 3, corrected Table 7.15. These choices apply only to the new decomposition
indicator; the baseline inventory factors are not re-characterized. Avoided
biogenic CO2 is reported as a separate physical mass and receives no CO2e credit.

The natural reference is fresh, unprocessed Sargassum deposited on the beach
and allowed to decompose. ATT receives dewatered presscake, currently at
76.3 wt% moisture. Methane potential is primarily related to biodegradable
organic matter, rather than water content itself. Normalize the existing
published weighted wet factor to dry solids for compatibility with that feed:

```text
dry CH4 factor = 7.7005 kg CH4/t fresh / (1 - 0.875)
              = 61.604 kg CH4/t dry Sargassum
presscake dry mass = actual inlet mass - actual inlet Water mass
avoided CH4 = actual dry tonnes * dry CH4 factor * realization fraction
avoided decomposition CO2e = avoided CH4 * selected CH4 GWP100
```

The dry factor is derived from the existing weighted wet factor, not independently
recalculated from rounded species-specific dry factors. The published reference
moisture remains 87.5 wt%; actual presscake moisture is read from the model.
Moisture is needed only for conversion between fresh, presscake and dry-feed
functional units. Holding dry solids and biodegradability constant while changing
water does not change total methane potential. An equivalent fresh mass may still
be reported as an optional interpretation; it does not drive the calculation.

Dry-solids conservation through pressing is assumed, not experimentally validated.
There is no operating upstream raw-feed stream or simulated pressing balance.
The raw-feed scale and component-retention calculation in `system.py` are scale
references only. Organic-matter losses to press liquor, feed composition, ash,
biodegradability differences and actual beach methane emissions remain uncertain.
The literature factor is a semi-empirical potential from elemental composition,
Boyle's equation and biodegradability correction, not a methane measurement from
the UCLA feedstock or actual beach conditions. Applying it to ATT dry solids and
assuming complete realization remain screening assumptions.

The existing IPCC beach-rot estimate remains a separate alternative, excluded
from original CI. It is never added to the new Bueno indicator. The calculator
also refuses enabled credits if a corresponding displacement is already
registered in the system's baseline impact ledger. Combining existing storage
with the requested full methane credit requires compatible counterfactual,
product-fate and permanence evidence before making a consequential LCA claim.

## Configuration and verification

Main environmental figures always show GCC displacement as its own factor.
The decomposition configuration defaults to disabled. Named potential scenarios
enable it explicitly and explore GWP100 and CH4-realization sensitivities.
Realization fractions of 0%, 10%, 50% and 100% are illustrative screening inputs,
not measured beach-emission estimates or confidence bounds. More field data are
needed to establish actual CH4 emissions, organic losses in pressing and the
relevant beach counterfactual. The legacy IPCC counterfactual is not combined
with the Bueno scenario.

Figure 1 uses the same model energy ledger on four bases: kg H2, kg dry feed
(0 wt% moisture), kg fresh wet equivalent (87.5 wt% moisture), and kg wet-feed
equivalent (75 wt% moisture). For energy per kg dry feed, multiply by dry-feed
flow/H2-component flow for hydrogen, or by 0.125 and 0.25 for the two wet cases.
Per-tonne CI conversion uses the same solids fractions. The modeled inlet's
actual moisture is reported separately. These are normalization choices, not
changes to feed moisture, energy demand or the original process model.

Figure 2B is the main GCC-adjusted environmental breakdown without decomposition.
Its design is retained. The separate Figure 2C compares the same S3 REE On main
result against the expanded potential beach-decomposition scenario. GCC is
included in both; CH4 avoidance is the only additional term. Figure 2C includes
the source, GWP, raw-moisture and dry-solids-conservation assumptions and is
exported as a standalone PDF/PNG as well as a separate page immediately after
Figure 2B in the S3 figure book.
Gray, blue and green H2 reference figures retain separate storage, WHR, GCC
and H2-displacement terms and pair results without/with decomposition. P0 in
the commercialization waterfall disposes the cakes and has no GCC substitution;
P1 starts CaCO3 commercialization and its GCC credit. Decomposition remains a
separate potential waterfall and comparison. Older PDF and repository HTML
reports supply visual references only; every plotted operating value is
recomputed from the current model.

`data/lca.yaml`, `lca.avoided_emissions`, holds the two independent enabled
switches for diagnostic API cases, factors, product streams, species mixture and GWP sensitivity inputs.
Disabling both returns expanded CI equal to original CI. The sensitivity CSV
includes main, potential, original-only, GCC-only and decomposition-only cases in addition to
the configured diagnostic case. Main reporting always includes GCC and excludes
decomposition; changing the configured diagnostic switches does not silently
change that definition. Annual hours cancel in normalization; hydrogen uses the
H2 component, not total product-gas mass.

Tests pin the source-reference emissions and enforce component, dry-solids,
credit-ledger and functional-unit accounting. The model-invariance check compares
streams, enthalpies, utilities, TEA, original CI and existing credits before and
after calculating the indicators. Existing model and physical-balance tests
remain applicable without changing their pinned results.
