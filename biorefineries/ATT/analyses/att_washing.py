"""ATT S1/S2 washing_on versus washing_off; no new scenarios.
Run: python -m biorefineries.ATT.analyses.att_washing
All files are written under paths.output_dir("tables").
"""
import json
import warnings
import pandas as pd
from biorefineries.ATT.analyses import scenarios as scen, inventory as inv, lca, tea
from biorefineries.ATT.analyses import marine_tea as mt
from biorefineries.ATT.analyses.breakdown import build_att_breakdown
from biorefineries.ATT.analyses.paths import output_dir


def washing_checks(system):
    u = inv._units(system)
    if "W2" not in u:
        return []
    rows = []
    for ID in ("W2", "F2R"):
        unit = u[ID]
        residual = sum((s.mass for s in unit.outs)) - sum((s.mass for s in unit.ins))
        for component, error in zip(unit.chemicals.IDs, residual):
            rows.append(dict(check=f"{ID} {component} component balance [kg/h]",
                             residual=float(error), status="PASS" if abs(error) < 1e-8 else "FAIL"))
        error = sum(s.F_mass for s in unit.outs) - sum(s.F_mass for s in unit.ins)
        rows.append(dict(check=f"{ID} total mass [kg/h]", residual=float(error),
                         status="PASS" if abs(error) < 1e-8 else "FAIL"))
    for component in ("CaCO3", "CaOH2"):
        error = float(u["F2R"].outs[0].imass[component] - u["F2"].outs[0].imass[component])
        rows.append(dict(check=f"Washing preserves {component} [kg/h]", residual=error,
                         status="PASS" if abs(error) < 1e-8 else "FAIL"))
    return rows


def run():
    materials, equipment, economics, impacts, checks, costs = [], [], [], [], [], []
    for mode in ("washing_off", "washing_on"):
        system = scen.create(washing=mode)
        streams, units = inv._streams(system), inv._units(system)
        for ID in ("f2_unwashed_cake", "caco3_cake", "scrubber_cake", "f2_wash_water", "f2_wash_liquor"):
            if ID not in streams:
                continue
            s = streams[ID]
            dry = float(s.F_mass - s.imass["Water"])
            row = dict(washing=mode, stream=ID, wet_kgph=float(s.F_mass), dry_kgph=dry,
                       CaCO3_purity_dry=float(s.imass["CaCO3"]) / dry if dry else float("nan"))
            row.update({ID: float(s.imass[ID]) for ID in ("Water", "CaCO3", "CaOH2", "NaOH", "Na2CO3")})
            materials.append(row)
        for ID in ("W2", "F2R"):
            if ID in units:
                unit = units[ID]
                equipment.append(dict(washing=mode, unit=ID, type=type(unit).__name__,
                    purchase_USD=unit.purchase_cost, installed_USD=unit.installed_cost,
                    electricity_kW=unit.power_utility.rate, design=json.dumps(unit.design_results)))
        checks.extend(dict(washing=mode, **r) for r in washing_checks(system))
        for f2_sales in (True, False):
            ref = mt.s1_reference(system, f2_sales=f2_sales)
            label = "optimistic F2+F3 component sales" if f2_sales else "no F2 sales; whole F2 cake disposed; F3 sales retained"
            base = build_att_breakdown(sys=system, f2_sales=f2_sales)
            result = tea.evaluate_att_tea(system, **scen.tea_config(f2_sales=f2_sales))
            for r in tea._opex_table(system, result):
                if r["category"] not in ("capital", "total"):
                    costs.append(dict(washing=mode, F2_sales=f2_sales, **r))
            baseline = ref["row"]
            rows = [dict(baseline, case="S1", engine_load=float("nan"))]
            for hours in (7920.0, 2640.0):
                for sources, name in (((), "S2 no WHR"), (("jacket", "scavenge", "exhaust"), "S2 WHR")):
                    row, _ = mt.evaluate_case(system, ref, name, sources=sources, hours=hours, load=0.75,
                                              f2_sales=f2_sales)
                    rows.append(row)
            for row in rows:
                economics.append(dict(washing=mode, sales_basis=label, F2_sales=f2_sales, **row))
            # The carbonate storage credit follows the CaCO3 disposition (att_lca.yaml
            # carbonate_storage_accounting), so the GWP depends on whether the F2 cake is sold.
            for row in base["GWP_by_contributor"].to_dict("records"):
                impacts.append(dict(washing=mode, F2_sales=f2_sales, **row))
        # Restore the optimistic configured S1 accounting after the comparisons.
        build_att_breakdown(sys=system)
    df = pd.DataFrame(economics)
    key = ["case", "hours", "F2_sales"]
    off = df.loc[df.washing == "washing_off"].set_index(key)
    for metric in ("MSP_USD_per_kg_H2", "FCI_USD", "AOC_net_USD_per_yr", "GWP_kgCO2e_per_kg_H2",
                   "GWP_inherited_carbonate_credit_kgCO2e_per_kg_H2"):
        df[f"washing_increment_{metric}"] = [
            r[metric] - off.loc[tuple(r[k] for k in key), metric] for r in df.to_dict("records")]
    return dict(materials=pd.DataFrame(materials), equipment=pd.DataFrame(equipment),
                economics=df, costs=pd.DataFrame(costs), lca=pd.DataFrame(impacts), checks=pd.DataFrame(checks))


if __name__ == "__main__":
    warnings.filterwarnings("ignore")
    out = output_dir("tables")
    out.mkdir(parents=True, exist_ok=True)
    for name, table in run().items():
        table.to_csv(out / f"att_washing_{name}.csv", index=False)
    print(f"Washing results saved to {out}")
