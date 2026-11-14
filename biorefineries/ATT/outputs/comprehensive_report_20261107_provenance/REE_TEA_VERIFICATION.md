# REE On/Off TEA verification

REE On has a higher hydrogen MSP in all three scenarios under the current assumptions. Independent bracketed roots of discounted cash flow reproduce the current prices. No economic calculation or accounting correction was required.

All six cases produce 372.924630359 kg H2/h, 2953563.072444 kg H2/year, at 7920 h/year. The full product-gas mass is not used as hydrogen production.

| Scenario | REE | FCI (USD) | Gross OPEX (USD/year) | Coproduct revenue (USD/year) | Net OPEX (USD/year) | Screening capital (USD/year) | Net treatment (USD/year) | DCF MSP (USD/kg H2) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| S1 | Off | 13,463,468.11 | 9,013,204.64 | 5,316,903.82 | 3,696,300.82 | 1,581,413.91 | 5,277,714.73 | 1.84222142 |
| S2 | Off | 17,719,109.57 | 9,054,951.50 | 5,316,903.82 | 3,738,047.68 | 2,081,279.96 | 5,819,327.64 | 2.04398179 |
| S3 | Off | 19,731,660.51 | 7,144,182.44 | 5,316,903.82 | 1,827,278.61 | 2,317,673.44 | 4,144,952.05 | 1.48445443 |
| S1 | On | 14,751,757.71 | 9,428,709.31 | 5,863,967.55 | 3,564,741.76 | 1,732,735.92 | 5,297,477.68 | 1.85420646 |
| S2 | On | 19,329,471.56 | 9,502,663.41 | 5,863,967.55 | 3,638,695.86 | 2,270,432.48 | 5,909,128.33 | 2.08109738 |
| S3 | On | 21,019,950.10 | 7,559,687.10 | 5,863,967.55 | 1,695,719.55 | 2,468,995.45 | 4,164,715.00 | 1.49643947 |

All increments below are REE On minus REE Off. Reagent and electricity subrows are already included in their parent cost groups; do not add them again.

| Increment | S1 | S2 | S3 |
|---|---:|---:|---:|
| FCI, USD | +1,288,289.59 | +1,610,361.99 | +1,288,289.59 |
| REE-specific installed equipment including auxiliaries, USD | +1,276,923.72 | +1,596,154.65 | +1,276,923.72 |
| Materials, USD/year | +258,596.50 | +258,596.50 | +258,596.50 |
|   HCl solution subset, USD/year | +192,516.17 | +192,516.17 | +192,516.17 |
|   Oxalic acid subset, USD/year | +13,633.63 | +13,633.63 | +13,633.63 |
|   NaOH subset, USD/year | +52,446.71 | +52,446.71 | +52,446.71 |
| Utilities and energy, USD/year | +81,733.23 | +81,733.23 | +81,733.23 |
|   Electricity subset, USD/year | +72,901.07 | +72,901.07 | +72,901.07 |
| Waste treatment/disposal, USD/year | +23,643.35 | +23,643.35 | +23,643.35 |
| Fixed operating costs, USD/year | +51,531.58 | +83,738.82 | +51,531.58 |
| Gross OPEX, USD/year | +415,504.66 | +447,711.90 | +415,504.66 |
| REO revenue, USD/year | +547,574.65 | +547,574.65 | +547,574.65 |
| CaCO3 revenue, USD/year | -510.92 | -510.92 | -510.92 |
| Total coproduct revenue, USD/year | +547,063.73 | +547,063.73 | +547,063.73 |
| Net OPEX, USD/year | -131,559.06 | -99,351.82 | -131,559.06 |
| Screening annual capital charge, USD/year | +151,322.01 | +189,152.52 | +151,322.01 |
| Net treatment cost, USD/year | +19,762.95 | +89,800.69 | +19,762.95 |
| Working capital, USD | +64,414.48 | +80,518.10 | +64,414.48 |
| Screening cost change, USD/kg H2 | +0.00669122 | +0.03040419 | +0.00669122 |
| DCF MSP change, USD/kg H2 | +0.01198504 | +0.03711559 | +0.01198504 |

