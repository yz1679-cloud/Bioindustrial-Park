"""Run the ATT preliminary TEA (H2 MSP) and export results."""
import argparse

from biorefineries.sabre.analyses.att.paths import SUBDIRS, output_dir
from biorefineries.sabre.analyses.att.tea import export_att_tea

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=None, help=f"output directory (default att_outputs/{SUBDIRS['tea']})")
    args = parser.parse_args()
    out = args.out or output_dir("tea")
    export_att_tea(out)
    print(f"ATT TEA results written to {out}")
