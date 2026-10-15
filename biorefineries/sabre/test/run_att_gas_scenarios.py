"""Export the side-by-side TEA/LCA contribution analysis of the Gas-C, Gas-Cprime and Gas-A scenarios."""
import argparse
import os

from biorefineries.sabre.analyses.att.scenarios import export_att_gas_scenario_comparison

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=os.path.join("att_final", "gas_scenario_comparison"), help="output directory")
    args = parser.parse_args()
    export_att_gas_scenario_comparison(args.out)
    print(f"ATT gas-scenario TEA/LCA comparison written to {args.out}")