S1 screening arithmetic: 415504.66 - 547063.73 + 151322.01 = 19762.95 USD/year, or 0.00669122 USD/kg H2. This is not the DCF MSP increment (0.01198504 USD/kg H2).

REO revenue is 547574.65 USD/year. Removing only REO revenue, leaving physical operations and all costs intact, raises S1 REE-On MSP from 1.85420646 to 2.03960104 USD/kg H2. The effect is revenue / annual hydrogen = 0.18539460 USD/kg H2. The same credit is verified independently for S2 and S3. CaCO3 credit is checked the same way while retaining the non-saleable cake disposal charge.

The additional REE equipment is LC1 and RO1 including their owned auxiliaries. Other process equipment changes explain the remainder of the FCI increment; the unit-by-unit installed costs and explicit scenario adjustments are exported in ree_equipment_costs.csv. S2 applies its existing 1.25 floating process multiplier and labor treatment; WHR is added after that multiplier. S3 uses the same industrial WHR increment in both REE cases.

The six horizontal cost stacks are annualized screening costs in million USD/year: materials + utilities/energy + waste treatment/disposal + fixed OPEX + FCI × CRF, with coproduct revenue shown separately as a negative credit. Gross OPEX is before coproduct credits but after actual WHR utility savings. Net OPEX = gross OPEX - coproduct revenue; net treatment cost = net OPEX + screening capital. H2 sales are excluded from screening costs. The three increment stacks use the same basis for On minus Off. DCF MSP is displayed separately.

DCF assumptions remain 10% IRR, 20 operating years (2026–2046), MACRS7 depreciation, 21% income tax, construction spending 40%/60%, 5% working capital recovered at project end, 60% debt at 8% over 10 years, and a 3-month startup with FOC 100%, VOC 50% and sales 50%. The startup FOC profile differs from sales/VOC. Depreciation affects taxable earnings rather than being added to OPEX. The DCF includes timed construction, debt payments and taxes; the screening CRF does not enter the DCF as another cost. No additional replacement capital is triggered by REE On in these cases.

The following audit uses the actual discounted cash-flow columns and operating/sales startup profiles, normalized by discounted hydrogen. It is an additive DCF check to solver tolerance, not an allocation of a fitted capital residual. Small residual NPVs are below one dollar.

| Discounted MSP increment, USD/kg H2 | S1 | S2 | S3 |
|---|---:|---:|---:|
| materials | +0.08755408 | +0.08755408 | +0.08755408 |
| utilities | +0.02767276 | +0.02767276 | +0.02767276 |
| waste | +0.00800503 | +0.00800503 | +0.00800503 |
| coproduct_revenue | -0.18522162 | -0.18522162 | -0.18522162 |
| fixed | +0.01768329 | +0.02873535 | +0.01768329 |
| capital | +0.05400389 | +0.06750486 | +0.05400389 |
| working_capital | +0.00221041 | +0.00276301 | +0.00221041 |
| financing | -0.00127984 | -0.00159980 | -0.00127984 |
| tax | +0.00135704 | +0.00170192 | +0.00135704 |

Accounting checks: installed unit costs plus explicit adjustments equal FCI; HCl and oxalic ledger costs equal their feed costs; CaCO3 and REO sales are credited once; independent DCF roots match the solved MSP. In BioSTEAM, negative-price waste products and net cake prices affect sales. The report separates their disposal and gross revenue portions for readability; raw TEA.AOC therefore differs from report gross OPEX without creating a second charge.

Code references:
- biorefineries/ATT/analyses/tea.py:58 — `class ATTTEA`
- biorefineries/ATT/analyses/tea.py:137 — `def _apply_prices`
- biorefineries/ATT/analyses/tea.py:207 — `def evaluate_att_tea`
- biorefineries/ATT/analyses/tea.py:293 — `def _opex_table`
- biorefineries/ATT/analyses/marine_tea.py:72 — `def evaluate_case`
- biorefineries/ATT/analyses/att_s3_industrial.py:12 — `def run(`
- biorefineries/ATT/analyses/ree_tea_verification.py:29 — `def _root`
- biorefineries/ATT/analyses/ree_tea_verification.py:44 — `def _dcf_components`
