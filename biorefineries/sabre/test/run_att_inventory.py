"""Export the ATT research-stage inventory, LCI and TEA cost inputs."""
import argparse

from biorefineries.sabre.analyses.att.paths import SUBDIRS, output_dir
from biorefineries.sabre.analyses.att.inventory import export_att_inventory

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=None, help=f"output directory (default att_outputs/{SUBDIRS['mass_energy']})")
    args = parser.parse_args()
    out = args.out or output_dir("mass_energy")
    export_att_inventory(out)
    print(f"ATT inventory written to {out}")
