# SaBRe ATT: alkaline thermal treatment of *Sargassum* to hydrogen (BioSTEAM)

Process model of alkaline thermal treatment (ATT) of *Sargassum* with NaOH at
500 °C to hydrogen, with NaOH recovery by causticization, built on the SaBRe
(Sargassum Biorefinery) framework in BioSTEAM. It provides a 1 kg dry/h baseline, a full-scale plant (NLR preprint scale, 3 million wet t/yr) with material, element, Na, water and energy balances, a
preliminary TEA (H₂ minimum selling price) and a GWP100 LCA, for two cases:
the ATT-only plant (wet *Sargassum*) and the ATT-integration case (presscake
of a biostimulant plant).

> **Data availability.** The measured gas yields and the workbook values in
> `data/att.yaml` are unpublished laboratory
> data of the UCLA collaborators. They may only be redistributed or made public
> with the collaborators' permission. See [Data sources](#data-sources).

## Installation

Tested with Python 3.12, biosteam 2.53.11 and thermosteam 0.53.5. From a
clone of the repository:

```
git clone https://github.com/yz1679-cloud/Bioindustrial-Park.git
cd Bioindustrial-Park
git checkout sabre
python -m venv .venv
.venv\Scripts\activate            # Windows  (Linux/macOS: source .venv/bin/activate)
pip install -e .
```

