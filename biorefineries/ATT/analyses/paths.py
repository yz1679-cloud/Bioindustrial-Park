# Bioindustrial-Park: BioSTEAM's Premier Biorefinery Models and Results
# Copyright (C) 2026-, Yu Zhou,
#                      Yalin Li <mailto.yalin.li@gmail.com>
#
# This module is under the UIUC open-source license. See
# github.com/BioSTEAMDevelopmentGroup/biosteam/blob/master/LICENSE.txt
# for license details.

"""
Default output locations of the ATT runners.

All generated results go to ``biorefineries/ATT/results/`` (inside the ATT
project, located from this file, not from the current working directory; the
folder is git-ignored, like the other ``results`` folders). Set the ``ATT_PROJECT_RESULTS_DIR``
environment variable (``RESULTS_ENV``) to use another root; ``run_att_all --out`` sets it for every step, and each runner also
accepts ``--out``.
Nothing is ever written to ``data/``.

Layout (keys of ``output_dir``)::

    baseline_1kg/              baseline_1kg   1 kg/h mass and energy audit
    full_scale/mass_energy/    mass_energy    inventory, balances, utilities, LCI
    full_scale/tea/            tea            MSP, CAPEX/OPEX, cases, sensitivities
    full_scale/lca/            lca            GWP100, contributions, scenarios
    full_scale/summary/        summary        consolidated results, final sheets C1-C14
    documentation/             documentation  master model documentation
    documentation/diagrams/    diagrams       process flow diagrams
    validation/                validation     run summary, tests and QC tally
    tables/                    tables         ATT S1/S2 scenario tables (analyses/att_*.py)
"""
import os
from pathlib import Path

__all__ = ("PROJECT_ROOT", "ATT_ROOT", "RESULTS_ENV", "SUBDIRS", "results_root", "output_dir")

# biorefineries/ATT/analyses/paths.py -> repository root
PROJECT_ROOT = Path(__file__).resolve().parents[3]
# biorefineries/ATT/
ATT_ROOT = Path(__file__).resolve().parents[1]
# The one environment variable that overrides the output root (read here, set by test/run_att_all.py).
RESULTS_ENV = "ATT_PROJECT_RESULTS_DIR"

SUBDIRS = {
    "baseline_1kg": "baseline_1kg",
    "mass_energy": "full_scale/mass_energy",
    "tea": "full_scale/tea",
    "lca": "full_scale/lca",
    "summary": "full_scale/summary",
    "documentation": "documentation",
    "diagrams": "documentation/diagrams",
    "validation": "validation",
    "tables": "tables",
}


def results_root():
    """biorefineries/ATT/results/ (or the RESULTS_ENV environment variable)."""
    env = os.environ.get(RESULTS_ENV)
    if env:
        return Path(env).resolve()
    return ATT_ROOT / "results"


def output_dir(key, root=None):
    """Directory for one result group (see module docstring), under ``root`` or ``results_root()``."""
    return (Path(root) if root is not None else results_root()) / SUBDIRS[key]
