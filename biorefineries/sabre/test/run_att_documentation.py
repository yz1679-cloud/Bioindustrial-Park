"""Export the ATT master documentation workbook, CSV files and README."""
import argparse

from biorefineries.sabre.analyses.att.paths import SUBDIRS, output_dir
from biorefineries.sabre.analyses.att.reporting import export_att_documentation

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=None, help=f"output directory (default att_outputs/{SUBDIRS['documentation']})")
    args = parser.parse_args()
    out = args.out or output_dir("documentation")
    export_att_documentation(out)
    print(f"ATT documentation written to {out}")
