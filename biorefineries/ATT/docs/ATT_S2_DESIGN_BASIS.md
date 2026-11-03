# ATT Scenario 2: shipboard ATT with marine waste heat recovery (design basis)

This is a **preliminary engineering and TEA screening basis, not a marine installation design.** Nothing here
implies that SPAR PYXIS, or any ship, can host ATT, or that class or OEM approval exists. Sources are listed in
`ATT_S2_REFERENCES.md`. Data classes are as in `data/marine_whr.yaml`: PUB-MFR, PUB-RES, MODEL, DERIVED, USER,
ENG (preliminary engineering estimate) and MISSING.

## 1. Scope and boundary

- **Process.** The process is ATT Scenario 1, **unchanged**: the same flowsheet (including the F2 and F1 cake washing with recycled wash liquor, the drying of the two CaCO3 cakes in D2 and D3, and the carbide-lime paste),
  chemistry, lumped residue, balances, NaOH 1 kg/kg dry, C1 0.88, presscake feed with D0, 5029.17 kg dry/h, HXN, the
  CaCO3 sales and the washed-residue assumption. S2 is `scenarios.ATT_S2` (key `att_s2`, `marine: true`).
- **WHR** is an **accounting layer** (`analyses/marine_whr.py`). Ship-side equipment is sized and costed, but
  it is not a BioSTEAM unit in the flowsheet, because the engine streams lie outside the ATT plant boundary. The
  ATT material balances are untouched.
- **Floating TEA** is `analyses/marine_tea.py`. It feeds `evaluate_att_tea` through neutral-by-default hooks:
  operating hours, extra capital after the FCI factor, extra VOC, and FOC terms. The S1 TEA is unchanged by
  construction; `test_att_s2.test_s1_reference_unchanged` checks this.
- **LCA** is incremental (`analyses/marine_lca.py`): avoided purchased heat plus pump electricity, applied to
  the S1 LCA. It is not a ship lifecycle assessment.
- **Driver:** `analyses/att_s2_marine.py`. Outputs go to `results/tables/att_s2_*.csv`. Tests:
  `test/test_att_s2.py`.

## 2. Reference vessel (R-V1, R-V2)

- SPAR PYXIS, Ultramax bulk carrier, IMO 9701932, 199.9 m × 32.26 m, about 63.3–63.8 kt DWT.
- Main engine MAN B&W 5S60ME-C8(.2), **8 050 kW** at 89 rpm.
- It is a conceptual engine-scale reference only. Deck space, holds, stability, propulsion and safety
  arrangement are not verified.
- The ship already has a composite exhaust boiler, and jacket water usually feeds a freshwater generator (R-AL2).
  These existing users are **ignored (USER-4)**, so the available heat is an **optimistic** boundary.

## 3. Engine heat sources at 75 % MCR (Mode A)

| Item | Value | Class / source |
|---|---|---|
| Shaft power | 8050 × 0.75 = 6 037.5 kW | USER-5, R-V2 |
| Fuel input | 6 037.5 / 0.493 = 12 246 kW | USER-5 (generic proxy, R-PREFEED / R-Z2020) |
| Exhaust flow | 8.0 kg/kWh → 13.4 kg/s | ENG (no OEM data); sensitivity 7–9 |
| Exhaust temperature after the turbocharger | 240 °C | ENG; sensitivity 220 / 260 °C (load points 255 / 240 / 230 °C at 100 / 75 / 50 %) |
| Minimum exhaust outlet (acid dew point, fouling) | 160 °C | ENG (fuel- and OEM-dependent) |
| Economizer steam | 4 bar(a), T_sat 143.6 °C; pinch 15 K | ENG / DERIVED |
| Gas-side Δp | 1.5 kPa, against an assumed 2.5 kPa limit | ENG; **OEM approval required** |
| Charge air after the compressor | 160 °C at 75 % (about 200 °C at 100 %) | ENG / USER note; sensitivity via load |
| HT hot-water loop (charge air) | 95 / 85 °C, source approach 10 K | ENG; **OEM-approved interface required**; can be disabled |
| Jacket water | 85 °C; gross 5.2 % of fuel; recoverable 30 % | ENG / R-PREFEED |
| LT hot-water loop (jacket) | 80 / 70 °C | ENG |
| Delivery efficiency | 0.90 (steam and loops) | ENG; sensitivity 0.85 / 0.95 |

The recoverable heat is temperature-limited, not a fixed fraction:
- **Exhaust:** Q = m·cp·(T_in − max(T_min, T_sat + pinch)).
- **Charge air:** Q = m·cp·(T_ca − (T_return + approach)), and requires T_ca ≥ T_supply + approach.
- **Jacket water:** Q = fraction × gross, and requires T_JW ≥ T_supply + approach.
- **Low load:** below 50 % load (collection at 15 %, anchored at 0 %) there is no qualifying heat (USER, conservative).

