"""Export the side-by-side TEA/LCA contribution analysis of the Gas-C, Gas-Cprime and Gas-A scenarios."""
import argparse

from biorefineries.sabre.analyses.att.paths import SUBDIRS, output_dir
from biorefineries.sabre.analyses.att.scenarios import export_att_gas_scenario_comparison

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=None, help=f"output directory (default att_outputs/{SUBDIRS['gas_scenarios']})")
    args = parser.parse_args()
    out = args.out or output_dir("gas_scenarios")
    export_att_gas_scenario_comparison(out)
    print(f"ATT gas-scenario TEA/LCA comparison written to {out}")
