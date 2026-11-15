# ATT S1/S2: techno-economic analysis, basis and assumptions

This document records what the TEA assumes and how it is set up. It contains no results. The numbers (MSP, FCI, operating
cost, breakdowns, sensitivities) come from the model and are in the generated report and tables
(see "Where the results are" at the end).

**Baseline assumptions.**
- The waste lime is the carbide lime of an acetylene plant (a paste with CaCO3 and inert mineral impurities), free.
- The seaweed ash of the presscake is split into an insoluble part (Ca, Mg and trace minerals, which stay in the char) and a
  soluble part (all K and Na, modeled as KCl and NaCl). The soluble salts are removed from the NaOH recycle by a **salt
  crystallizer** (XL1) and disposed of.
- The insoluble char is set to 0.15 g per g of dry feed (RS1). The rest of the lumped U2 residue leaves as
  `att_residue_untracked` with no credit and no cost.
- Both CaCO3 cakes (F2 and F3) are **dried** to 1 wt % moisture (steam-heated drum dryers D2 and D3; the target is an
  assumption) and **sold** at 100 USD/t of CaCO3 (an assumption with no buyer); the non-CaCO3 mass is disposed.
- The F2 cake and the F1 char cake are washed (1 kg water per kg of dry cake) with the condensate the dissolver does not
  need. The F2 wash liquor is recycled to the dissolver and the F1 wash liquor to the carbonate solution of C1.
- **REE recovery is on by default** (`ree_recovery=False` turns it off): the washed char cake is leached with HCl, the rare
  earths are precipitated as oxalate and roasted, and the product is sold on its REO content (35 USD/kg REO, an assumption).
  The leached char is the residue product and has a **net price of 0** (assumed to be taken as a sorbent, no buyer).

S2 is evaluated for 7,920 h/yr underway. MSP is the minimum H2 selling price in USD per kg of contained H2 (NPV = 0 at
a 10 % IRR). The carbon accounting paired with it is described in `ATT_S1_S2_LCA.md`.

## 1. Production and financial basis

| Item | Value | Class |
|---|---|---|
| H2 delivery | H2-rich gas at 2 MPa, no PSA. MSP is per kg of contained H2; CH4 in the product earns no credit | Model / [ASSUMPTION] |
| Operating time | 7,920 h/yr | [ASSUMPTION] |
| Financial method | ATTTEA DCF: IRR 10 %, 2026–2046, MACRS-7, 21 % income tax, 40/60 construction, 60 % debt at 8 % over 10 yr, working capital 5 % of FCI, 3-month startup | Inherited SaBRe/BioSTEAM |
| Capital convention | FCI = installed equipment cost (no separate indirect costs); CEPCI 596.2 (2020 USD) | Inherited SaBRe; ATT cost year |
| Fixed operating cost | 4 % of FCI per yr (labor, maintenance, overhead) | Inherited SaBRe |
| Prices | NaOH 0.405 USD/kg; waste Ca(OH)2 0 (fresh lime 0.28 USD/kg, not used); H2SO4 0.0948 USD/kg; process water 0.000441 USD/kg; solid disposal 0.04 USD/kg wet; wastewater 0.004 USD/kg; natural gas 4.36 USD/GJ (LHV); LP steam 0.2378 USD/kmol; electricity 0.0782 USD/kWh | `tea.yaml`, BioSTEAM defaults |
| REE chemicals and product | HCl (31 wt %) 0.20 USD/kg; oxalic acid 0.60 USD/kg; REO 35 USD/kg of contained REO (range 2–151) | [ASSUMPTION] `tea.yaml` |
| CaCO3 sales | 100 USD/t of CaCO3 component, F2 and F3 cakes (unverified) | [ASSUMPTION] |
| CaCO3 drying | Cakes dried from 25 to 1 wt % moisture; no grinding, purification or handling cost | [ASSUMPTION] |
| ATT residue | Net price 0 (`prices.att_char`): the leached char is assumed to be taken as a sorbent | [ASSUMPTION] |
| Salt cake | Disposed at the solid-waste price (0.04 USD/kg wet) | [ASSUMPTION] |
| Feedstock | 0 USD/t (collection and transport outside the boundary) | [ASSUMPTION] |

## 2. Cost structure