Cross-check: the gross exhaust heat of 3.12 MW (to 25 °C) matches the previous 25.5 %-of-fuel estimate
(3.123 MW).

| Source | T | Gross MW | Recoverable MW | Delivered MW | Utilized MW |
|---|---|---|---|---|---|
| Exhaust (economizer → steam) | 240 → 160 °C | 3.12 | 1.16 | 1.04 | 1.04 |
| Charge air (HT loop 95/85 °C) | 160 → 95 °C | 1.59 | 0.86 | 0.78 | 0.78 |
| Jacket water (LT loop 80/70 °C) | 85 °C | 0.64 | 0.19 | 0.17 | 0 |
| **Total** | | **5.34** | **2.21** | **1.99** | **1.82** |

Charge-air gross is counted to 40 °C (the previous estimate gave 2.02 MW).

## 4. ATT heat sinks (MODEL, S1 at 5029.17 kg dry/h, after the S1 HXN)

The sinks are the **purchased** heating that remains after the S1 heat exchanger network, which already recovers
the U3 gas-cooler heat into C1, D0, D2 and D3. Those HXN savings are never offered again. The steam sinks add up to
the system's net purchased LP steam of 16.46 MW (a test checks this).

| Unit | Purchased before HXN (MW) | Purchased after HXN (MW) | Process T | WHR assigned (MW) | Remaining (MW) |
|---|---|---|---|---|---|
| D0 dryer (drum at 70 °C) | 9.29 | 3.10 | 70–74 °C | 1.82 (0.78 charge air + 1.04 steam) | 1.28 |
| D2 and D3 CaCO3 cake dryers (drum at 70 °C) | 1.99 | 0 (covered by the HXN) | 74 °C | 0 | 0 |
| C1 causticizer | 1.52 | 0 (covered by the HXN) | 90 °C | 0 | 0 |
| EC1 evaporator | 13.26 | 13.30 | 90–91.5 °C boiling | 0 | 13.30 |
| U3D sieve regeneration | 0.11 | 0.07 (the HXN covers 0.04) | 40 → 127 °C | 0 | 0.07 |
| U2 feed preheater (S2 boundary, conceptual) | — | 0.29 (fired-equivalent) | 78 → 95 °C | 0 (no source left) | 0.29 |
| U2 500 °C reaction heat (fired) | 13.54 | 13.24 | 500 °C | **not eligible** | 13.24 |

EC1's purchased duty after the HXN (13.30 MW) is slightly above its unit duty (13.26 MW). BioSTEAM's HXN
recomputes the utility exchanger of that stream; the after-HXN value is used because it is what the system
actually purchases.

**Allocation rules** (`marine_whr.allocate`):
- Sources are taken from the lowest grade first (jacket, then charge air, then exhaust steam); sinks from the
  coldest first.
- A source serves a sink only if T_return − 10 K ≥ T_sink,in and T_supply − 10 K covers the sink. Sensible sinks
  are covered partly, from the cold end.
- No sink receives more than its purchased duty, and each source is used once.
- External heating after = before − assigned (≥ 0).
- Heat delivered but not utilized: 0.17 MW of jacket water (all of it), for which no remaining sink is cold enough.

## 5. Added WHR equipment (installed USD, Mode A)

| Item | Installed USD | Basis |
|---|---|---|
| Exhaust economizer (513 m², U 0.05 kW/m²K) | 247 k | R-BST floating-head correlation, a proxy for finned water tubes |
| Steam drum / boiler interface | 150 k | ENG placeholder (vendor data MISSING) |
| Feedwater / condensate pump | 19 k | R-BST pump |
| Charge-air HT recovery cooler (367 m²) | 198 k | R-BST proxy; OEM interface |
| Scavenge-air loop pump | 21 k | R-BST pump |
| Piping, valves, bypass, sootblowing, instruments, controls, insulation | 254 k | ENG, 40 % of the above |
| **Total** | **0.89 M** | Sensitivity × 0.5 / × 2 and an IMO power-WHRS context of 5.2 MUSD |

- Pump electricity is 10.0 kW.
- The jacket-water loop has no sink, so its plate exchanger and pump are not part of the equipment.
- A buffer tank is optional and off; it is a transient buffer, not MW-hours of storage.
- There is no ORC (future option only).
- The process-side heaters of D0, D2, D3, EC1 and U3D are assumed to accept steam or hot water without modification
  (ENG).

## 6. Operating modes and feed logistics

- **Mode A**: 7 920 h/yr underway at 75 % MCR (idealized, USER-3). Same hourly capacity as S1, so 2 954 t H2/yr. The
  results of this document are for this mode. A reduced-hours operating mode (collection at 15 % and anchored at 0 %
  give no heat and no processing) is defined in `marine_whr.yaml` and is not reported here.