`pip install -e .` (editable) is recommended. Optional extras for the report
tools: `openpyxl` (Excel export) and `matplotlib` and `graphviz` (process flow
diagrams; the diagrams also need the Graphviz `dot` program,
https://graphviz.org/download/, on the PATH).

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
| `run_att_1kgph_audit` | `baseline_1kg/` |
| `run_att_inventory` | `full_scale/mass_energy/` |
| `run_att_tea` | `full_scale/tea/` |
| `run_att_lca` | `full_scale/lca/` |
| `run_att_consolidated` | `full_scale/summary/` |
| `run_att_documentation` | `documentation/` |
| `run_att_diagram [--format png]` | `documentation/diagrams/` |

Key conversions against theoretical values, material usage, heat-duty waterfalls (by unit and by
physical origin), low- versus high-grade and external versus internal heat, and EROI, for both cases
(`results/tables/att_*.csv`, `results/figures/fig_att_heat_*.png`):

```
python biorefineries/sabre/analyses/att_key_metrics.py
```

Process flow diagram: `results/figures/att_sys.svg` (BioSTEAM auto-generated, `test/run_att_diagram.py`).

Cost and GWP breakdown of H2 for both cases (MSP by cost type, CAPEX by process
area, OPEX by group, GWP100 by contributor), as tables and a figure under
`results/` (like the other SaBRe systems):

```
python biorefineries/sabre/analyses/cost_gwp_breakdown_att.py
```

Every runner accepts `--out`. Results are written below `att_outputs/` at the
repository root (or `ATT_OUTPUTS_DIR`), never into `data/`. `att_outputs/` is
git-ignored: regenerate results instead of committing them.

Unit tests: `python -m unittest discover -s biorefineries/sabre/test -t . -p "test_att*.py"`
(set `ATT_RUN_REAL_SYSTEM_TEST=1` for the real-flowsheet smoke test).

## Results layout

```
att_outputs/
├── baseline_1kg/            1 kg dry/h mass and energy audit
├── full_scale/
│   ├── mass_energy/         streams, mass/element/water/Na-Ca balances, unit energy, utilities, LCI
│   ├── tea/                 MSP, CAPEX/OPEX, CaCO3/lime/P1/off-gas cases, sensitivities
│   ├── lca/                 GWP100 summary, contributions, scenarios, data gaps
│   └── summary/             consolidated process/TEA/GWP results
├── documentation/           master model documentation workbook; diagrams/
└── validation/              run summary, unit-test and step logs
```


## Code structure

```
biorefineries/sabre/
├── units/_att.py                  ATT units: ATTReactor (U2), CausticizationReactor (C1),
│                                  NaOHEvaporator (EC1), ATTDrumDryer, ATTCompressor, ATTMolecularSieve
├── systems/_att_system.py         create_att_system(): P1-D0-M1-U2-U3HX-U3C-U3D-U3K-U3P-U3V / RC1-W3-SW-D1-F1-C1-F2-SP1-EC1
├── analyses/att/                  analyses (see analyses/att/__init__.py)
│   ├── mass_energy.py  thermodynamics.py                       process-level helpers
│   ├── inventory.py  tea.py  lca.py  breakdown.py                 full-scale analyses
│   ├── reporting.py                                               consolidated results, documentation
│   ├── validation.py                                              read-only audits (1 kg/h, Na ledger)
│   └── paths.py                                                   output locations
├── data/                          inputs only (see below)
├── test/                          test_att_*.py (unit tests), run_att_*.py (runners), run_att_all.py
├── _chemicals.py  _tea.py  utils.py                               shared SaBRe modules
```

## Data sources

| File | Content | Source |
|---|---|---|
| `data/att.yaml` | process specification, U2 baseline yields, unit settings, heat recovery | collaborators' workbook "ATT Inputs and Assumptions_261005.xlsx" (unpublished), user-confirmed design basis, literature, engineering assumptions; `data_sources` records the origin of each section |
| `data/att_tea.yaml`, `data/tea.yaml` | prices, capital items, financial assumptions | literature and SaBRe database |
| `data/att_lca.yaml` | GWP100 characterization factors | collaborators, GREET 2022, NETL, literature |
| `data/feedstock.yaml`, `data/preprocessing.yaml` | Sargassum composition, scale, press | SaBRe database |

## Model boundary and main assumptions

- Laboratory experiment (UCLA, Ni-CatATT): 0.5 g daf Sargassum, 1 g NaOH,
  500 °C, 1 h, N₂ carrier and 3.6 g steam; measured H₂, CH₄, CO, CO₂ (mmol/g daf).
  N₂ and the catalyst are laboratory conditions, not plant feeds.
- Plant: NLR preprint scale, 3 million wet t/yr (9,091 wet t/d, about 1,300 dry t/d) of fresh *Sargassum* (NLR preprint composition), 330 d/yr.
  ATT-only case: P1 screw press (municipal biosolids press cost and power; the press
  liquid is the raw juice for biostimulant production, transferred at no price) and
  D0 dryer to 50 wt % moisture. Integration case: the presscake of the biostimulant
  plant is fed directly (no P1). U2 at 773.15 K with 2.995 kg NaOH/kg daf (all CO₂ captured, see below); gas cooling, drying and compression to 20 bar (no PSA in
  the baseline: the product gas is about 98.6 mol % H₂, the rest CH₄ and CO; `create_att_system(psa=True)` restores the PSA with 90 % H₂ recovery and
  a burned tail gas); residue dissolution (in the EC1 and U3C condensates, with fresh water only as makeup), causticization with Ca(OH)₂
  (85 %, 1.1 equivalents, 90 °C), 5 % whole-liquor purge, evaporation to
  50 wt % NaOH and recycle.
- U2 gas yields are specified (experimental team: H₂ 70.52, CH₄ 0.70, CO 0.31
  mmol/g daf, measured at 1 g/g NaOH, where the gas also had CO₂ 22.68); carbon not otherwise assigned
  leaves as CO₂, which the NaOH then captures; product water closes oxygen. `ATTReactor.balance_checks()` reports (i) NaOH capacity for
  the CO₂ generated and (ii) electron, mass and energy balances of the identified
  products. Unidentified reactions are not tracked.
- NaOH dose (baseline since 2026-10-17): 2.995 g NaOH per g daf Sargassum, not the laboratory 1 g/g. It is the dose
  that captures all the CO₂ generated as Na₂CO₃ (2 NaOH per CO₂, 74.9 mmol/g daf; at 1 g/g only a third is captured),
  so the gas CO₂ yield is 0. H₂, CH₄ and CO yields stay at the team's slate, which was measured at 1 g/g; whether it
  holds at the higher dose is an assumption to confirm. Without CO₂ in the gas no PSA is needed for a fuel-grade product.
- MSP and GWP are per kg of H₂ in the product gas; the CH₄ and CO in it are not credited.
- TEA: preliminary; equipment in 2020 USD (CEPCI 596.2), 2024-2025 prices; no
  CaCO₃ or CH₄ revenue in the reference case. With `psa=True` the tail gas (mainly CH₄ and
  unrecovered H₂) is assumed burned in the U2 burner and displaces natural gas
  up to U2's fuel demand; no burner is modeled.
- Lime recycle (default, `create_att_system(lime_recycle=True)`): the F2 CaCO3 cake is calcined in a lime
  kiln (K1, natural gas), 5 % is purged (LP), the rest is slaked (S1) and returned to C1 with fresh Ca(OH)2 makeup.
  Sodium in the cake rides with the lime and returns to C1. The kiln is costed PRELIMINARY (drum-dryer shell
  correlation x an assumed refractory factor + furnace) and fuelled to about 7.3 GJ per t CaO; its natural gas is
  counted under "Natural gas U2" in the LCA. `lime_recycle=False` buys all the Ca(OH)2 and disposes of the cake.
- Heat recovery: BioSTEAM's `HeatExchangerNetwork` (HXN, 10 K minimum approach) is in the
  system by default (`create_att_system(heat_exchanger_network=True)`). Heating and cooling
  duties of D0, C1, EC1 (evaporator and condenser) and U3HX are matched; U2's fired duty, the
  solids cooler RC1, the U3K intercoolers and the U3D regeneration are not. Where BioSTEAM
  carries a duty without an exchanger (C1, U3K, U3D) an auxiliary exchanger is costed.
- LCA: GWP100 cradle-to-gate excluding Sargassum collection/transport; no
  allocation or product credits; biogenic CO₂ not counted. (With `psa=True` the tail gas is burned in the U2 burner:
  natural gas offset, no CH₄ emission.) The biogenic carbon stored in landfilled solids (CaCO₃ cake, ash/char cake, lime purge) is credited in the net as a negative emission (permanence assumed; carbon released as CO₂ anywhere, including the lime kiln, is not). The avoided landfill CH₄ of the feed is reported as an alternative credit (same carbon, different fate), not in the net and not additive with the stored-carbon credit.
- Burning part of the dried U2 gas as plant fuel instead of selling it as H2 was tested and removed:
  it is not helpful. At the earlier baseline (1 g/g NaOH, with PSA) and recycled lime (ATT-integration), splitting 10 % raises the MSP from 2.80 to
  3.01 USD/kg H2 and the GWP from 17.9 to 18.9 kg CO2e/kg H2 (20 %: 3.27 and 20.2; 50 %: 4.65 and
  27.1). The smaller PSA and compressor save only about 4 MUSD of FCI per 10 %, far less than the H2
  revenue lost, and the burned gas displaces natural gas that U2 would need anyway.
- Main unvalidated items are listed in the documentation sheets 23-24.

## Credits

ATT model: Yu Zhou and Yalin Li (UIUC open-source license, see the
module headers). Laboratory data: UCLA collaborators (unpublished; permission
required, see above).

## Planned work

- **Fired heater for U2 (replaces the tail-gas offset).** Model U2's furnace as
  a fired-heater facility, following `FiredHeater` in the MCCA whey-olefins
  model (ASPECT concept paper, `whey_olefins_prelim.py`): connect `u3_tail_gas`
  as a stream burned with air plus a natural-gas makeup stream and a flue-gas
  outlet, and move the TEA/LCA natural gas of U2 from per-kJ agent factors to
  streams. Cost with a Seider et al. (2017) fired-heater correlation from the
  VIFF toolkit: "Heater, pyrolysis" (0.737 Q^0.81, Q in Btu/hr, 10-500
  MMBtu/hr, bare-module factor 2.19; 2013 basis), or the Sinnott box furnace
  (30-120 MW) as an alternative. U2's duty at the SaBRe scale is about 750
  MMBtu/hr (220 MW), so use parallel units (about USD 13 million purchase for
  two 375 MMBtu/hr units, by a rough estimate); the 1 kg/h baseline is below
  the correlation minimum. BioSTEAM has only steam boilers (`bst.Boiler`,
  `bst.BoilerTurbogenerator`, as used by the 3HP system), which would supply
  the LP steam of EC1, D0, C1 and U3D, not U2's 500 °C furnace.
- **Crystal separation after EC1.** Na₂CO₃ crystals currently pass through M1
  and U2 (relabeled as liquid in M1); a solid-liquid separator sending them to
  D1 would save about 0.4 % of plant heat.
