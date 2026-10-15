"""
Consolidated research-stage ATT results (process, TEA, GWP100) on one
frozen system, built only from the existing analysis modules:
_att_inventory (mass/energy), _att_tea (SaBReTEA cases) and _att_lca
(BioSTEAM GWP100). Adds only the collection/transport sensitivity and
TEA-LCA consistency checks. Writes att_results/att_consolidated_results.xlsx.
"""
import os

from biorefineries.sabre.analyses import _att_inventory as inv
from biorefineries.sabre.analyses import _att_lca as lca
from biorefineries.sabre.analyses import _att_tea as tea_mod
from biorefineries.sabre.utils import load_assumptions

__all__ = ("build_att_consolidated_results", "export_att_consolidated_results")

_TEA_PRICE = load_assumptions("tea.yaml")["price"]
COLLECTION_COST_USD_PER_WET_T = (0.0, 5.0, 10.0, 20.0, 50.0)
ILLUSTRATIVE_FUEL_KG_PER_WET_T = (1.0, 5.0, 10.0)   # parametric only; no data


def _row(table, section, item, value, unit, basis=""):
    table.append(dict(section=section, item=item, value=value, unit=unit, basis=basis))


def _process_and_materials(sys, utilities):
    s = inv._streams(sys)
    dry = inv._dry_feed_kgph(sys)
    hours = sys.operating_hours
    U2 = inv._units(sys)["U2"]
    u = {r["item"]: r["per_kg_dry"] for r in utilities}
    h2 = float(s["h2_product"].imass["H2"]) / dry
    rows = []
    P, M = "Process and energy", "Materials and products"
    _row(rows, P, "Wet Sargassum feed", float(s["att_sargassum_feed"].F_mass) * 24 / 1e3, "t/d", "SaBRe scale")
    _row(rows, P, "Dry Sargassum feed", dry * 24 / 1e3, "t/d", "SaBRe database moisture 86.73 %")
    _row(rows, P, "Operating time", hours, "h/yr", "tea.yaml 330 d/yr")
    measured = U2.reported_gas_yield_mmol_per_g_daf
    for gas in ("H2", "CH4", "CO", "CO2"):
        _row(rows, P, f"{gas} yield, measured", float(measured[gas]), "mmol/g daf", "EXPERIMENTAL (Ni-CatATT)")
        _row(rows, P, f"{gas} yield, model", U2._model_gas_yield_mmol_per_g_daf[gas], "mmol/g daf",
             f"ENGINEERING PREDICTION ({U2.gas_closure_method})")
    _row(rows, P, "H2 at U2 outlet", float(U2.outs[0].imass["H2"]) / dry, "kg/kg dry", "model yield x daf")
    _row(rows, P, "H2 product (PSA 90 %)", h2, "kg/kg dry", "PSA recovery: engineering assumption")
    _row(rows, P, "H2 product", h2 * dry * hours / 1e3, "t/yr", "")
    for item, unit in (("U2 natural gas: fuel input (LHV)", "MJ/kg dry"),
                       ("LP steam: utility heat incl. 5 % loss", "MJ/kg dry"),
                       ("LP steam: boiler natural gas (LHV)", "MJ/kg dry"),
                       ("Cooling water: heat removed", "MJ/kg dry"),
                       ("Electricity: total", "kWh/kg dry")):
        _row(rows, P, item, u[item], unit, "frozen model, reference scale")
    _row(rows, P, "Total natural gas (U2 + steam boiler)", u["U2 natural gas: fuel input (LHV)"]
         + u["LP steam: boiler natural gas (LHV)"], "MJ/kg dry", "")
    _row(rows, P, "Total natural gas per kg H2", (u["U2 natural gas: fuel input (LHV)"]
                                                 + u["LP steam: boiler natural gas (LHV)"]) / h2, "MJ/kg H2", "")
    ledger = {r["item"]: r["value"] for r in inv.get_att_sodium_calcium_ledger(sys)}
    _row(rows, P, "Effective NaOH recovery", ledger["Effective NaOH recovery = 1 - makeup / gross"], "-",
         "95 % whole-liquor recycle")
    for label, ID, comp in (("NaOH makeup", "fresh_naoh_solid", "NaOH"), ("Ca(OH)2", "lime", "CaOH2"),
                            ("Process water (D1)", "dissolution_water", "Water")):
        v = float(s[ID].imass[comp]) / dry
        _row(rows, M, label, v, "kg/kg dry", "")
        _row(rows, M, f"{label} per kg H2", v / h2, "kg/kg H2", "")
    cake = s["caco3_cake"]
    _row(rows, M, "CaCO3 equivalent in cake", float(cake.imass["CaCO3"]) / dry, "kg/kg dry", "model (C1 85 %)")
    _row(rows, M, "CaCO3 wet filter cake (impure)", float(cake.F_mass) / dry, "kg/kg dry",
         "incl. Ca(OH)2, NaOH, Na2CO3, 25 % water")
    _row(rows, M, "Ash/char cake to disposal", float(s["ash_residue_cake"].F_mass) / dry, "kg/kg dry", "")
    ww = sum(float(s[ID].F_mass) for ID in lca._LCA["waste_management"]["wastewater_streams"]) / dry
    _row(rows, M, "Wastewater incl. alkaline purge", ww, "kg/kg dry", "")
    tail = s["u3_tail_gas"]
    _row(rows, M, "PSA off-gas (total)", float(tail.F_mass) / dry, "kg/kg dry",
         "explicit collected stream; final fate unresolved; direct CH4 emission not in baseline GWP; "
         "treatment equipment and cost not in baseline TEA")
    for gas in ("CH4", "H2", "CO", "CO2"):
        _row(rows, M, f"  {gas} in PSA off-gas", float(tail.imass[gas]) / dry, "kg/kg dry", "model")
    for r in inv.get_att_experimental_gas_yield_scenario(sys)[:4]:
        if r["item"] in ("CH4", "CO"):
            _row(rows, M, f"{r['item']} at the measured yield (reference)", r["U2_outlet_kg_per_kg_dry"],
                 "kg/kg dry", "EXPERIMENTAL value x daf; not a balanced-model output")
    return rows


