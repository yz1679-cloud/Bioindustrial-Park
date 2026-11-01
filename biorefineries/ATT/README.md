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
Tests (from the repository root): `python -m unittest discover -s biorefineries/ATT/test -p "test_att_*.py" -t .`
