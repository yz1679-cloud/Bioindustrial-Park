"""Export the consolidated ATT process/TEA/GWP100 results."""
import argparse

from biorefineries.sabre.analyses.att.paths import SUBDIRS, output_dir
from biorefineries.sabre.analyses.att.reporting import export_att_consolidated_results

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=None, help=f"output directory (default att_outputs/{SUBDIRS['summary']})")
    args = parser.parse_args()
    out = args.out or output_dir("summary")
    export_att_consolidated_results(out)
    print(f"ATT consolidated results written to {out}")