def _collection_transport(sys, estimates, gwp_per_kg_dry):
    s = inv._streams(sys)
    dry = inv._dry_feed_kgph(sys)
    h2 = float(s["h2_product"].imass["H2"]) / dry
    wet_t_per_kg_dry = float(s["att_sargassum_feed"].F_mass) / 1e3 / dry
    rows = []
    for case, kw in (("Reference", {}), ("Case A", dict(caco3=dict(fraction=0.0)))):
        for cost in COLLECTION_COST_USD_PER_WET_T:
            msp = tea_mod.evaluate_att_tea(sys, estimates, feedstock_usd_per_wet_t=cost, **kw)["msp"]
            rows.append(dict(analysis="TEA", case=case, parameter="collection + transport cost",
                             value=cost, unit="USD/wet t", result=msp, result_unit="MSP USD/kg H2",
                             note="sensitivity; no SaBRe/ATT location-specific data"))
    sc = _TEA_PRICE["sargassum"]
    for name, v in sc["scenario"].items():
        msp = tea_mod.evaluate_att_tea(sys, estimates, feedstock_usd_per_wet_t=v * 1e3,
                                       caco3=dict(fraction=0.0))["msp"]
        rows.append(dict(analysis="TEA", case="Case A", parameter=f"tea.yaml sargassum.{name}", value=v * 1e3,
                         unit="USD/wet t", result=msp, result_unit="MSP USD/kg H2", note=sc["source"]))
    tea_mod.evaluate_att_tea(sys, estimates)
    ef = float(lca._EF["marine_fuel"]["value"])
    coeff = wet_t_per_kg_dry * ef
    rows.append(dict(analysis="LCA", case="Baseline", parameter="GWP coefficient per kg fuel per wet t",
                     value=1.0, unit="kg fuel/wet t", result=coeff / h2, result_unit="kg CO2e/kg H2",
                     note=f"marine fuel combustion {ef} kg CO2/kg (collaborators); fuel upstream not included; "
                          f"{coeff:.4f} kg CO2e/kg dry"))
    for fuel in ILLUSTRATIVE_FUEL_KG_PER_WET_T:
        rows.append(dict(analysis="LCA", case="Baseline", parameter="illustrative fuel intensity (NOT data)",
                         value=fuel, unit="kg fuel/wet t", result=(gwp_per_kg_dry + fuel * coeff) / h2,
                         result_unit="kg CO2e/kg H2", note="parametric; no collection fuel-use data available"))
    return rows