The TEA reports, per scenario: installed cost by equipment and by area, FCI and total capital, annual operating cost by
group (LP steam, natural gas, NaOH makeup, electricity, fixed cost, disposal of the CaCO3 cakes and the salt cake, H2SO4
for the purge neutralization, wastewater, cooling water, REE reagents), the REE and CaCO3 sales, and the MSP broken down
into utilities, capital-related cost (capital, debt service and tax), waste treatment, materials, fixed cost and the two
revenues. The groups are defined in `analyses/breakdown.py`.

## 3. F2 and F1 washing (S1)

Both washes, the cake dryers, the ash split, the char split and the salt crystallizer are part of the flowsheet (the
switches that turned them off were removed). The washes recover sodium, so the fresh NaOH is only a makeup of the gross dose.

| Item | Value |
|---|---|
| Wash ratio | 1 kg water per kg of dry cake, both washes; one ideal mixed stage (0.25 h) and refiltration at the cake moisture |
| Wash water | Condensate left after the dissolver (and, for F1, after the F2 wash); fresh water only as a top-up |
| Wash liquors | F2 to the dissolver D1; F1 joined with the F1 filtrate and sent to C1 |
| F2 equipment | W2 MixTank; F2R rotary vacuum filter |
| F1 equipment | W1 MixTank; F1R pressure filter |

**Notes.**
- The F1 wash adds equipment (W1 + F1R), and its wash water is evaporated again in EC1.
- A net price of 0 for the residue is an **assumption** (`prices.att_char`). At the disposal fee (0.04 USD/kg wet) the wet
  char cake would carry a disposal cost; there is no buyer or specification.

## 4. CaCO3 cakes and the ATT residue

The CaCO3 of the cakes comes from the causticization, the CO2 scrubber and the CaCO3 (4 % of the dry lime) of the
carbide lime. The F2 cake and the F3 scrubber cake are sold on their CaCO3 content.

**Drying (D2, D3).** The filter cakes (25 wt % moisture) are dried to 1 wt % in two steam-heated drum dryers of the
D0 type. The target moisture is an assumption; there is no filler specification, grinding or purification. The disposal
charge (0.04 USD/kg wet) is applied to all non-CaCO3 mass of the sold cakes, including their water, so drying also reduces
the disposal charge.

**Accounting interpretation.** No unit separates CaCO3 from the cake. The revenue/disposal split is a **net cake
price**: the CaCO3 content × 100 USD/t, minus 0.04 USD/kg × the non-CaCO3 mass (moisture, unreacted Ca(OH)2, inert
minerals, sodium and the K and Na chlorides). It is booked once, on the stream price. There is no product specification,
buyer or verified price: a cake with unreacted Ca(OH)2 and inert minerals is **not** high-purity PCC, and the lab ≈ 97 %
purity was measured on a different, clean system. The sales case is therefore an upper bound, and the no-sales value
should be quoted beside it.

**CaCO3 price cases (S1).** No sales (both cakes disposed); 0 USD/t (taken away, the non-CaCO3 mass disposed); 100 USD/t
(baseline); 315 USD/t (approximate public industrial reference, unverified for this product). The MSP changes linearly with
the CaCO3 price.

**ATT residue (leached char).** The cake is the wet leached char (30 wt % moisture) with the ash minerals, the organic
char, CharN and CharS, and the REO that was not recovered. The baseline assumes the residue has a net price of 0, for
example as a sorbent. Setting `tea.yaml prices.att_char` to -0.04 (the disposal fee) gives the other case.

**Salt cake.** The crystallizer XL1 removes 99 % of the NaCl and KCl from the EC1 concentrate; the salt cake is disposed at
0.04 USD/kg. The chloride contents of the seaweed are not measured.

## 5. REE recovery

The seaweed is assumed to carry 737 ppm TREE already (the Sargassum of the lab, soaked in acid mine drainage). The
capture section (soak tank, screen, press) is **not modeled or costed**.

| Item | Value |
|---|---|
| REE basis | Wastewater 1.4 mg TREE/L at 2.5 g dry seaweed/L; REO/TREE factor 1.169; product REO = 60 % of the REE of the initial wastewater, capped by the oxalate stoichiometry (85 % of the REE of the char) |
| Reagents | 31 wt % HCl (0.2 USD/kg) and oxalic acid (0.6 USD/kg), at the lab doses per g of char |
| Product | Roasted oxalate precipitate with mineral filler from the char ash, sold on its REO content |
| Equipment | LC1 (leach and oxalate tanks, filters); RO1 (roaster, only the precipitate) |
| REO price | 35 USD/kg of contained REO in the baseline; swept from 2 to 151 USD/kg |

