"""Export the final ATT results (experimental data, lab screening LCA, industrial TEA/LCA, comparisons)."""
import argparse

from biorefineries.sabre.analyses.att.final import export_att_final_results
from biorefineries.sabre.analyses.att.paths import output_dir

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=None,
                        help="directory for ATT_Final_Results.xlsx and the D sheets (default att_outputs/comparison)")
    parser.add_argument("--summary-out", default=None,
                        help="directory for the C-sheet CSVs (default att_outputs/full_scale/summary, "
                             "or --out when only --out is given)")
    args = parser.parse_args()
    export_att_final_results(args.out, args.summary_out)
    print(f"ATT final results written to {args.out or output_dir('comparison')}")
