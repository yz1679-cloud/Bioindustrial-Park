# SaBRe ATT: alkaline thermal treatment of *Sargassum* to hydrogen (BioSTEAM)

Process model of alkaline thermal treatment (ATT) of *Sargassum* with NaOH at
500 °C to hydrogen, with NaOH recovery by causticization, built on the SaBRe
(Sargassum Biorefinery) framework in BioSTEAM. It provides the laboratory
experimental dataset, a 1 kg dry/h baseline, a full-scale plant
(15,000 wet t/d) with material, element, Na, water and energy balances, a
preliminary TEA (H₂ minimum selling price) and a GWP100 LCA, gas-yield
scenarios, and a comparison of laboratory and plant results.

> **Data availability.** `data/att_experiment.yaml`
> and the measured gas yields in `data/att.yaml` are unpublished laboratory
> data of the UCLA collaborators. They may only be redistributed or made public
> with the collaborators' permission. See [Data sources](#data-sources).

## Installation

Tested with Python 3.12 and the versions in `requirements-att.txt`. From a
clone of the repository:

```
git clone https://github.com/yz1679-cloud/Bioindustrial-Park.git
cd Bioindustrial-Park
git checkout att-model-refactor
python -m venv .venv
.venv\Scripts\activate            # Windows  (Linux/macOS: source .venv/bin/activate)
pip install -e .
pip install -r biorefineries/sabre/requirements-att.txt
```

