# ATT six-case verification

Git HEAD: branch `sabre`, commit `59e7f1cb19be1b9b8aed335475a5c112514cac46`; working tree dirty; generated 2026-11-07T23:09:58.028920+00:00.
Uncommitted changes, active input SHA-256 fingerprints and dependency versions are recorded in provenance.json.

Report-generation QC: 226 PASS, 0 FAIL.
Full ATT suite: Not invoked by write_report; use --verify-tests for a release run.

| Scenario | REE | MSP (USD/kg H2) | Net GWP (kg CO2e/kg H2) | Net OPEX (USD/year) | WHR (kW) | Residual heat (kW) |
|---|---|---:|---:|---:|---:|---:|
| S1 | On | 1.85420646 | 17.15869700 | 3564741.76 | 0.000000 | 28905.613371 |
| S2 | On | 2.08109738 | 15.72645039 | 3638695.86 | 1819.058047 | 27086.555324 |
| S3 | On | 1.49643947 | 7.35581761 | 1695719.55 | 12536.384796 | 16369.228575 |
| S1 | Off | 1.84222142 | 16.98688846 | 3696300.82 | 0.000000 | 28842.444567 |
| S2 | Off | 2.04398179 | 15.55464186 | 3738047.68 | 1819.058047 | 27023.386520 |
| S3 | Off | 1.48445443 | 7.18400908 | 1827278.61 | 12536.384796 | 16306.059770 |

Baseline net GWP includes the existing permanent-storage assumption. Optional beach decomposition is outside it.
REE economics: all six independent DCF roots agree; REO and CaCO3 revenues are credited once. Annualized cost stacks use screening capital recovery and keep DCF MSP separate. See REE_TEA_VERIFICATION.md for the numeric On/Off reconciliation.
All six balance rows use the common ATT flowsheet; S2/S3 WHR accounting leaves physical boundary streams unchanged.

Remaining scientific limitations: UCLA insoluble-residue/reagent basis and low-concentration recovery; unverified REO saleability and oxide basis; unresolved organics; lime assay/supply/handling; carbon-storage permanence; and host heat surplus, competing users and screening equipment costs.
The H3 interpretation follows the prior supplied-PDF review recorded in docs/ATT_S3_DESIGN_BASIS.md; no new literature validation is claimed.
