"""Export BioSTEAM Graphviz process flow diagrams of the ATT system."""
import argparse
import os

import biosteam as bst

from biorefineries.sabre.analyses.att.paths import output_dir
from biorefineries.sabre.systems._att_system import create_att_system

KINDS = ("cluster", "thorough", "surface", "minimal")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=None, help="output directory (default att_outputs/documentation/diagrams)")
    parser.add_argument("--format", default="svg", help="svg, png or pdf")
    parser.add_argument("--dry-feed", type=float, default=1.0, help="dry Sargassum basis [kg/h]")
    parser.add_argument("--dark", action="store_true", help="use the dark theme instead of light")
    parser.add_argument("--heat-integration", action="store_true", help="include the HXR facility")
    args = parser.parse_args()
    args.out = os.fspath(args.out or output_dir("diagrams"))

    os.makedirs(args.out, exist_ok=True)
    if args.dark:
        bst.preferences.dark_mode()
    else:
        bst.preferences.light_mode()
    bst.main_flowsheet.clear()
    sys = create_att_system(dry_sargassum_kgph=args.dry_feed, heat_integration=args.heat_integration)
    sys.simulate()
    for kind in KINDS:
        file = os.path.join(args.out, f"{sys.ID}_{kind}")
        sys.diagram(kind=kind, file=file, format=args.format, number=True, label=True)
        print(f"{kind:>8} diagram written to {file}.{args.format}")