`pip install -e .` (editable) is recommended. The process flow diagrams also
need the Graphviz `dot` program (https://graphviz.org/download/) on the PATH.

## Run

All results, in dependency order, from any working directory:

```
python -m biorefineries.sabre.test.run_att_all                     # results + unit tests + QC tally
python -m biorefineries.sabre.test.run_att_all --out D:\att_test     # another output root
python -m biorefineries.sabre.test.run_att_all --real-system-test    # also the real-flowsheet smoke test
```

It stops at the first failing step and names it, and writes
`att_outputs/validation/run_summary.md`. QC rows that could not be evaluated
are reported as NOT CHECKED, never as PASS. Single parts:

| Command (`python -m biorefineries.sabre.test.<runner>`) | Output (`att_outputs/…`) |
|---|---|
| `run_att_experiment` | `experimental/` |
| `run_att_1kgph_audit` | `baseline_1kg/` |
| `run_att_inventory` | `full_scale/mass_energy/` |
| `run_att_tea` | `full_scale/tea/` |
| `run_att_lca` | `full_scale/lca/` |
| `run_att_consolidated` | `full_scale/summary/` |
| `run_att_final` | `comparison/` (C-sheet CSVs to `full_scale/summary/`) |
| `run_att_gas_scenarios` | `scenarios/gas_yield/` |
| `run_att_documentation` | `documentation/` |
| `run_att_heat_integration --hen --json-out <file>` | heat-recovery screening (console/JSON) |
| `run_att_diagram [--format png]` | `documentation/diagrams/` |

Every runner accepts `--out`. Results are written below `att_outputs/` at the
repository root (or `ATT_OUTPUTS_DIR`), never into `data/`. `att_outputs/` is
git-ignored: regenerate results instead of committing them.

Unit tests: `python -m unittest discover -s biorefineries/sabre/test -t . -p "test_att*.py"`
(set `ATT_RUN_REAL_SYSTEM_TEST=1` for the real-flowsheet smoke test).

## Results layout

```
att_outputs/
├── experimental/            measured gas yields, conditions, conversions (A1-A3), lab screening LCA (B1)
├── baseline_1kg/            1 kg dry/h mass and energy audit
├── full_scale/
│   ├── mass_energy/         streams, mass/element/water/Na-Ca balances, unit energy, utilities, LCI
│   ├── tea/                 MSP, CAPEX/OPEX, CaCO3/lime/P1/off-gas cases, sensitivities
│   ├── lca/                 GWP100 summary, contributions, scenarios, data gaps
│   └── summary/             consolidated process/TEA/GWP results and final sheets C1-C14
├── comparison/              ATT_Final_Results.xlsx (all sheets A-D) and D1-D7 lab vs plant, gas-yield scenarios
├── scenarios/gas_yield/     Gas-C (baseline) / Gas-Cprime / Gas-A detailed TEA and LCA
├── scenarios/heat_integration/  heat-recovery screening and HEN designs (JSON)
├── documentation/           master model documentation workbook; diagrams/
└── validation/              run summary, unit-test and step logs
```

Experimental (laboratory) results and full-scale model results are kept in
separate folders; they meet only in `comparison/`.

## Code structure

```
biorefineries/sabre/
├── units/_att.py                  ATT units: ATTReactor (U2), CausticizationReactor (C1),
│                                  NaOHEvaporator (EC1), NaOHMakeupMixer (M2), ATTHeatRecovery (HXR)
├── systems/_att_system.py         create_att_system(): P1-D0-M1-U2-U3HX-U3C-U3D-U3P-U3K / RC1-D1-F1-C1-F2-SP1-EC1-M2
├── analyses/att/                  analyses (see analyses/att/__init__.py)
│   ├── mass_energy.py  thermodynamics.py  heat_integration.py   process-level helpers
│   ├── experiment.py                                              laboratory data only
│   ├── inventory.py  tea.py  lca.py  scenarios.py                 full-scale analyses
│   ├── reporting.py  final.py                                     consolidated results, documentation, comparison
│   ├── validation.py                                              read-only audits (1 kg/h, Na ledger)
│   └── paths.py                                                   output locations
├── data/                          inputs only (see below)
├── test/                          test_att_*.py (unit tests), run_att_*.py (runners), run_att_all.py
├── _chemicals.py  _naoh_properties.py  _tea.py  utils.py          shared SaBRe modules
```

## Data sources

| File | Content | Source |
|---|---|---|
| `data/att_experiment.yaml` | cell-referenced transcription of the experimental data and the collaborators' assumptions | UCLA collaborators (unpublished), "ATT Inputs and Assumptions_261005.xlsx" |
| `data/att.yaml` | process specification, U2 baseline yields (copy of the Ni-CatATT measurements), unit settings, heat recovery | user-confirmed design basis, literature, engineering assumptions (each entry states its basis) |
| `data/att_tea.yaml`, `data/tea.yaml` | prices, capital items, financial assumptions | literature and SaBRe database |
| `data/att_lca.yaml` | GWP100 characterization factors | collaborators, GREET 2022, NETL, literature |
| `data/feedstock.yaml`, `data/preprocessing.yaml` | Sargassum composition, scale, press | SaBRe database |

## Model boundary and main assumptions

- Laboratory experiment (UCLA, Ni-CatATT): 0.5 g daf Sargassum, 1 g NaOH,
  500 °C, 1 h, N₂ carrier and 3.6 g steam; measured H₂, CH₄, CO, CO₂ (mmol/g daf).
  N₂ and the catalyst are laboratory conditions, not plant feeds.
- Plant: SaBRe reference scale, 15,000 wet t/d (1,990.5 dry t/d), 330 d/yr.
  P1 screw press and D0 dryer to 50 wt % moisture; U2 at 773.15 K with
  2 kg NaOH/kg daf; gas cooling, drying, PSA (90 % H₂ recovery) and
  compression to 20 bar; residue dissolution, causticization with Ca(OH)₂
  (85 %, 1.1 equivalents, 90 °C), 5 % whole-liquor purge, evaporation to
  50 wt % NaOH and recycle.
- U2 baseline gas closure `uniform_redox_scaling`: all four measured gas
  yields × s (s = 0.5998), preserving the measured ratios and closing C, H, O
  with char and water. Model yields are engineering predictions; the measured
  values are never modified. Gas-Cprime and Gas-A are alternative closures.
- TEA: preliminary; equipment at CEPCI 567.5 (2017), 2024-2025 prices; no
  CaCO₃, CH₄ or off-gas revenue in the reference case.
- LCA: GWP100 cradle-to-gate excluding Sargassum collection/transport; no
  allocation or credits; the final fate of the PSA off-gas (mainly CH₄) is
  unresolved and not included.
- Main unvalidated items are listed in `comparison/ATT_Final_Results.xlsx`
  sheet C14 and in the documentation sheets 23-24.

## Credits

SaBRe framework: Azhar Razin and Yalin Li (UIUC open-source license, see the
module headers). Laboratory data: UCLA collaborators (unpublished; permission
required, see above).
