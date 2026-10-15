"""Export the final ATT results (experimental data, lab screening LCA, industrial TEA/LCA, comparisons)."""
import argparse

from biorefineries.sabre.analyses.att.final import export_att_final_results

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="att_final", help="output directory")
    args = parser.parse_args()
    export_att_final_results(args.out)
    print(f"ATT final results written to {args.out}")
