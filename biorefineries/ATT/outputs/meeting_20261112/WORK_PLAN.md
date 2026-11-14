# ATT advisor figures — November 12, 2026

User specification: pasted task attachment ef15b4ce-9bc5-4556-a547-f827e21a0a40.

Deliver one vector PDF and standalone reproducible scripts in this directory.
Preserve every existing source/configuration/report file. Work on scratch model
instances in a separate Python process. The existing dirty working tree is the
validated source: every recorded input hash matches the November 7 report.

- [x] Read the reference payload and verify active S1 Off, S1 On, S3 On.
- [x] Calculate P0 with full cake and ATT char disposal at $0.04/kg; preserve LCA.
- [x] Reconcile energy at the process-heat plane, with primary fuel separately.
- [x] Group discounted cash flows and LCA inventory without residual allocation.
- [x] Research H2 references; label non-comparable selling prices illustrative.
- [x] Build Figures 1–4 and a complete boundary ledger using vector graphics.
- [x] Reconcile all calculations, protect input hashes, render and inspect all pages.

Design: landscape pages, Matplotlib vector charts, positive/negative stacks,
actual sequential waterfalls, compact tables and linked primary references.
Economic treatment calculations use FCI x existing CRF; MSP uses actual DCF.
Dry basis includes feed ash. H2 basis uses component mass, not gas mass.
Electricity enters EROI as delivered energy; free external waste heat has zero
assigned burden, with a physical-heat-inclusive ratio disclosed separately.
No feedstock-inclusive EROI without an established feed LHV.

Independent read-only review found no critical or important issues. Its two
minor observations are addressed: the empty PSA tail-gas placeholder is listed
explicitly, and the inaccessible DOE PDF URL is disclosed alongside the source.
The benchmark assumptions intentionally use the user-authorized illustrative
fallback: prices are not market quotes and the small CapEx LCA boundary mismatch
is explicit. Existing leach-NaOH and roaster-direct-emissions omissions remain
disclosed; no unrelated model audit or model correction was performed.

Final verification: 57 numerical checks pass; 19 landscape pages rendered and
visually inspected, including every ledger page. All pages contain vector
graphics and no embedded raster images. Text bounds/footer checks pass. The
reference HTML and all 26 recorded model/configuration inputs retain their
SHA-256 fingerprints. PDF SHA-256:
`d160256031e3b8466845fb279dbeb3f6ccd04525a84b60d4c5ffb31665494705`.
