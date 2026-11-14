# Report-only revision plan

Spec: user-provided “Revise ATT Advisor Meeting Figures and Generate a New 10-Page PDF”.

Use saved full-precision results and the existing plotting helpers. Do not run
collect_meeting_data.py or any model evaluation. Create only new output files.

- [x] Snapshot source/data/report hashes and original PDF bytes.
- [x] Rebuild Page 2 with S3-only bars, combined H1/H3, and separate demand/supply legend columns.
- [x] Rebuild Page 4 with Other costs, distinct category colors, larger table and preserved DCF notes.
- [x] Rebuild Page 5 with one natural-gas WHR adjustment, Other emissions, and separate storage credit.
- [x] Assemble exactly ten pages, copying original Pages 1, 3, and 6–10 directly.
- [x] Verify full-precision aggregation, unchanged page text/content/rendering, page bounds and source hashes.
- [x] Render and visually inspect revised Pages 2, 4, and 5 at presentation resolution.

Implementation: standalone generate_revised_10p.py; new PDF and three PNG previews
alongside the original; revision_validation.json records the checks. This is a
report artifact task, without repository integration or model tests.