- **Feed.** S1's 120.7 t dry/d of presscake (76.3 % moisture, about 509 t wet/d) is far above one 200 t/d
  fresh-seaweed collector, which gives about 30 t dry/d at 85 %. Mode A would need the equivalent of about 4 such
  collectors. Feed supply and onboard storage are **unresolved feasibility limits**.
- The presscake feed itself presumes a biostimulant press upstream (S1 configuration). Its availability at sea is
  not examined.

## 7. Floating TEA (`data/marine_tea.yaml`)

- **Process CAPEX** = S1 installed capital (units + S1 estimate items) × 1.25 (USER-2; sensitivity 1.10–1.40).
  It is itemized as an "FCI factor" line.
- **WHR CAPEX** is added after the multiplier, so there is no double marine factor.
- **Labor.** S1 has no labor line: its FOC = 4 % of FCI lumps labor, maintenance and overhead. The S1 labor is
  taken as **50 % of the S1 FOC** (ENG, no staffing basis; sensitivity 25–75 %), which is about 0.33 MUSD/yr.
  - S2 FOC = 2.0 × S1 labor (fixed USD/yr, USER-1) + 50 % × 4 % × FCI_S2 for maintenance and overhead.
  - The multiplier therefore applies to labor only, and the CAPEX factor does not scale labor (a test checks
    this).
- **Utility savings** use the S1 marginal prices: LP steam 0.0221 USD/kWh of delivered heat (BioSTEAM agent),
  and U2 gas at the natural-gas price ÷ 0.90 burner efficiency. Pump electricity is added at the BioSTEAM power
  price.
- **Unchanged from S1:** materials, disposal, CaCO3 sales, the washed-residue assumption, financing and
  depreciation.
- **Excluded:** ship acquisition, charter or retrofit; hull and stability works; onboard storage; mooring and
  offloading; ship crew; port, insurance and class costs.

## 8. LCA (incremental)

- **Method.** The S1 method is unchanged. The WHR change = pump electricity − avoided boiler gas (steam ÷ 0.80)
  − avoided U2 gas (÷ 0.90), using the S1 factors.
- **Ship side.** The waste heat is burden-free because propulsion happens anyway. ATT does not claim zero
  propulsion emissions; propulsion fuel is not allocated (no data).
- **Not estimated:** a ship-system GWP with fuel allocation.
- The provisional items of S1 (lumped residue, which is credited as stored carbon, the sold CaCO3 and the residue-disposal
  assumption) are kept as they are.

## 9. Results (`results/tables/att_s2_*.csv`, all PROVISIONAL)

| Case | Hours | H2 t/yr | FCI MUSD | Labor MUSD/yr | Energy OPEX MUSD/yr | MSP USD/kg | GWP kg CO2e/kg H2 |
|---|---|---|---|---|---|---|---|
| S1 | 7 920 | 2 954 | 16.47 | 0.33 | 6.07 | 2.03 | 10.64 |
| S2, no WHR | 7 920 | 2 954 | 20.58 | 0.66 | 6.07 | 2.35 | 10.64 |
| S2, exhaust | 7 920 | 2 954 | 21.16 | 0.66 | 5.88 | 2.32 | 9.86 |
| S2, all three | 7 920 | 2 954 | 21.47 | 0.66 | 5.75 | 2.29 | 9.28 |

**Energy:**
- External heating falls from 30.0 to 28.2 MW (−6.1 %).
- Purchased LP steam falls by 11.0 %.
- The U2 fired duty (13.5 MW) is unchanged.

**Engine load:**
- At 50 % load, WHR utilizes 0.81 MW.
- At 100 % load, it utilizes 3.32 MW.
- At 15 % load and at anchor, it utilizes nothing.

**Cost:**
- The WHR saves 0.31 MUSD/yr of utilities, which recovers about a fifth of the floating cost penalty (+0.32 USD/kg H2
  without WHR, +0.26 with it).

## 10. Main limitations

1. No OEM part-load data: the exhaust and charge-air temperatures and flows are ENG estimates. The economizer
   backpressure, charge-air interface and jacket-water use need OEM approval.
2. Existing onboard heat users (composite boiler, freshwater generator) are ignored (optimistic).
3. WHR costs come from proxy correlations and placeholders; no vendor quotations.
4. The labor share of the S1 FOC is an assumption: S1 has no staffing estimate.
5. The floating multipliers are USER assumptions. Vessel and platform costs are excluded.
6. Feed logistics (about 4 collectors) and onboard storage are unresolved.
7. The U2 feed preheater is conceptual (wet slurry). Hot-water use in D0 assumes compatible heating surfaces.
8. The S1 provisional items (lumped residue, residue enthalpy, CaCO3 purity, drying and sales, residue disposal, and storage) carry
   over unchanged.
