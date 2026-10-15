"""Run the ATT GWP100 LCA and export results (separate from the inventory)."""
import argparse

from biorefineries.sabre.analyses._att_lca import export_att_lca

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="att_lca", help="output directory")
    args = parser.parse_args()
    export_att_lca(args.out)
    print(f"ATT GWP100 results written to {args.out}")
