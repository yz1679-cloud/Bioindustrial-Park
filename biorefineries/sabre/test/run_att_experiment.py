"""Export the ATT experimental results: measured data, verification and lab screening LCA."""
import argparse

from biorefineries.sabre.analyses.att.paths import SUBDIRS, output_dir
from biorefineries.sabre.analyses.att.final import export_att_experimental_results

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=None, help=f"output directory (default att_outputs/{SUBDIRS['experimental']})")
    args = parser.parse_args()
    out = args.out or output_dir("experimental")
    export_att_experimental_results(out)
    print(f"ATT experimental results written to {out}")
