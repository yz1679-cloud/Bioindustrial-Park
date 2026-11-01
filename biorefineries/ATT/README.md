# ATT: alkaline thermal treatment of Sargassum to H2

Independent project derived from SaBRe Scenario 5 (`biorefineries/sabre`, which it does not import or modify).
Baseline: **ATT Scenario 1** (`att_s1`). See `IMPLEMENTATION_NOTES.md` for the changes, results and open issues.

```python
from biorefineries.ATT.analyses.att import scenarios
sys = scenarios.create(scenarios.ATT_S1)                 # full capacity (5029.17 kg dry/h), HXN on
sys_1kg = scenarios.create(scenarios.ATT_S1, dry_kgph=1.0, hxn=False)

from biorefineries.ATT.analyses.att.breakdown import build_att_breakdown
tables = build_att_breakdown("att_s1")                   # MSP / CAPEX / OPEX / GWP, U2 balance checks
```

Configuration: `data/att.yaml` (`att.scenarios.att_s1`, `att.reactor`, `att.downstream`).
Standard exports (`test/run_att_*.py`, `tea.export_att_tea`, `lca.export_att_lca`, reporting) run `att_s1` with
`scenarios.tea_config` / `scenarios.lca_overrides`; ATT S2: `python biorefineries/ATT/analyses/att_s2_marine.py`.
Outputs: `biorefineries/ATT/outputs/`, or the root in `ATT_PROJECT_OUTPUTS_DIR` (set by `run_att_all --out`).
Tests (from the repository root): `python -m unittest discover -s biorefineries/ATT/test -p "test_att_*.py" -t .`

## F2 cake washing (same S1/S2 scenarios)

The updated default is washing_on: original C1/F2 -> native MixTank W2 -> native
RotaryVacuumFilter F2R. Select the previous process with
scenarios.create(washing="washing_off"); use washing="washing_on", wash_ratio=...
for the fresh-water ratio [kg/kg original dry F2 cake, including dissolved solids].
The final F2 product remains caco3_cake; the original cake is f2_unwashed_cake.

data/att.yaml downstream.f2_washing records the screening assumptions: 1 kg water/kg
dry cake, 25 C fresh water, 0.25 h agitated contact, one perfectly mixed dilution stage,
and refiltration to the unchanged F2 cake moisture. CaCO3 and Ca(OH)2 remain solids;
NaOH/Na2CO3 follow diluted mother liquor. No reaction or 97% purity target is imposed.
The wash filtrate f2_wash_liquor is separately neutralized/treated using the existing
ATT H2SO4 stoichiometry and wastewater price/factors; it is not recycled to EC1.

The 100 USD/t CaCO3-component sales price is an **optimistic, unverified reference**.
An approximately 84% theoretical dry purity is not a confirmed commercial specification.
build_att_breakdown(..., f2_sales=False) disposes the entire F2 cake, earns no F2
revenue or F2 avoided-disposal credit, and retains the existing F3 sales assumption.
The corresponding marine functions accept f2_sales=False.

Run python -m biorefineries.ATT.analyses.att_washing to export both operating
configurations, equipment, material/component checks, itemized costs, optimistic and
conservative S1/S2 economics, and LCA contributions to outputs/tables/att_washing_*.csv.
The inherited DCF and LCA carbon-storage methodology are unchanged. The known
inconsistency between CaCO3 sales and landfill-storage credits remains a scientific
limitation, not evidence of permanent storage.
