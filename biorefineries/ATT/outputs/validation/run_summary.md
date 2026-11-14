# ATT run summary: OK

Output root: `C:\Users\zhouy\Bioindustrial-Park\biorefineries\ATT\outputs`

## Steps

| Step | Exit code | Seconds | Log |
|---|---:|---:|---|
| baseline_1kg | 0 | 25.5 | `validation\logs\baseline_1kg.log` |
| inventory | 0 | 24.3 | `validation\logs\inventory.log` |
| tea | 0 | 22.7 | `validation\logs\tea.log` |
| lca | 0 | 20.6 | `validation\logs\lca.log` |
| consolidated | 0 | 24.7 | `validation\logs\consolidated.log` |
| documentation | 0 | 27.1 | `validation\logs\documentation.log` |
| diagram_svg | 0 | 22.7 | `validation\logs\diagram_svg.log` |
| diagram_png | 0 | 22.4 | `validation\logs\diagram_png.log` |

## Unit tests

OK (ran 119, skipped 0, 49.8 s)

## QC tables

PASS = evaluated and passed; NOT CHECKED = not evaluated (never counted as PASS); INFORMATIONAL = design notes, flags or raw values.

| Table | PASS | FAIL | NOT CHECKED | INFORMATIONAL |
|---|---:|---:|---:|---:|
| baseline_1kg/14_Limitations_Checks.csv | 72 | 0 | 0 | 19 |
| full_scale/mass_energy/17_stream_sanity_check.csv | 86 | 0 | 0 | 0 |
| full_scale/mass_energy/22_utility_consistency.csv | 8 | 0 | 0 | 0 |
| full_scale/tea/05_checks.csv | 13 | 0 | 0 | 0 |
| full_scale/lca/08_checks.csv | 8 | 0 | 0 | 0 |
| full_scale/summary/08_consistency_checks.csv | 26 | 0 | 0 | 11 |
| documentation/26_QC_Checks.csv | 53 | 0 | 0 | 18 |
| **Total** | 266 | 0 | 0 | 48 |