def _consistency(sys, estimates, tea_result, contributions, utilities):
    """TEA and LCA use the same activity data (same system, same streams)."""
    s = inv._streams(sys)
    hours = sys.operating_hours
    dry = inv._dry_feed_kgph(sys)
    c = {r["item"]: r for r in contributions}
    u = {r["item"]: r["per_kg_dry"] for r in utilities}
    tea = tea_result["tea"]
    gas = [hu for hu in sys.heat_utilities if hu.agent.ID == "natural_gas"]
    ng_tea_MJ = (sum(hu.cost for hu in gas) * hours
                 + next(v for n, v in tea_result["voc_items"] if n.startswith("Natural"))) / tea_mod._ng_usd_per_MJ()
    aux = next(v for n, v in tea_result["voc_items"] if n.startswith("Electricity: agitators"))
    elec_tea_kWh = (sys.power_utility.rate * hours + aux / tea_mod.bst.PowerUtility.price)
    checks = [
        ("Operating hours (TEA = LCA)", tea.operating_days * 24, sys.operating_hours),
        ("H2 product for MSP = LCA functional-unit basis [kg/yr]", float(s["h2_product"].F_mass) * hours,
         c["TOTAL (System.get_net_impact)"]["GWP_kgCO2e_per_kg_dry"] / c["TOTAL (System.get_net_impact)"][
             "GWP_kgCO2e_per_kg_H2"] * dry * hours),
        ("NaOH: TEA purchase = LCA activity [kg/kg dry]", float(s["fresh_naoh_solid"].F_mass) / dry,
         c["NaOH makeup"]["activity_per_kg_dry"]),
        ("Ca(OH)2: TEA purchase = LCA activity [kg/kg dry]", float(s["lime"].F_mass) / dry,
         c["Ca(OH)2"]["activity_per_kg_dry"]),
        ("U2 natural gas: TEA priced fuel = LCA fuel [MJ/kg dry]", ng_tea_MJ / hours / dry,
         c["Natural gas U2: combustion"]["activity_per_kg_dry"]),
        ("U2 natural gas = inventory fuel [MJ/kg dry]", ng_tea_MJ / hours / dry, u["U2 natural gas: fuel input (LHV)"]),
        ("Electricity priced in TEA = LCA unit + auxiliary [kWh/kg dry]", elec_tea_kWh / hours / dry,
         c["Electricity: process units"]["activity_per_kg_dry"]
         + c["Electricity: outside unit models (agitators, EC1 vacuum)"]["activity_per_kg_dry"]),
        ("Wastewater: TEA disposal volume = LCA treatment volume [m3/kg dry]",
         sum(float(s[ID].F_mass) for ID in tea_mod._T["prices"]["wastewater_streams"]) / 1e3 / dry,
         c["Wastewater treatment"]["activity_per_kg_dry"]),
        ("Ash/char cake: TEA disposal = LCA landfill [kg/kg dry]",
         sum(float(s[ID].F_mass) for ID in tea_mod._T["prices"]["solid_waste_streams"]) / dry,
         c["Landfill: ash/char cake"]["activity_per_kg_dry"]),
    ]
    rows = [dict(check=a, TEA_or_model=b, LCA_or_reference=d,
                 status="PASS" if abs(b - d) <= 1e-6 * max(1.0, abs(d)) else "FAIL") for a, b, d in checks]
    rows += [
        dict(check="Steam: TEA prices steam (agent price covers generation); LCA counts boiler natural gas",
             TEA_or_model=float("nan"), LCA_or_reference=float("nan"), status="BY DESIGN (no double count)"),
        dict(check="Cooling: TEA cooling-water price; LCA cooling-tower electricity",
             TEA_or_model=float("nan"), LCA_or_reference=float("nan"), status="BY DESIGN (no double count)"),
        dict(check="CaCO3: TEA Case B revenue does not imply an LCA credit; LCA baseline has no CaCO3 credit",
             TEA_or_model=float("nan"), LCA_or_reference=float("nan"), status="BY DESIGN"),
        dict(check="CaCO3 cake: TEA Case A disposes the cake; LCA baseline treats it as a coproduct without "
                   "burden. Case-A-consistent LCA adds cake landfill (see GWP sheet)",
             TEA_or_model=float("nan"), LCA_or_reference=float("nan"), status="FLAGGED, quantified"),
        dict(check="tea.yaml sargassum scenarios mid_cost_collect = high_cost_collect = 0.05 USD/kg while the "
                   "range reaches 0.10 (existing SaBRe data; not changed)",
             TEA_or_model=float("nan"), LCA_or_reference=float("nan"), status="FLAGGED"),
    ]
    return rows


