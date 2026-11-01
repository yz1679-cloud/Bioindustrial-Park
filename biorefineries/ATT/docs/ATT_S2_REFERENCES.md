# ATT Scenario 2: references

Source IDs used in `data/marine_whr.yaml`, `data/marine_tea.yaml` and `ATT_S2_DESIGN_BASIS.md`.

The "Checked" column records what was actually done in this work (2026-11-01):
- **Fetched**: the URL was retrieved and the cited content confirmed.
- **Resolved only**: the URL redirects correctly, but the content was not read.
- **Not retrieved**: the server refused the request; the citation is as supplied by the user.

No value is claimed from a source that was not read.

## Vessel

| ID | Source | URL | Checked | Used for | Limitations |
|---|---|---|---|---|---|
| R-V1 | Spar Shipping AS, "Spar Pyxis" fleet page | https://sparshipping.com/fleet/spar-pyxis/ | Fetched | Ultramax; built 2015; 199.9 m × 32.26 m; DWT 63 266; main engine MAN B&W 5S60ME-C8.2 | No engine power, boiler or WHR data on the page |
| R-V2 | Scheepvaartwest, "Spar Pyxis – IMO 9701932" | https://www.scheepvaartwest.be/CMS/index.php/general-cargo/8244-spar-pyxis-imo-9701932 | Fetched | IMO 9701932; Jiangsu Hantong 2015; HHM-MAN B&W 5S60ME-C8, **8 050 kW / 12 880 bhp at 89 rpm**; 3 × 850 kW Daihatsu generator sets; **one Kangrim composite auxiliary boiler**; summer DWT 63 800 t | Secondary ship-spotting database; no part-load engine data; the composite boiler shows the ship already uses exhaust heat |

## Marine waste heat: research

| ID | Source | URL | Checked | Used for | Limitations |
|---|---|---|---|---|---|
| R-Z2020 | Zhu, S., Zhang, K., Deng, K. (2020). A review of waste heat recovery from the marine engine with highly efficient bottoming power cycles. *Renewable and Sustainable Energy Reviews* 120, 109611. | https://doi.org/10.1016/j.rser.2019.109611 | Resolved only (→ Elsevier PII S1364032119308196, matching the local file `Downloads/1-s2.0-S1364032119308196-main.pdf`). The local PDF could not be read here (no PDF tools) | Main waste-heat sources, temperature grades, load dependence, corrosion constraints (qualitative). The engine fractions 25.5 / 16.5 / 5.2 % and the 49.3 % shaft efficiency come from the earlier pre-FEED documentation, which attributes them to this review | **Fractions not re-verified against the PDF.** Generic engine data, not SPAR PYXIS |
| R-Z2020E | Zhu et al. (2020). Energy and exergy analysis of the combined cycle power plant recovering waste heat from the marine two-stroke engine under design and off-design conditions. *Energy*. | https://doi.org/10.1016/j.energy.2020.118558 | Not retrieved | Qualitative: pinch temperature and off-design behavior govern economizer duty | No numbers taken |
| R-MDPI | Energy Saving Analysis of a Marine Main Engine during the Whole Voyage Utilizing an Organic Rankine Cycle System to Recover Waste Heat. *J. Mar. Sci. Eng.* 11(1), 103 (2023). | https://www.mdpi.com/2077-1312/11/1/103 | Not retrieved (HTTP 403) | Qualitative: voyage load profile and exhaust conditions set the available heat | No numbers taken; ORC not adopted |

## Manufacturers and agencies

