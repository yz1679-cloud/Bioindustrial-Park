"""
Default output locations of the ATT runners.

All generated results go to ``att_outputs/`` at the repository root, located
from this file (not from the current working directory). Set the
``ATT_OUTPUTS_DIR`` environment variable to use another root; every runner
also accepts ``--out``. Nothing is ever written to ``data/``.

Layout (keys of ``output_dir``)::

    experimental/              experimental   measured data, verification, lab screening LCA
    baseline_1kg/              baseline_1kg   1 kg/h mass and energy audit
    full_scale/mass_energy/    mass_energy    inventory, balances, utilities, LCI
    full_scale/tea/            tea            MSP, CAPEX/OPEX, cases, sensitivities
    full_scale/lca/            lca            GWP100, contributions, scenarios
    full_scale/summary/        summary        consolidated results, final sheets C1-C14
    comparison/                comparison     ATT_Final_Results.xlsx, experimental vs plant (D1-D7)
    scenarios/gas_yield/       gas_scenarios  Gas-C / Gas-Cprime / Gas-A TEA and LCA
    scenarios/heat_integration/ heat_integration  heat-recovery screening and HEN report
    documentation/             documentation  master model documentation
    documentation/diagrams/    diagrams       process flow diagrams
    validation/                validation     run summary, tests and QC tally
"""
import os
from pathlib import Path

__all__ = ("PROJECT_ROOT", "SUBDIRS", "outputs_root", "output_dir")

# biorefineries/sabre/analyses/att/paths.py -> repository root
PROJECT_ROOT = Path(__file__).resolve().parents[4]

SUBDIRS = {
    "experimental": "experimental",
    "baseline_1kg": "baseline_1kg",
    "mass_energy": "full_scale/mass_energy",
    "tea": "full_scale/tea",
    "lca": "full_scale/lca",
    "summary": "full_scale/summary",
    "comparison": "comparison",
    "gas_scenarios": "scenarios/gas_yield",
    "heat_integration": "scenarios/heat_integration",
    "documentation": "documentation",
    "diagrams": "documentation/diagrams",
    "validation": "validation",
}


def outputs_root():
    """att_outputs/ in the repository (or ATT_OUTPUTS_DIR; or the working directory for an installed package)."""
    env = os.environ.get("ATT_OUTPUTS_DIR")
    if env:
        return Path(env).resolve()
    if (PROJECT_ROOT / "setup.py").exists() and (PROJECT_ROOT / "biorefineries").is_dir():
        return PROJECT_ROOT / "att_outputs"
    return Path.cwd() / "att_outputs"


def output_dir(key, root=None):
    """Directory for one result group (see module docstring), under ``root`` or ``outputs_root()``."""
    return (Path(root) if root is not None else outputs_root()) / SUBDIRS[key]