def _existing_outputs_check(rows, msp_reference, gwp_per_kg_H2):
    """Compare with the existing exported workbooks, when present."""
    import pandas as pd

    for path, item, value in (("att_tea/00_summary.csv", "H2 MSP", msp_reference),
                              ("att_lca/01_summary.csv", "GWP100 per kg H2", gwp_per_kg_H2)):
        if os.path.exists(path):
            df = pd.read_csv(path)
            ref = float(df.loc[df["item"] == item, "value"].iloc[0])
            rows.append(dict(check=f"Matches existing {path}: {item}", TEA_or_model=value, LCA_or_reference=ref,
                             status="PASS" if abs(value - ref) <= 1e-6 * max(1.0, abs(ref)) else "FAIL"))
    return rows


def _findings(msp, caco3, gwp, stage, slag, sens_tea, sens_lca, ct, case_a_lca, h2, lime_share=float("nan"),
              s_factor=float("nan"), cap_share=float("nan")):
    """Preliminary conclusions with a robustness label for presentation."""
    def m(case, price=250.0, handling=0.0, f=None, lime="0.24 (original)"):
        for r in caco3:
            if (r["lime_price"] == lime and r["case"].startswith(case)
                    and (f is None or (r["marketable_fraction"] == f and r["CaCO3_price_usd_per_t"] == price
                                       and r["handling_usd_per_t"] == handling))):
                return r["MSP_USD_per_kg_H2"]
    st = {r["stage"]: r for r in stage}
    ng = st["Onsite fuel combustion"]["share"] + st["Natural gas supply chain"]["share"]
    ct10 = [r["result"] for r in ct if r["analysis"] == "TEA" and r["case"] == "Case A"
            and r["parameter"] == "collection + transport cost"]
    rows = [
        ("Cost drivers", f"Ca(OH)2 is the largest cost ({lime_share:.0%} of the reference MSP {msp:.2f} USD/kg); steam, NaOH "
         f"and filter-cake disposal follow; capital recovery is {cap_share:.0%}. The process is operating-cost dominated.",
         "ROBUST (ranking); main text"),
        ("Conservative MSP", f"Case A (no CaCO3 sales, cake disposed at an assumed 0.04 USD/kg) "
         f"{m('Case A'):.2f} USD/kg H2; reference without cake cost {msp:.2f}.", "ROBUST as a bound; main text"),
        ("Lime price", f"0.28 instead of 0.24 USD/kg (USGS 2025e, f.o.b.) raises MSP by "
         f"{m('Case A', lime='0.28 (USGS MCS 2026, 2025e)') - m('Case A'):.2f} USD/kg; delivery not included.",
         "SENSITIVITY; main text"),
        ("CaCO3 marketability", f"At 250 USD/t (optimistic commodity reference) Case A falls to "
         f"{m('Case B', f=0.5):.2f} (50 % marketable) and {m('Case B', f=1.0):.2f} USD/kg (100 %); at 50 USD/t "
         f"and 100 % only to {m('Case B', price=50.0, f=1.0):.2f}. Feasibility hinges on cake quality and market.",
         "SENSITIVITY; main text figure, not a result"),
        ("Collection/transport cost", f"Each 10 USD/wet t adds ~{(ct10[2] - ct10[0]):.2f} USD/kg H2 "
         f"(~{1 / h2 * 7.536 / 1e3 * 1e3:.0f} t wet Sargassum per t H2); 50 USD/t -> "
         f"{ct10[4]:.2f}.", "SENSITIVITY; main text (data pending)"),
        ("GWP100", f"{gwp:.1f} kg CO2e/kg H2 (partial boundary, no collection/transport); natural gas "
         f"(combustion + upstream) {ng:.0%}, chemical supply {st['Chemical supply']['share']:.0%}.",
         "ROBUST (ranking); value partial-boundary"),
        ("Lime sourcing (LCA)", f"Steel-slag Ca(OH)2 lowers GWP to {slag:.1f} kg CO2e/kg H2 "
         f"({slag / gwp - 1:.0%}); limestone range 0.59-1.00 gives "
         f"{min(r['GWP_kgCO2e_per_kg_H2'] for r in sens_lca if 'CaOH2_limestone' in r['scenario']):.1f}-"
         f"{max(r['GWP_kgCO2e_per_kg_H2'] for r in sens_lca if 'CaOH2_limestone' in r['scenario']):.1f}.",
         "SENSITIVITY; main text"),
        ("Case-A-consistent GWP", f"Landfilling the CaCO3 cake (WARM proxy) adds {case_a_lca:.2f} kg CO2e/kg H2.",
         "SENSITIVITY; SI"),
        ("Gas-yield basis", f"Model gas yields = {s_factor:.4f} x measured for all four gases (ratios preserved); the "
         "measured gases carry 1.38x the feed's available electrons, so s is fixed by conservation. Model yields are "
         "engineering predictions, not measurements.", "ROBUST as method; value depends on feed composition"),
        ("Open items before submission", "Collection/transport activity data; CaCO3 purity and outlet; delivered "
         "lime price and source; P1 power basis (5 vs 280 kWh/t dry); PSA capital; plant-location grid factor; "
         "indirect capital; collaborator confirmation of gas analysis.", "TO RESOLVE"),
    ]
    return [dict(topic=a, finding=b, robustness_and_placement=c) for a, b, c in rows]


