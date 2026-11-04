# ATT: alkaline thermal treatment of Sargassum to H2

Independent project derived from SaBRe Scenario 5 (`biorefineries/sabre`, which it does not import or modify).
Baseline: **ATT Scenario 1** (`att_s1`). See `docs/` for the process, TEA, LCA and design-basis documents.

```python
from biorefineries.ATT.analyses import scenarios
sys = scenarios.create(scenarios.ATT_S1)                 # full capacity (5029.17 kg dry/h), HXN on
sys_1kg = scenarios.create(scenarios.ATT_S1, dry_kgph=1.0)

from biorefineries.ATT.analyses.breakdown import build_att_breakdown
tables = build_att_breakdown("att_s1")                   # MSP / CAPEX / OPEX / GWP, U2 balance checks
```

Configuration: `data/att.yaml` (`att.scenarios.att_s1`, `att.reactor`, `att.downstream`).
Standard exports (`python -m biorefineries.ATT.analyses.run`, `tea.export_att_tea`, `lca.export_att_lca`, reporting) run `att_s1` with
`scenarios.tea_config` / `scenarios.lca_overrides`; ATT S2: `python biorefineries/ATT/analyses/att_s2_marine.py`.
Outputs: `biorefineries/ATT/results/`, or the root in `ATT_PROJECT_RESULTS_DIR` (set by `run all --out`).
Tests (from the repository root): `python -m unittest discover -s biorefineries/ATT/test -p "test_att_*.py" -t .`

## Washing, lime, sales and the residue (S1 and S2)

The baseline washes two cakes. F2 (CaCO3): the cake goes to a native MixTank W2 and a RotaryVacuumFilter F2R, and the
wash liquor is recycled to the dissolver D1. F1 (ATT residue): the cake goes to a MixTank W1 and a PressureFilter F1R
(30 wt % moisture, no dryer), and the wash liquor is combined with the carbonate solution that feeds C1. The wash
water is the condensate that the dissolver does not need (fresh water only as a top-up); the ratio is 1 kg water/kg dry
cake in both. The final F1 product is `att_char`. Both CaCO3 cakes are then dried to 1 wt % moisture before sale (`downstream.caco3_drying`): the F2
cake in a drum dryer D2 and the scrubber cake in D3, the same dryer type as the feed dryer D0. The sold streams are `caco3_cake`
and `scrubber_cake` (their undried forms are `caco3_cake_wet` and `scrubber_cake_wet`).

The washes, the cake drying, the ash split, the char split and the heat exchanger network are always part of the flowsheet; their
settings are in `data/att.yaml` (`downstream.f2_washing`, `downstream.f1_washing`, `downstream.caco3_drying`,
`downstream.char`, `feed_preparation.ash_split`, `downstream.salt_crystallizer`, `heat_recovery`).

Waste lime: `downstream.waste_lime` in `data/att.yaml` models the carbide lime of an acetylene plant as a paste (dry
basis 92 % Ca(OH)2, 4 % CaCO3, 4 % inert minerals; 40 wt % water). It is free and burden-free; the Ca(OH)2 dose follows
the stoichiometry. Trace metals and other impurities are not modeled.

REE recovery (switch `ree_recovery=` in `scenarios.create(...)`, default ON; `ree_recovery=False` gives the process without it: `downstream.ree_recovery` in `data/att.yaml`): the washed char cake is
leached with 0.1 M HCl (LC1), the REE are precipitated with oxalic acid (the leached char leaves as the residue product), and only the oxalate precipitate is
roasted at 900 C (RO1) into the `ree_product` (60 % of the REE of the initial wastewater, 1.31 wt % REO, the rest mineral filler), which is sold on its REO content (`tea.yaml prices.REO`, default 35 USD/kg REO, an assumption), and the spent leachate goes
to the dissolver D1 (the surplus condensate is the leach water). The seaweed is assumed to carry 737 ppm TREE already: the AMD capture
section (soak tank, screen, press) is NOT modeled or costed. S2 inherits it because it is the S1 process. `python -m biorefineries.ATT.analyses.ree_sensitivity` sweeps the REO grade of the product (up to the
collaborators' 98 wt % case, with the REO mass unchanged) and the REO price for S1 and S2 (`ree_grade=` in `scenarios.create`).

Economics (`data/tea.yaml`): both (dried) CaCO3 cakes are sold at 100 USD/t of CaCO3 (`caco3_sales`, an **optimistic,
unverified** price), and the washed ATT residue (the char cake) is
assumed to be taken as a sorbent at a net price of 0 (`prices.att_char`, no buyer or specification; set it to -0.04, the
disposal fee, to dispose of it).

Carbon (`data/lca.yaml`): the Sargassum carbon of the CaCO3 and of the lumped residue is credited as stored carbon;
the soluble Na2CO3 and the CaCO3 of the lime are not.

Exports: `python -m biorefineries.ATT.analyses.run figures` saves the
BioSTEAM flowsheet diagrams of S1 and S2 to `results/figures/`. The DCF methodology is inherited unchanged.
