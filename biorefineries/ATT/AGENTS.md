# ATT: rules for people and coding agents

## Branches
- Everyone works on the `ATT` branch. Do not create other branches, and keep the local and the remote copy of `ATT` the same.
- Never copy and paste code between branches or folders. Merge or push, so that the history is kept.
- No backup branches. Use a tag if an archive is needed.

## Where results go
- Generated results go to `results/` only. It is git-ignored; the default folders are in `analyses/paths.py`. Re-running a generator replaces its folder in place.
- No `outputs/` folder, no dated or versioned folders (`..._20261107`, `_FINAL`, `_old`), no copies of reports or PDFs in git.
- Do not commit runtime caches (numba, matplotlib) or `__pycache__`.
- `scenario_docs/` holds hand-written documentation only. A number typed into a document is copied from a result and must be updated when the result changes.

## Tests (`test/`)
A test stays only if it does one of two things:
1. it pins a reported result (a number in an email, report or figure), with a tolerance that covers the heat-integration (`hensmith`) release differences, about 8 % for MSP, GWP and AOC; process quantities (FCI, H2, NaOH, Ca(OH)2, U2 duty) stay at 1e-5;
2. it enforces a physical law or an accounting identity (mass and element balance, energy conservation, temperature feasibility, an independent re-computation of the DCF).

Do not add tests for input validation, file formats, HTML strings, row counts, or formulas copied from the code under test. If a deliberate model change moves a pinned value, update the pin in the same commit and say why.

## Code and files
- One copy of each module and each yaml file. Names say what the file is, not when or why it was made (no `_final`, `_v2`, `_10p`, `_old`).
- No planning, work-plan or notes files in the repository.
- Edit the model and its inputs only in `units/`, `system.py` and `data/*.yaml`.
