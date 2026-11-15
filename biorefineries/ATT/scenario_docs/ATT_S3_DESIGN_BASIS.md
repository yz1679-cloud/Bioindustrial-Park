# ATT S3: industrial waste-heat screening (provisional)

## Status and implementation plan

S3 is an independent accounting extension around the S1 flowsheet; it does not alter S1 or S2. It simulates S1 with the existing REE switch, reconciles post-HXN utility agents, allocates temperature-feasible carbide heat once and applies incremental costs and emissions to S1. The HXN warning and non-passing frozen regression tests remain material inherited limitations. Results are provisional engineering screens, not a designed heat-exchanger network or validated facility performance.

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

`marine_whr.s1_heat_sinks` sums the unsigned `Q` of each lifecycle's `HXutility`. `System.heat_utilities` sums signed `HeatUtility` objects by agent over system cost units, including the HXN's negative original-utility adjustment and positive replacement utilities. For U3D the final `HXutility.Q` is 625.833 kW but its actual heat utility is **cooling water at -625.833 kW**, not steam. Treating that magnitude as positive steam caused the entire discrepancy. Other rows were checked against their actual utility agents; the S3-only correction uses positive residual LP steam duties, and fails if the resulting total does not reconcile.

REE-on reconciliation, kW, BioSTEAM 2.53.11:

| Unit | Description | Gross steam | HXN gross minus net | S3 net steam / system contribution | Old sink total | Old difference |
|---|---|---:|---:|---:|---:|---:|
| D0 | Feed dryer | 9294.012 | 5145.407 | 4148.605 | 4148.605 | 0 |
| D2 | CaCO3 dryer | 1961.325 | 1961.325 | 0 | 0 | 0 |
| D3 | CaCO3 dryer | 77.869 | 77.869 | 0 | 0 | 0 |
| C1 | Causticization | 1516.129 | 1516.129 | 0 | 0 | 0 |
| EC1 | NaOH evaporator | 11896.632 | -29.816 | 11926.448 | 11926.448 | 0 |
| U3D | Gas dryer regeneration | 112.292 | 112.292 | 0 | 625.833 | +625.833 |
| Total | | 24858.258 | 8783.206 | 16075.052 | 16700.886 | +625.833 |

Gross and net values are utility duties including efficiency allowances; the difference is a signed accounting change, not necessarily physical process-to-process heat. In particular, the EC1 residual utility is 29.816 kW higher than its original utility because of HXN utility/efficiency accounting; it is not negative physical heat recovery. U3D process duty is 106.677 kW: its HXN lifecycle receives 8.546 + 723.965 kW of process heat and rejects 625.833 kW as cooling, leaving 106.677 kW net. The network therefore overshoots and cools the stream; S3 does not credit that cooler as a heat sink. Gross process heating elsewhere, cooling utilities, U2 natural gas, and RO1 natural gas are not mixed into the steam comparison.

The inherited HXN warning is **related**, not merely coincidental: BioSTEAM's balance metric sums absolute heat-exchanger loads, and this overshoot-plus-cooling appears in that metric. An independent enthalpy audit of all 12 network stream lifecycles found a maximum difference of 1.1e-11 kW between each original stream enthalpy change and its lifecycle stages. The 10 process-to-process exchangers each balance their two stream enthalpy changes within 4.5e-10 kW. S3 repeats these checks and refuses results if either maximum exceeds 1e-6 times the summed absolute original process enthalpy changes. Thus these modeled stream balances close even though BioSTEAM's absolute-load metric reports 2.835% against its 2% threshold. The overshoot and corrective cooling remain physically questionable for a practical network; no warning was suppressed, and a practicable exchanger design remains outside this screening model.

The project declares `biosteam>=2.53.0`; the frozen test comments say 2.54.0. A controlled 2.54.0 install in a temporary directory, using the existing Thermosteam, failed before simulation: that release does not expose `biosteam.HeatExchangerNetwork`, which the unchanged S1 code requires. It cannot reproduce these baseline results without separate compatibility work. This does not establish the cause of the frozen numerical differences in 2.53.11.

## Verification and results

Run from repository root using the project's environment:

```powershell
.\.venv\Scripts\python.exe -m unittest biorefineries.ATT.test.test_att_s3
.\.venv\Scripts\python.exe -m biorefineries.ATT.analyses.s3_industrial
.\.venv\Scripts\python.exe -m biorefineries.ATT.analyses.s3_industrial --no-ree
.\.venv\Scripts\python.exe -m biorefineries.ATT.analyses.s3_results
```

The exporter runs both REE configurations and recomputes S1/S2/S3 in the same runtime. It creates a timestamped directory under `biorefineries/ATT/results/att_s3/` containing strict `results.json`, process-product, heat-source, heat-allocation, summary and scenario-comparison CSVs. Each case includes the configuration, S1/S3 boundary-flow fingerprint check and mass-balance audit. `--out` can select a new directory; existing directories are rejected rather than overwritten. Run `python -m biorefineries.ATT.analyses.s3_results --help` to configure host/reference hours, utilization, approach, effectiveness, capital, auxiliary electricity, heat price and allocated heat burden. The S2 row inherits the unchanged S2 accounting limitation described above.

REE-on and REE-off runs complete using BioSTEAM 2.53.11. At 7,920 h/year overlap the source provides 14.48774 MW theoretical heat, of which 13.92932 MW is above the 159.039 C steam pinch. All 13.92932 MW is extracted under the baseline demand; 1.39293 MW is lost and 12.53638 MW reaches the steam header, displacing 12.53638 MW purchased steam. Unused heat remaining at the source is 0.55842 MW. The steam utility duty is equivalent to 11.90957 MW process-side heating after the S1 steam-transfer efficiency; this conversion is not a further deduction from displaced utility. Annual delivered steam heat is 99,288.17 MWh or 357,437.40 GJ. With REE on, remaining purchased steam is 3.53867 MW; remaining total external utility heat including unchanged fired heat is 17.04174 MW. With REE off these are 3.53279 and 16.96483 MW respectively.

The incremental installed allowance is $6.268 million; incremental fixed operating allowance is $0.251 million/year; avoided steam cost is $2.197 million/year; added electricity costs about $0.078 million/year. Avoided boiler fuel is 15.67048 MW LHV using the S1 boiler efficiency of 0.80. With the $500/kW and 1% auxiliary placeholders and zero heat charge/burden, the provisional REE-on MSP is $1.462/kg H2 and GWP is 7.834 kg CO2e/kg H2. REE-off MSP is $1.526/kg H2 and GWP is 7.715 kg CO2e/kg H2. These figures include inherited S1 assumptions and are not validated design estimates. The original S2 extractor and its failing reconciliation test remain unchanged.

The S1 boundary inventory reports 100,437.762 kg/h in and out with REE on (relative difference 1.56e-12) and 100,349.924 kg/h in and out with REE off (5.30e-12). S3 is an accounting extension and does not change these flows. S3 net AOC uses the S1 breakdown coproduct-revenue convention; raw BioSTEAM AOC is reported separately.

| Scenario | Process | Heat source | Economics / GWP status |
|---|---|---|---|
| S1 | Land, REE on | Purchased utilities plus existing HXN | $1.820/kg H2; 17.637 kg CO2e/kg H2 in this environment |
| S2 | Same process, shipboard, REE on | Marine engine sources | $2.047/kg H2; 16.204 kg CO2e/kg H2, existing S2 accounting, subject to extractor issue |
| S3 | Same land process, REE on | Hypothetical scaled carbide cooling | $1.462/kg H2; 7.834 kg CO2e/kg H2, provisional assumptions above |