| ID | Source | URL | Checked | Used for | Limitations |
|---|---|---|---|---|---|
| R-AL1 | Alfa Laval, Aalborg XW exhaust gas economizer | https://www.alfalaval.us/products/heat-transfer/boilers/exhaust-gas-economizer/aalborg-xw/ | Fetched | Finned ("double-gilled") water-tube, forced circulation; 0.2–17.0 t steam (page gives no "/h"); design pressures 18 or 24 bar(g); steam or compressed-air sootblowers; optional superheater and preheater | Product range only; says nothing about the steam available from SPAR PYXIS; no bypass stated |
| R-AL2 | Alfa Laval, Heating and cooling in the engine room | https://www.alfalaval.us/industries/marine-and-transportation/marine/heating-and-cooling/heating-and-cooling-in-the-engine-room/ | Fetched | Jacket-water, charge-air and central cooling circuits; gasketed plate exchangers; **jacket-water heat already used by freshwater generators** | No temperatures given. The 70–90 °C jacket-water range is an ENG assumption from general practice, not from this page |
| R-IMO | IMO GreenVoyage2050, Waste Heat Recovery Systems | https://greenvoyage2050.imo.org/technology/waste-heat-recovery-systems/ | Fetched | Installed WHRS cost **5.2–11.5 MUSD per ship**; maintenance 10–30 kUSD/yr; fuel savings 2–6 %; about 10 MW engine as the practical lower limit; slow steaming at ~80 % load may prevent turbine use; usually not relevant for retrofits | These are power-generating WHRS (steam or power turbines, ORC), not heat-only exchangers; used only as an upper-bound cost context |
| R-LR1 | Lloyd's Register, LR-GN-061 Guidance Notes for Onboard Hydrogen Generation (28 January 2026) | https://www.lr.org/en/knowledge/lloyds-register-rules/guidance-notes/guidance-notes-for-onboard-hydrogen-generation/ | Fetched | Safety topics for design: fuel preparation rooms, ventilation and inerting, fire and explosion protection, interfaces with ship systems, risk-based studies | Not evidence of any approval of ATT on a ship |
| R-LR2 | Lloyd's Register, Rules and Regulations for the Classification of Ships (LR-RU-001, edition 1 July 2026) | https://www.lr.org/en/knowledge/lloyds-register-rules/rules-and-regulations-for-the-classification-of-ships/ | Fetched (title and edition only) | Classification framework that a real installation would need | Not reviewed in detail; no approval implied |

## Cost correlations (software)

| ID | Source | Used for |
|---|---|---|
| R-BST | BioSTEAM 2.53.11 (installed): `biosteam.units.heat_exchange.compute_floating_head_purchase_cost` (Seider et al., floating-head shell-and-tube, CE-scaled) with the BioSTEAM HX bare-module factor 3.17; `bst.Pump` cost and power | Proxy costs of the economizer, charge-air recovery cooler, jacket-water plate exchanger and U2 feed preheater; pump cost and power. The correlation is a proxy: finned economizers and plate exchangers differ |

## Project documents

| ID | Document | Status | Used for |
|---|---|---|---|
| R-UCLA | `SabRe Meeting_Gyudae_20260928.pptx` (UCLA, G. Sim, 28 Sep 2026); local copies in `Downloads/` and `Box/PhD_Yu Zhou-Li/SaBRe/slide/` | Slide text read | Motivation only: slide 12 cites R-Z2020 for ship waste heat; slide 16 states "water evaporation takes 65–77 % of energy in ATT" and about 9.5 kg CO2e/kg H2 with waste heat. **Not transferred**: different model, moisture and boundary |
| R-PREFEED | `ATT_ship_waste_heat_preFEED_model.xlsx` | **Not found locally** (Downloads, Desktop, Documents, Box searched) | Its assumptions are used only as documented by the user: 3.123 / 2.021 / 0.637 MW gross and 1.062 / 0.601 / 0.162 MW delivered at about 30 t dry/d; fractions 25.5 / 16.5 / 5.2 %; capture 40 / 35 / 30 %; delivery 85 %. Its historical U2 value is about 3 619 **kW** at 30 t dry/d (not "MW"); it is not used |
| R-ATT | ATT S1 model (this project): `data/att.yaml`, `IMPLEMENTATION_NOTES.md`, the simulated utility ledger | MODEL | Heat sinks, utility prices, TEA and LCA basis |

## User-supplied assumptions (not literature-verified)

| ID | Assumption |
|---|---|
| USER-1 | Floating labor OPEX = 2.0 × land labor OPEX |
| USER-2 | Floating CAPEX = 1.1–1.4 × land process CAPEX; central value 1.25 |
| USER-3 | ATT processing only while the ship is underway |
| USER-4 | Other onboard consumers of the ship's heat are ignored. This is an **optimistic availability boundary**: SPAR PYXIS has a composite boiler (R-V2), and jacket water typically feeds a freshwater generator (R-AL2) |
| USER-5 | Main engine at 75 % MCR underway; shaft efficiency 0.493 (generic proxy); Mode B profile of 8 h transit (75 %), 8 h collection (15 %) and 8 h anchored (0 %) |