def build_att_consolidated_results():
    sys = tea_mod.create_att_tea_system()
    estimates = inv.get_att_cost_estimates(sys)
    # TEA (reference case leaves the reference prices applied).
    caco3 = tea_mod.get_att_caco3_cases(sys, estimates)
    lime = tea_mod.get_att_lime_price_cases(sys, estimates)
    sens_tea = tea_mod.get_att_tea_sensitivity(sys, estimates)
    p1 = tea_mod.get_att_p1_power_cases(sys, estimates)
    result = tea_mod.evaluate_att_tea(sys, estimates)
    capex = tea_mod._capex_table(sys, result)
    opex = tea_mod._opex_table(sys, result)
    case_a = tea_mod.evaluate_att_tea(sys, estimates, caco3=dict(fraction=0.0))
    opex_a = tea_mod._opex_table(sys, case_a)
    result = tea_mod.evaluate_att_tea(sys, estimates)
    # LCA on the same system.
    applied = lca.apply_att_gwp(sys, estimates=estimates)
    contributions = lca.get_att_gwp_contributions(sys, applied)
    stage = lca.get_att_gwp_by_stage(contributions)
    sens_lca = lca.get_att_gwp_sensitivity(sys, estimates)
    total = contributions[-1]
    gwp_dry, gwp_h2 = total["GWP_kgCO2e_per_kg_dry"], total["GWP_kgCO2e_per_kg_H2"]
    slag = next(r["GWP_kgCO2e_per_kg_H2"] for r in sens_lca if r["scenario"].startswith("S1"))
    s = inv._streams(sys)
    dry = inv._dry_feed_kgph(sys)
    h2 = float(s["h2_product"].imass["H2"]) / dry
    cake_landfill = float(s["caco3_cake"].F_mass) / dry * float(lca._EF["inert_landfill"]["value"])
    utilities = inv.get_att_purchased_utilities(sys, estimates)
    ct = _collection_transport(sys, estimates, gwp_dry)
    gwp_rows = [dict(view="by stage", item=r["stage"], GWP_kgCO2e_per_kg_dry=r["GWP_kgCO2e_per_kg_dry"],
                     GWP_kgCO2e_per_kg_H2=r["GWP_kgCO2e_per_kg_H2"], share=r["share"]) for r in stage]
    gwp_rows += [dict(view="by input", item=r["item"], GWP_kgCO2e_per_kg_dry=r["GWP_kgCO2e_per_kg_dry"],
                      GWP_kgCO2e_per_kg_H2=r["GWP_kgCO2e_per_kg_H2"], share=r["share"]) for r in contributions]
    gwp_rows += [
        dict(view="lime sourcing", item="Limestone Ca(OH)2 (baseline)", GWP_kgCO2e_per_kg_dry=gwp_dry,
             GWP_kgCO2e_per_kg_H2=gwp_h2, share=float("nan")),
        dict(view="lime sourcing", item="Steel-slag Ca(OH)2 (S1)", GWP_kgCO2e_per_kg_dry=slag * h2,
             GWP_kgCO2e_per_kg_H2=slag, share=float("nan")),
        dict(view="Case-A-consistent", item="Baseline + CaCO3 cake landfill (WARM inert proxy)",
             GWP_kgCO2e_per_kg_dry=gwp_dry + cake_landfill, GWP_kgCO2e_per_kg_H2=(gwp_dry + cake_landfill) / h2,
             share=float("nan")),
    ]
    msp_rows = [dict(case="Reference (no CaCO3 revenue, cake not costed)", lime_USD_per_kg=0.24,
                     MSP_USD_per_kg_H2=result["msp"])]
    msp_rows += [dict(case=r["case"] if r["case"].startswith("Case A") else
                      f"{r['case']} | {r['CaCO3_price_usd_per_t']} USD/t, handling "
                      f"{r['handling_usd_per_t']} USD/t, marketable {r['marketable_fraction']}",
                      lime_USD_per_kg=r["lime_price"], MSP_USD_per_kg_H2=r["MSP_USD_per_kg_H2"])
                 for r in caco3 if not r["case"].startswith("Reference")]
    consistency = _consistency(sys, estimates, result, contributions, utilities)
    consistency = _existing_outputs_check(consistency, result["msp"], gwp_h2)
    sens = ([dict(analysis="TEA (MSP USD/kg H2)", case=r["case"], value=r["MSP_USD_per_kg_H2"], delta=r["delta"])
             for r in sens_tea]
            + [dict(analysis="TEA lime price (Case A)", case=r["lime_price"], value=r["MSP_USD_per_kg_H2"],
                    delta=r["delta_vs_0.24"]) for r in lime if r["case"].startswith("Case A")]
            + [dict(analysis="TEA/LCA P1 power (pending decision)", case=r["case"], value=r["MSP_USD_per_kg_H2"],
                    delta=r["delta_GWP_kgCO2e_per_kg_H2"]) for r in p1]
            + [dict(analysis="LCA (kg CO2e/kg H2)", case=r["scenario"], value=r["GWP_kgCO2e_per_kg_H2"],
                    delta=r["delta_per_kg_H2"]) for r in sens_lca])
    assumptions = _assumptions_table()
    lime_share = next(r["USD_per_kg_H2"] for r in opex if r["item"] == "Ca(OH)2") / result["msp"]
    findings = _findings(result["msp"], caco3, gwp_h2, stage, slag, sens_tea, sens_lca, ct, cake_landfill / h2, h2,
                         lime_share, float(inv._units(sys)["U2"]._gas_scale_factor),
                         next(r["USD_per_kg_H2"] for r in opex if r["category"] == "capital") / result["msp"])
    return {
        "00_key_findings": findings,
        "01_process_materials": _process_and_materials(sys, utilities),
        "02_tea_capex": capex,
        "03_tea_opex_reference": opex,
        "03b_tea_opex_case_A": opex_a,
        "04_msp_cases": msp_rows,
        "05_gwp100": gwp_rows,
        "06_sensitivities": sens,
        "07_collection_transport": ct,
        "08_consistency_checks": consistency,
        "09_assumptions_sources": assumptions,
    }


