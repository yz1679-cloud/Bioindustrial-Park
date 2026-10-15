"""Export the ATT 1 kg dry Sargassum/h process mass and energy audit."""
import argparse

from biorefineries.sabre.analyses.att.paths import SUBDIRS, output_dir
from biorefineries.sabre.analyses.att.validation import export_att_1kgph_audit

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=None, help=f"output directory (default att_outputs/{SUBDIRS['baseline_1kg']})")
    args = parser.parse_args()
    out = args.out or output_dir("baseline_1kg")
    export_att_1kgph_audit(out)
    print(f"ATT 1 kg/h audit written to {out}")
