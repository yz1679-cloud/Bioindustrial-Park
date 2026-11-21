# ATT S3: industrial waste-heat screening (provisional)

## Status and scope

S3 is an independent accounting extension around the S1 flowsheet; it does not alter S1 or S2. It simulates S1 with the existing REE switch, reconciles post-HXN utility agents, allocates temperature-feasible carbide heat once and applies incremental costs and emissions to S1. The HXN warning remains a material inherited limitation. Results are provisional engineering screens, not a designed heat-exchanger network or validated facility performance.

This document records the design basis and assumptions. It contains no results; the numbers come from the model and are in the generated tables (see "Where the results are" at the end).

The 2013 [CSB case study](https://www.csb.gov/file.aspx?DocumentId=5665) states that the Louisville facility had one 50 MW furnace with nominal capacity of 120,000 tons/year and did not produce acetylene for sale. This is historical capacity, not verified current throughput; the report does not specify short or metric tons. No carbide or acetylene process is simulated. The baseline S1 process itself already assumes waste carbide lime; this S3 extension does not modify that assumption or imply that the host supplies it.

## Design and assumption register

| Parameter | Value | Unit | Source | Class and explanation |
|---|---:|---|---|---|
| Host historical nominal capacity | 120,000 | tons/year | CSB, 2013 | Literature; ton subtype unstated |
| Conversion to metric | 0.90718474 | t/short ton | task specification | Assumes short tons: 108,862.1688 t/year |
| Reference nominal capacity | 120,000 | metric t/year | Wang et al., conclusion | Reference scenario; not current host production |
| H1 | 12.04 | MW | Wang et al. 2025, doi:10.1016/j.psep.2025.107306 | Fig. 10 and text: 1664.4 to 800 C |
| H3 | 3.93 | MW | same | Table 1, Fig. 10 and text: 800 to 40 C; Table 4 says 400 C |
| H1 scaled | 10.9225042696 | MW | calculation | At equal operating hours and full utilization |
| H3 scaled | 3.5652360282 | MW | calculation | Same |
| Total source | 14.4877402978 | MW | calculation | Theoretical availability; not recovered heat |
| Reference/host operating hours | 7920 / 7920 | h/year | engineering assumption | Independently configurable; fixed annual nominal output gives duty proportional to reference hours / host hours |
| Utilization | 1 | fraction | engineering assumption | Scales nominal annual production; configurable 0–1 |
| Overlap | min(host hours, ATT hours) | h/year | optimistic assumption | Perfect scheduling; storage and outages not modeled |
| Minimum approach | 20 | K | task specification | Screening assumption |
| LP steam agent | 139.039 C; 344738 Pa | C; Pa | BioSTEAM LP utility agent | Condensing vapor; saturated condensate return assumed at agent temperature |
| Steam latent heat | 2147.15 | kJ/kg | BioSTEAM utility duty / steam mass flow | No extra sensible feedwater heating or blowdown modeled |
| Steam-to-process efficiency | 0.95 | fraction | BioSTEAM utility agent | Converts steam utility duty to process heat; not applied again to steam displacement |
| Transfer effectiveness | 0.90 | fraction | engineering assumption | Extracted industrial heat to useful steam; remaining 10% is a transfer loss |
| Installed WHR cost | 500 | USD/kW delivered capacity | placeholder | Configurable total allowance for high-temperature recovery interface, steam generation, pumps, loops, piping, insulation, controls and installation; not a vendor estimate |
| Auxiliary electricity | 0.01 | kW/kW delivered | placeholder | Configurable; no equipment sizing |
| Maintenance | S1 FOC fraction of incremental installed capital | fraction/year | S1 TEA | Incremental maintenance/overhead follows S1 FOC rule, no marine factors |
| Heat purchase price | 0 | USD/MWh delivered | assumption | Configurable separately from capital |
| Heat burden | 0 | kg CO2e/MWh delivered | allocation assumption | Configurable; host production excluded, equipment embodied emissions excluded as in S1 boundary |

Wang et al., *Process Safety and Environmental Protection* 199 (2025), 107306, [publisher record](https://www.sciencedirect.com/science/article/pii/S0957582025005737), analyzes a carbide–acetylene and higher-alcohols complex, including inter-plant heat use. The supplied PDF was inspected: Table 1 gives H3 as 800 to 40 C and 5.17 kW/K; Figure 10 shows 800 to 40 C and 3929.09 kW; the text agrees. Table 4 instead prints 800 to 400 C alongside 3.93 MW. This inconsistency is retained here; the 40 C interpretation is consistent with the figure, text and duty. Extending the two streams to a carbide-only host, without competing heat users, is an engineering assumption, not evidence of available Louisville heat.

## Method and limitations

The `scenarios.create(ATT_S1, ree_recovery=...)` function creates the land-based process, including or excluding LC1 and RO1 using the existing switch. `marine_whr.s1_heat_sinks` supplies the initial rows; S3 corrects matched rows from the signed HXN residual heat utility objects and verifies they sum to the actual system steam utility. None of S2's marine sources, equipment, or cost factors is used. The U2 feed preheater is disabled. Fired U2 and REO-roasting duties lack a validated transferable temperature profile and remain unmatched. This means sinks not represented by the existing steam extraction are not assessed; savings are screening bounds, not an optimized heat integration design.

S3 generates steam for the existing LP steam header rather than applying D0 or EC1 proxy temperatures to the industrial source. It reads the BioSTEAM agent temperature, pressure and vapor phase, and calculates latent enthalpy from the net utility duty and steam mass flow. The utility model condenses steam at the agent state, so this screen assumes saturated liquid returns at that temperature. No extra sensible heating of colder condensate, blowdown, flash losses, feedwater treatment or steam transport design is included; those require additional site data. The 95% steam-to-process efficiency is already embedded in the S1 utility duty. The reported process-heat equivalent uses the ratio of net process-side to utility-side steam duties; the 90% source-to-header loss is separate and is not applied a second time.

Each source has constant heat-capacity flow across its stated temperature range. Only heat above the LP agent temperature plus 20 K is offered to an isothermal steam generator. Sources are used in ascending temperature order, limited by source capacity and purchased steam demand divided by the 90% delivery factor. Allocation to residual steam users is bookkeeping on a common header; it does not assert a separate source-to-unit exchanger. Source heat is counted once. `feasible_overlap_kW` is all source heat above the pinch whether or not needed; `source_extracted_overlap_kW` is actual heat removed; `transfer_loss_overlap_kW` is extracted heat not delivered; `useful_steam_overlap_kW` is header duty. `unused_overlap_kW` equals available minus extracted, excluding transfer losses. The reported `used_average_kW` and remaining demand include the assumed overlap fraction; source values and installed capacity refer to host-operation overlap. Annual recovered heat is average kW times ATT operating hours. This is an isothermal screening construction, not equipment sizing or proof that the source interface exists.

TEA uses S1's DCF and incremental `extra_capital` and `extra_voc`; the capital allowance is installed capacity at overlap duty, and auxiliary and contractual costs scale with actual overlap. Emissions use the existing S1 boiler efficiency, natural-gas and electricity factors; recovered steam is credited once, and auxiliary electricity and an optional waste-heat burden are added. Fixed operating costs include the S1 fraction on the added capital. The incremental operating benefit excludes capital recovery, financing and taxes; MSP includes them. `s3_AOC_usd_per_year` is BioSTEAM's AOC and should not be directly compared to the breakdown summary's net AOC without matching treatment of coproduct revenue.

## Steam reconciliation and inherited HXN warning

`marine_whr.s1_heat_sinks` sums the unsigned `Q` of each lifecycle's `HXutility`. `System.heat_utilities` sums signed `HeatUtility` objects by agent over system cost units, including the HXN's negative original-utility adjustment and positive replacement utilities. For U3D the final `HXutility.Q` can be a cooling duty: its actual heat utility is **cooling water at a negative duty**, not steam. Treating that magnitude as positive steam caused an earlier discrepancy of the sink inventory. Other rows were checked against their actual utility agents; the S3-only correction uses positive residual LP steam duties, and fails if the resulting total does not reconcile.

The reconciliation, by unit (D0 feed dryer, D2 and D3 CaCO3 dryers, C1 causticization, EC1 NaOH evaporator, U3D gas dryer regeneration), compares the gross steam duty, the HXN gross-minus-net change, the S3 net steam, and the old sink total. Gross and net values are utility duties including efficiency allowances; the difference is a signed accounting change, not necessarily physical process-to-process heat. In particular, the EC1 residual utility can be higher than its original utility because of HXN utility/efficiency accounting; it is not negative physical heat recovery. The U3D lifecycle of the HXN can receive more process heat than its duty and reject the surplus as cooling, leaving a small net duty: the network then overshoots and cools the stream, and S3 does not credit that cooler as a heat sink. Gross process heating elsewhere, cooling utilities, U2 natural gas, and RO1 natural gas are not mixed into the steam comparison. How much of the U3D duty the network covers depends on the heat-integration (`hensmith`) release, which is why the tests do not pin it.

The inherited HXN warning is **related**, not merely coincidental: BioSTEAM's balance metric sums absolute heat-exchanger loads, and the overshoot-plus-cooling appears in that metric. An independent enthalpy audit of all network stream lifecycles compares each original stream enthalpy change with its lifecycle stages, and each process-to-process exchanger balances its two stream enthalpy changes. S3 repeats these checks and refuses results if either maximum exceeds 1e-6 times the summed absolute original process enthalpy changes (`test_att_s3.py` enforces them). Thus the modeled stream balances close even though BioSTEAM's absolute-load metric can exceed its 2% threshold. The overshoot and corrective cooling remain physically questionable for a practical network; no warning was suppressed, and a practicable exchanger design remains outside this screening model.

## Verification and generation

Run from the repository root using the project's environment:

```powershell
.\.venv\Scripts\python.exe -m unittest biorefineries.ATT.test.test_att_s3
.\.venv\Scripts\python.exe -m biorefineries.ATT.analyses.s3_industrial
.\.venv\Scripts\python.exe -m biorefineries.ATT.analyses.s3_industrial --no-ree
.\.venv\Scripts\python.exe -m biorefineries.ATT.analyses.s3_results
.\.venv\Scripts\python.exe -m biorefineries.ATT.analyses.s3_figures
```

The exporter runs both REE configurations and recomputes S1/S2/S3 in the same runtime. It writes strict `results.json`, process-product, heat-source, heat-allocation, summary and scenario-comparison CSVs to `biorefineries/ATT/results/s3_results/` (git-ignored; regenerated in place; `--out` selects another directory). Each case includes the configuration, the S1/S3 boundary-flow fingerprint check and the mass-balance audit. Run `python -m biorefineries.ATT.analyses.s3_results --help` to configure host/reference hours, utilization, approach, effectiveness, capital, auxiliary electricity, heat price and allocated heat burden. S3 is an accounting extension and does not change the S1 boundary flows. S3 net AOC uses the S1 breakdown coproduct-revenue convention; raw BioSTEAM AOC is reported separately. The S2 row inherits the S2 accounting limitation described in `ATT_S2_DESIGN_BASIS.md`. The S3 figure set (PDF) is generated by `analyses/s3_figures.py` into `results/s3_figures/`.

| Scenario | Process | Heat source |
|---|---|---|
| S1 | Land, REE on | Purchased utilities plus existing HXN |
| S2 | Same process, shipboard, REE on | Marine engine sources |
| S3 | Same land process, REE on | Hypothetical scaled carbide cooling |

## Where the results are

The recovered heat, the economics and the GWP of S3 are in `results/s3_results/` and in the S1, S2 and S3 comparison of
`python -m biorefineries.ATT.analyses.comprehensive_report` (`scenario_comparison.csv`). They include the inherited S1
assumptions and are not validated design estimates.

## Figure reporting conventions

The current comprehensive HTML and S3 PDF are regenerated in
`results/avoided_emissions/` by `analyses.comprehensive_report` and
`analyses.s3_figures`. Underlying process LCA GWP100 includes existing burdens,
assumed biogenic carbon storage and applicable WHR adjustments, before GCC/REO
substitution benefits. Final Net GWP100 subtracts the configured GCC and potential
contained-REO credits once. The additional beach comparison subtracts the separate
potential decomposition credit once. Storage permanence, GCC equivalence and
commercial substitution by low-grade REO remain unverified. REO upgrading
requirements and environmental burdens are unresolved. GCC means Ground Calcium
Carbonate, the conventional product assumed displaced, not a classification of
the recovered CaCO3 production pathway.

Figure 1 converts the same unrounded energy ledger between reporting bases.
The actual ATT inlet remains presscake at 76.3 wt% moisture: MJ/kg wet presscake =
MJ/kg dry solids × (1 − 0.763). The `nlr_fresh` dataset specifies 85.7 wt% moisture
(14.3% solids). The retained 87.5 wt% panel (12.5% solids) is a separate legacy
illustrative equivalent-mass reference, not that dataset's fresh-feed moisture.
The source of the legacy choice has not been established; it must not be treated
as a new measurement. Neither reference conversion simulates upstream pressing
or changes feed rates, energy duties or process calculations.

The PDF contains thirteen sequential figures after the executive summary:
energy and EROI (1–2), DCF MSP/GWP100 and decomposition comparison (3–5), H2
benchmark inputs (6), detailed Gray/Blue/Green balances (7–9), net benchmark
summary (10), sequential waterfall (11), six-configuration GWP100 comparison
(12), and potential-decomposition waterfall (13). The net treatment benchmark
balance includes H2 selling revenue and uses the existing annualized screening
capital convention, distinct from DCF MSP. Net emissions in benchmark comparisons
are relative to displaced benchmark H2 production, with and without the separate
potential beach-decomposition benefit. Figure 10 retains only these net balances.
Sensitivity accounting and numerical scenario data remain in the model and HTML;
the PDF omits the sensitivity page.

Figure 3 groups existing discounted WHR heat savings into Heating / Natural Gas
once, without a separate negative WHR bar. Auxiliary electricity, capital,
financing and fixed costs keep their existing categories. All H2 benchmarks,
revenues, credits, financial calculations and numerical results remain unchanged.
Generated values and component ledgers are in
`results/avoided_emissions/ATT_S3_Figures_data.json` and the companion PDF.
