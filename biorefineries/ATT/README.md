# ATT: alkaline thermal treatment of Sargassum to H2

Independent project derived from SaBRe Scenario 5 (`biorefineries/sabre`, which it does not import or modify).
Baseline: **ATT Scenario 1** (`att_s1`). See `IMPLEMENTATION_NOTES.md` for the changes, results and open issues.

```python
from biorefineries.ATT.analyses import scenarios
sys = scenarios.create(scenarios.ATT_S1)                 # full capacity (5029.17 kg dry/h), HXN on
sys_1kg = scenarios.create(scenarios.ATT_S1, dry_kgph=1.0, hxn=False)

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
cake in both. The final F2 product is `caco3_cake` and the final F1 product `ash_residue_cake`.

Switches (`scenarios.create(...)`): `washing="washing_on"|"washing_off"` and `wash_ratio=` (F2), `wash_recycle=`,
`wash_condensate=`, `f1_wash=`, `f1_wash_ratio=`, `f1_wash_condensate=`. The defaults are in `data/att.yaml`
(`downstream.f2_washing`, `downstream.f1_washing`). A ratio of 0 means no washing.

Waste lime: `downstream.waste_lime` in `data/att.yaml` models the carbide lime of an acetylene plant as a paste (dry
basis 92 % Ca(OH)2, 4 % CaCO3, 4 % inert minerals; 40 wt % water). It is free and burden-free; the Ca(OH)2 dose follows
the stoichiometry. Trace metals and other impurities are not modeled.

Economics (`data/att_tea.yaml`): both CaCO3 cakes are sold at 100 USD/t of CaCO3 (`caco3_sales`, an **optimistic,
unverified** price; `build_att_breakdown(..., f2_sales=False)` disposes the F2 cake), and the washed ATT residue is
assumed to pay for its own disposal (`residue_sale`, net cost 0, no buyer or specification). Either assumption can be
switched off in the file.

Carbon (`data/att_lca.yaml`): the Sargassum carbon of the CaCO3 and of the lumped residue is credited as stored carbon;
the soluble Na2CO3 (`credit_soluble_carbonate: false`) and the CaCO3 of the lime are not.

Exports: `python -m biorefineries.ATT.analyses.att_washing` writes the washing-on and washing-off configurations,
equipment, material/component checks, itemized costs, the economics with and without F2 sales, and the LCA
contributions to `results/tables/att_washing_*.csv`. `python -m biorefineries.ATT.analyses.run figures` saves the
BioSTEAM flowsheet diagrams of S1 and S2 to `results/figures/`. The DCF methodology is inherited unchanged.