def _assumptions_table():
    rows = [
        ("EXPERIMENTAL", "Measured gas yields", "H2 66.728, CH4 8.769, CO 0.165, CO2 0.187 mmol/g daf",
         "ATT Inputs and Assumptions_261005.xlsx, Ni-CatATT"),
        ("ENGINEERING", "Model gas yields", "s x measured (uniform_redox_scaling, s = 0.5998)", "att.yaml reactor.material_balance"),
        ("EXPERIMENTAL", "CH4 / CO yields (separate scenario)", "8.769 / 0.165 mmol/g daf", "same workbook; not in balanced model"),
        ("EXPERIMENTAL", "NaOH : daf", "2 : 1", "workbook / advisor"),
        ("LITERATURE/DATABASE", "Feedstock", "ash 34.53 % dry, moisture 86.73 %", "SaBRe feedstock.yaml (Milledge 2020)"),
        ("LITERATURE", "Ca(OH)2 price", "0.24 (ref.) / 0.28 USD/kg, f.o.b.", "USGS MCS 2025 / 2026"),
        ("LITERATURE", "Emission factors", "NaOH 1.12, Ca(OH)2 0.91/0, NG 0.056 + 0.0199, grid 0.449",
         "collaborators; NETL 2019; GREET 2022 (att_lca.yaml)"),
        ("LITERATURE", "Collection cost scenarios", "-20 to 100 USD/wet t", "tea.yaml, Rodriguez-Martinez 2023"),
        ("ENGINEERING", "PSA recovery / capital", "90 % / 38.6 MUSD (+/-50 %)", "assumption / review anchor"),
        ("ENGINEERING", "Filter cakes, recycle, C1", "F1 30 %, F2 25 % moisture; 95 % recycle; C1 85 %, lime 1.1x",
         "att.yaml"),
        ("ENGINEERING", "Heat supply", "U2 burner 0.90; steam boiler 0.80; 5 % heat loss", "workbook / BioSTEAM"),
        ("ENGINEERING", "Cake disposal (Case A)", "0.04 USD/kg wet", "tea.yaml disposal_solid (assumed)"),
        ("ILLUSTRATIVE", "CaCO3 price", "250 USD/t (optimistic) / 50 USD/t (low)", "not a demonstrated price"),
        ("FINANCIAL", "SaBReTEA", "IRR 10 %, 20 yr, MACRS7, 21 % tax, FOC 4 % FCI, FCI = installed cost",
         "tea.yaml"),
        ("COST YEAR", "Equipment / prices", "CEPCI 567.5 (2017) / 2024-2025 prices", "see att_tea 10_cost_year"),
        ("BOUNDARY", "LCA", "cradle-to-gate, collection/transport EXCLUDED, no allocation or CaCO3 credit",
         "att_lca.yaml"),
    ]
    rows = [dict(type=a, item=b, value=c, source=d) for a, b, c, d in rows]
    rows += [dict(type="LIMITATION", item="TEA", value=x, source="att_tea.yaml") for x in
             load_assumptions("att_tea.yaml")["tea"]["limitations"]]
    return rows


def export_att_consolidated_results(out_dir="att_results"):
    import pandas as pd

    tables = build_att_consolidated_results()
    os.makedirs(out_dir, exist_ok=True)
    with pd.ExcelWriter(os.path.join(out_dir, "att_consolidated_results.xlsx")) as writer:
        for name, rows in tables.items():
            df = pd.DataFrame(rows)
            df.to_csv(os.path.join(out_dir, f"{name}.csv"), index=False)
            df.to_excel(writer, sheet_name=name[:31], index=False)
    return tables
