"""Export the ATT 1 kg dry Sargassum/h process mass and energy audit."""
import argparse
import os

from biorefineries.sabre.analyses.att.validation import export_att_1kgph_audit

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=os.path.join("att_documentation", "1kgph_audit"), help="output directory")
    args = parser.parse_args()
    export_att_1kgph_audit(args.out)
    print(f"ATT 1 kg/h audit written to {args.out}")
