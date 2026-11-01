# Bioindustrial-Park: BioSTEAM's Premier Biorefinery Models and Results
# Copyright (C) 2026-, Yu Zhou,
#                      Yalin Li <mailto.yalin.li@gmail.com>
#
# This module is under the UIUC open-source license. See
# github.com/BioSTEAMDevelopmentGroup/biosteam/blob/master/LICENSE.txt
# for license details.

"""
Default output locations of the ATT runners.

All generated results go to ``biorefineries/ATT/outputs/`` (inside the ATT
project, located from this file, not from the current working directory), so
ATT never writes into SaBRe's ``att_outputs/``. Set the ``ATT_PROJECT_OUTPUTS_DIR``
environment variable to use another root; every runner also accepts ``--out``.
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
"""
import os
from pathlib import Path

__all__ = ("PROJECT_ROOT", "ATT_ROOT", "SUBDIRS", "outputs_root", "output_dir")

# biorefineries/ATT/analyses/att/paths.py -> repository root
PROJECT_ROOT = Path(__file__).resolve().parents[4]
# biorefineries/ATT/
ATT_ROOT = Path(__file__).resolve().parents[2]

SUBDIRS = {
    "baseline_1kg": "baseline_1kg",
    "mass_energy": "full_scale/mass_energy",
    "tea": "full_scale/tea",
    "lca": "full_scale/lca",
    "summary": "full_scale/summary",
    "documentation": "documentation",
    "diagrams": "documentation/diagrams",
    "validation": "validation",
}


def outputs_root():
    """biorefineries/ATT/outputs/ (or ATT_PROJECT_OUTPUTS_DIR)."""
    env = os.environ.get("ATT_PROJECT_OUTPUTS_DIR")
    if env:
        return Path(env).resolve()
    return ATT_ROOT / "outputs"


def output_dir(key, root=None):
    """Directory for one result group (see module docstring), under ``root`` or ``outputs_root()``."""
    return (Path(root) if root is not None else outputs_root()) / SUBDIRS[key]
