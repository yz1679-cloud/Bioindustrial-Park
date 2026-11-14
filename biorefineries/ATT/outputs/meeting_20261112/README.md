# ATT advisor meeting — November 12, 2026

Final deliverable: **ATT_Advisor_Meeting_Figures.pdf** (19 landscape vector pages).
Figures 1–3 use S3 REE On; Figure 4 uses P0 through P3 as specified.

From `biorefineries/ATT`, reproduce with:

```powershell
../../.venv/Scripts/python.exe outputs/meeting_20261112/collect_meeting_data.py
../../.venv/Scripts/python.exe outputs/meeting_20261112/generate_figures.py
../../.venv/Scripts/python.exe outputs/meeting_20261112/verify_pdf.py
```

The first command reruns only the required scratch cases; the second reads
the existing validated report without modifying or regenerating it. The third
checks protected source hashes and renders every PDF page with PyMuPDF.

- `controlled_results.json`: fresh P0/P1/P2/P3, physical boundary, activities,
  and provenance.
- `figure_data_and_validation.json`: plotted values, 52-entry boundary ledger,
  and 57 numerical checks.
- `render_checks.json`: page bounds, vector content, source protection, PDF hash.
- `renders/`: inspected page images and contact sheets.

All 19 final pages were visually inspected. The independent read-only review
found no critical or important accounting issues. Uncertainties are documented
inside the PDF: illustrative H2 prices, benchmark LCA boundary differences,
product marketability, storage permanence, industrial WHR availability/costing,
provisional reagent factors, and existing omitted emissions. The existing model
and comprehensive report were preserved.