Whether the REE recovery lowers or raises the MSP depends on the REO price, the 60 % recovery, the grade and a buyer, all
of which are assumptions; the break-even REO price is part of the results. A 1.3 wt % REO solid would not fetch a high price
without a buyer and a grade that suits a refiner.

**REO grade sensitivity (the collaborators' 98 wt % case).** If the seaweed is soaked in a concentrated REE solution, the
product can reach 98 wt % REO (their 0.01 M Nd run gave 98.8 % Nd2O3). The sensitivity (`analyses/ree_sensitivity.py`)
changes **only the grade**: the REO mass of the product stays (60 % of the REE of the dilute wastewater) and the mineral
filler that dilutes it shrinks; the grades swept are 1.31 (baseline), 5, 20, 50 and 98 wt %. A larger REE loading of the
seaweed (more REO per kg of char) is **not** modeled. Whether a 98 % product would fetch more than the 35 USD/kg of the
mixed concentrate is an assumption, which is why the price is swept.

## 6. Scenario definitions

| Case | Definition |
|---|---|
| S1 | The baseline above, on land |
| S2 floating, no WHR | The S1 process on an existing vessel, without waste heat recovery |
| S2 floating, all WHR | As above with the marine waste heat recovery (exhaust, scavenge air; the jacket-water loop is included in the screening) |

Each case is also evaluated without the REE recovery (`ree_recovery=False`). A second residue case disposes of the leached
char at 0.04 USD/kg wet instead of the net price of 0.

**S2 cost structure assumptions** (`data/marine_tea.yaml`, `data/marine_whr.yaml`):
- Process CAPEX = 1.25 × the S1 FCI (the floating-vessel multiplier).
- The WHR equipment is added after the multiplier: economizer, steam drum and interface (placeholder), charge-air cooler,
  pumps, and a piping and controls allowance. A jacket-water loop whose sinks are not cold enough does not buy its
  exchanger and pump.
- Labor = 2 × the S1 labor; the S1 labor is taken as 50 % of the S1 fixed operating cost.
- The WHR cuts purchased energy (steam and natural gas); engine load and operating hours scale the recovered heat.

**S2 floating-factor sensitivity ranges:** CAPEX multiplier 1.10 / 1.40; labor multiplier 1 / 2; WHR CAPEX × 0.5 / × 2;
WHR CAPEX at the IMO lower bound for power WHRS (5.2 MUSD); engine load 0.5 / 1.0.

## 7. How to read the results

- The CaCO3 revenue is an unverified assumption and a large item of the MSP; quote the no-sales value beside the sales
  case unless a buyer and specification for the cake are confirmed.
- The net price of 0 for the leached char is an assumption; the other case (disposal at 0.04 USD/kg wet) shows its effect.
- The REE recovery result depends on the REO price, the 60 % recovery, the 1.31 wt % grade and the buyer; report it
  with the break-even price, not as a gain or a loss alone.
- The S2 results are at 7,920 h/yr underway; fewer hours spread the fixed costs over less H2.

Boundary reminders:
- No vessel acquisition, harvesting, collection or transport cost.
- No CH4 credit.
- The REE capture from the acid mine drainage is not modeled or costed.
- The dissolved metals of the HCl leach (Fe, Al, Mn, Ca, Mg and others) are not tracked through the recycle.
- Prices are not escalated across years.

## Where the results are

Generate them with the project interpreter; all go to the git-ignored `results/` folder:
- `python -m biorefineries.ATT.analyses.comprehensive_report`: the HTML report and its CSV tables for S1, S2 and S3
  (`dcf_msp_components.csv`, `annual_cost_breakdown.csv`, `ree_incremental_economics.csv`, `scenario_comparison.csv`);
- `python -m biorefineries.ATT.analyses.run tea`: the TEA workbooks of the S1 case (see `analyses/run.py` for the other steps);
- `analyses/ree_sensitivity.py` and `analyses/u2_cost_sensitivity.py`: the REO price and grade, and the U2 cost sensitivities.
