# Bioindustrial-Park: BioSTEAM's Premier Biorefinery Models and Results
# Copyright (C) 2026-, Azhar Razin,
#                      Yalin Li <mailto.yalin.li@gmail.com>
#
# This module is under the UIUC open-source license. See
# github.com/BioSTEAMDevelopmentGroup/biosteam/blob/master/LICENSE.txt
# for license details.
"""
Process settings (scenario assumptions) for the SaBRe flowsheets, and
feedstock stream construction from those assumptions.
"""
from pathlib import Path
import yaml
import biosteam as bst

__all__ = (
    'load_assumptions', 'get_feedstock_type_params', 'make_sargassum_feed',
    'OPERATING_DAYS_PER_YEAR', 'OPERATING_HOURS_PER_YEAR',
)


def load_assumptions(filename: str):
    # assumptions.yaml is retired (moved to legacy/); every caller must
    # name one of the topic-specific files under data/ explicitly.
    path = Path(__file__).resolve().parent / "data" / filename
    with open(path, "r") as f:
        return yaml.safe_load(f)


# data/tea.yaml's operating_days -- single source of truth for ATTTEA's
# operating_days default (analyses/tea.py) and every unit-level add_OPEX
# annualization (units/_ad.py, _pretreatment.py, _biostimulant.py).
OPERATING_DAYS_PER_YEAR = load_assumptions("tea.yaml")["operating_days"]
OPERATING_HOURS_PER_YEAR = float(OPERATING_DAYS_PER_YEAR) * 24.0


def get_feedstock_type_params(A: dict, feedstock_type: str) -> dict:
    ft = A["feedstock_type"]
    if feedstock_type not in ft:
        raise KeyError(f"Unknown feedstock_type '{feedstock_type}'. Options: {list(ft.keys())}")
    return ft[feedstock_type]


def make_sargassum_feed(fresh_feed_kgph: float, moisture_frac: float, dry_composition: dict):
    """Wet Sargassum stream from the dry-basis composition of a data/feedstock.yaml feedstock type."""
    water_kgph = fresh_feed_kgph * moisture_frac
    dry_kgph   = fresh_feed_kgph * (1 - moisture_frac)
    dry_fracs = dict(dry_composition)

    # Normalize for numerical safety
    s = sum(dry_fracs.values())
    dry_fracs = {k: v / s for k, v in dry_fracs.items()}

    # Allocate component mass flows
    kwargs = {k: dry_kgph * frac for k, frac in dry_fracs.items()}

    return bst.Stream(
        "sargassum_feed",
        Water=water_kgph,
        units="kg/hr",
        phase="l",
        **kwargs,
    )
