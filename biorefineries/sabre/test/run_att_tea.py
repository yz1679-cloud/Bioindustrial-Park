"""Run the ATT preliminary TEA (H2 MSP) and export results."""
import argparse

from biorefineries.sabre.analyses._att_tea import export_att_tea

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="att_tea", help="output directory")
    args = parser.parse_args()
    export_att_tea(args.out)
    print(f"ATT TEA results written to {args.out}")
