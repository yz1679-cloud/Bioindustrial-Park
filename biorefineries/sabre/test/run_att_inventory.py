"""Export the ATT research-stage inventory, LCI and TEA cost inputs."""
import argparse

from biorefineries.sabre.analyses.att.inventory import export_att_inventory

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="att_inventory", help="output directory")
    args = parser.parse_args()
    export_att_inventory(args.out)
    print(f"ATT inventory written to {args.out}")
