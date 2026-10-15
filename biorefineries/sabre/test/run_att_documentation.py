"""Export the ATT master documentation workbook, CSV files and README."""
import argparse

from biorefineries.sabre.analyses.att.reporting import export_att_documentation

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="att_documentation", help="output directory")
    args = parser.parse_args()
    export_att_documentation(args.out)
    print(f"ATT documentation written to {args.out}")
