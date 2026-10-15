"""Export the consolidated ATT process/TEA/GWP100 results."""
import argparse

from biorefineries.sabre.analyses.att.reporting import export_att_consolidated_results

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="att_results", help="output directory")
    args = parser.parse_args()
    export_att_consolidated_results(args.out)
    print(f"Consolidated ATT results written to {args.out}")
