"""Run the ATT GWP100 LCA and export results (separate from the inventory)."""
import argparse

from biorefineries.sabre.analyses.att.paths import SUBDIRS, output_dir
from biorefineries.sabre.analyses.att.lca import export_att_lca

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=None, help=f"output directory (default att_outputs/{SUBDIRS['lca']})")
    args = parser.parse_args()
    out = args.out or output_dir("lca")
    export_att_lca(out)
    print(f"ATT GWP100 results written to {out}")
