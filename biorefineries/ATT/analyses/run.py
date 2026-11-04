# Bioindustrial-Park: BioSTEAM's Premier Biorefinery Models and Results
# Copyright (C) 2026-, Yu Zhou,
#                      Yalin Li <mailto.yalin.li@gmail.com>
#
# This module is under the UIUC open-source license. See
# github.com/BioSTEAMDevelopmentGroup/biosteam/blob/master/LICENSE.txt
# for license details.

"""
Export the ATT results, one step at a time or all of them in dependency order.

    python -m biorefineries.ATT.analyses.run STEP [--out DIR]
    python -m biorefineries.ATT.analyses.run all [--out DIR] [--skip-tests] [--real-system-test]

STEP is one of:

    baseline_1kg     1 kg/h mass and energy audit
    inventory        full-scale mass/energy inventory
    tea              MSP           (read by the cross-checks of consolidated and documentation)
    lca              GWP100        (read by the cross-checks of consolidated and documentation)
    consolidated     full-scale summary
    documentation    master model documentation
    diagram          process flow diagrams (--format svg|png|pdf, --dry-feed, --dark, --no-hxn)
    figures          BioSTEAM flowsheet diagrams of S1 and S2 at their capacity (svg and png; not part of ``all``)
    all              the steps above in this order (diagram as svg and png), then the ATT unit tests (unless
                     --skip-tests) and a tally of every exported QC table, written to
                     validation/run_summary.md and run_summary.json

The default output root is biorefineries/ATT/results/ (paths.results_root). In ``all`` every step runs in its own
Python process with ATT_PROJECT_RESULTS_DIR (paths.RESULTS_ENV) set to the output root, so every step resolves the
same paths. The exit status of ``all`` is 1 if a step or a test fails or any QC row is FAIL. QC rows that were not
evaluated are counted as NOT CHECKED, never as PASS.
"""
import argparse
import csv
import importlib
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

from biorefineries.ATT.analyses.paths import RESULTS_ENV, PROJECT_ROOT, SUBDIRS, output_dir, results_root

# step: (SUBDIRS key, module, export function, message)
EXPORTS = {
    "baseline_1kg": ("baseline_1kg", "validation", "export_att_1kgph_audit", "ATT 1 kg/h audit"),
    "inventory": ("mass_energy", "inventory", "export_att_inventory", "ATT inventory"),
    "tea": ("tea", "tea", "export_att_tea", "ATT TEA results"),
    "lca": ("lca", "lca", "export_att_lca", "ATT GWP100 results"),
    "consolidated": ("summary", "reporting", "export_att_consolidated_results", "ATT consolidated results"),
    "documentation": ("documentation", "reporting", "export_att_documentation", "ATT documentation"),
}
STEPS = (
    ("baseline_1kg", "baseline_1kg", ()),
    ("inventory", "inventory", ()),
    ("tea", "tea", ()),
    ("lca", "lca", ()),
    ("consolidated", "consolidated", ()),
    ("documentation", "documentation", ()),
    ("diagram_svg", "diagram", ("--format", "svg")),
    ("diagram_png", "diagram", ("--format", "png")),
)
DIAGRAM_KINDS = ("cluster", "thorough", "surface", "minimal")
# Exported tables whose status column holds check results.
QC_TABLES = (
    "baseline_1kg/14_Limitations_Checks.csv",
    "full_scale/mass_energy/17_stream_sanity_check.csv",
    "full_scale/mass_energy/22_utility_consistency.csv",
    "full_scale/tea/05_checks.csv",
    "full_scale/lca/08_checks.csv",
    "full_scale/summary/08_consistency_checks.csv",
    "documentation/26_QC_Checks.csv",
)


def export_diagrams(out, format="svg", dry_feed=1.0, dark=False, hxn=True):
    """BioSTEAM Graphviz process flow diagrams of the ATT system, one file per diagram kind."""
    import biosteam as bst
    from biorefineries.ATT.system import create_att_system

    out = os.fspath(out)
    os.makedirs(out, exist_ok=True)
    bst.preferences.dark_mode() if dark else bst.preferences.light_mode()
    bst.main_flowsheet.clear()
    sys_ = create_att_system(dry_sargassum_kgph=dry_feed, heat_exchanger_network=hxn)
    sys_.simulate()
    for kind in DIAGRAM_KINDS:
        file = os.path.join(out, f"{sys_.ID}_{kind}")
        sys_.diagram(kind=kind, file=file, format=format, number=True, label=True)
        print(f"{kind:>8} diagram written to {file}.{format}")


def export_figures(out, formats=("svg", "png")):
    """BioSTEAM's own flowsheet diagram of the S1 and S2 systems at their capacity (S2 is the S1 process)."""
    import biosteam as bst
    from biorefineries.ATT.analyses import scenarios as scen

    out = os.fspath(out)
    os.makedirs(out, exist_ok=True)
    bst.preferences.light_mode()
    # the baseline flowsheets and, with the REE recovery switch on (LC1 leach, RO1 roaster, leachate recycle), the *_ree_flowsheet files
    for suffix, ree in (("", False), ("_ree", True)):
        for key, spec in (("att_s1", scen.ATT_S1), ("att_s2", scen.ATT_S2)):
            bst.main_flowsheet.clear()
            system = scen.create(spec, ree_recovery=ree)
            for fmt in formats:
                file = os.path.join(out, f"{key}{suffix}_flowsheet")
                system.diagram(kind="thorough", file=file, format=fmt, number=True, label=True)
                print(f"{spec['short']}{' with REE recovery' if ree else ''} diagram written to {file}.{fmt}")


def run_step(step, out=None, format="svg", dry_feed=1.0, dark=False, hxn=True):
    """Run one export step; ``out`` defaults to its folder under paths.results_root()."""
    if step == "figures":
        export_figures(out or output_dir("figures"))
        return
    if step == "diagram":
        export_diagrams(out or output_dir("diagrams"), format, dry_feed, dark, hxn)
        return
    key, module, function, message = EXPORTS[step]
    out = out or output_dir(key)
    getattr(importlib.import_module(f"biorefineries.ATT.analyses.{module}"), function)(out)
    print(f"{message} written to {out}")


def _classify(status):
    s = status.strip().upper()
    if s.startswith("NOT CHECKED"):
        return "NOT CHECKED"
    if s in ("PASS", "OK"):
        return "PASS"
    if s.startswith("FAIL"):
        return "FAIL"
    return "INFORMATIONAL"   # BY DESIGN, FLAGGED, INFO, blank (raw values)


def _qc_tally(root):
    out = {}
    for rel in QC_TABLES:
        path = root / rel
        if not path.exists():
            out[rel] = {"MISSING TABLE": 1}
            continue
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        col = next((c for c in (rows[0] if rows else {}) if c.lower() == "status"), None)
        out[rel] = dict(Counter(_classify(r[col] if col else "") for r in rows))
    return out


def step_env(root, base=None):
    """Environment of every step and of the tests: the output root in paths.RESULTS_ENV, the repository on the path."""
    base = os.environ if base is None else base
    return dict(base, **{RESULTS_ENV: str(root)}, PYTHONWARNINGS="ignore",
                PYTHONPATH=os.pathsep.join(x for x in (str(PROJECT_ROOT), base.get("PYTHONPATH")) if x))


def _run(cmd, log, env, cwd):
    start = time.time()
    with open(log, "w", encoding="utf-8") as f:
        code = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, env=env, cwd=cwd).returncode
    return code, round(time.time() - start, 1)


def run_all(out=None, skip_tests=False, real_system_test=False):
    root = Path(out).resolve() if out else results_root()
    logs = root / SUBDIRS["validation"] / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    env = step_env(root)
    summary = dict(output_root=str(root), python=sys.version.split()[0], steps=[], tests=None, qc=None)
    failed = None
    for name, step, extra in STEPS:
        cmd = [sys.executable, "-m", "biorefineries.ATT.analyses.run", step, *extra]
        print(f"[{len(summary['steps']) + 1:2d}/{len(STEPS)}] {name} ...", end=" ", flush=True)
        code, seconds = _run(cmd, logs / f"{name}.log", env, root)
        summary["steps"].append(dict(step=name, module=step, exit_code=code, seconds=seconds,
                                     log=str((logs / f"{name}.log").relative_to(root))))
        print("ok" if code == 0 else f"FAILED (exit {code}, see {logs / f'{name}.log'})", f"{seconds} s")
        if code != 0:
            failed = name
            break

    if not skip_tests and failed is None:
        test_env = dict(env, ATT_RUN_REAL_SYSTEM_TEST="1") if real_system_test else env
        cmd = [sys.executable, "-m", "unittest", "discover", "-s", str(PROJECT_ROOT / "biorefineries/ATT/test"),
               "-t", str(PROJECT_ROOT), "-p", "test_att*.py"]
        print("[tests] ATT unit tests ...", end=" ", flush=True)
        code, seconds = _run(cmd, logs / "unit_tests.log", test_env, PROJECT_ROOT)
        text = (logs / "unit_tests.log").read_text(encoding="utf-8")
        ran = re.search(r"^Ran (\d+) tests?", text, re.M)
        verdict = re.findall(r"^(OK.*|FAILED.*)$", text, re.M)   # tests may print after the verdict
        skipped = re.search(r"skipped=(\d+)", verdict[-1]) if verdict else None
        summary["tests"] = dict(exit_code=code, seconds=seconds, ran=int(ran.group(1)) if ran else None,
                                skipped=int(skipped.group(1)) if skipped else 0,
                                result=verdict[-1] if verdict else f"no unittest verdict found (exit {code})")
        print(summary["tests"]["result"], f"{seconds} s")

    summary["qc"] = _qc_tally(root) if failed is None else None
    totals = Counter()
    for counts in (summary["qc"] or {}).values():
        totals.update(counts)
    qc_fail = totals["FAIL"] + totals["MISSING TABLE"]
    ok = failed is None and (summary["tests"] is None or summary["tests"]["exit_code"] == 0) and qc_fail == 0
    summary.update(status="OK" if ok else "FAILED", failed_step=failed, qc_totals=dict(totals))

    lines = [f"# ATT run summary: {summary['status']}", "", f"Output root: `{root}`", "", "## Steps", "",
             "| Step | Exit code | Seconds | Log |", "|---|---:|---:|---|"]
    lines += [f"| {s['step']} | {s['exit_code']} | {s['seconds']} | `{s['log']}` |" for s in summary["steps"]]
    if failed:
        lines += ["", f"**Stopped at failed step `{failed}`; later steps were not run.**"]
    if summary["tests"]:
        t = summary["tests"]
        lines += ["", "## Unit tests", "", f"{t['result']} (ran {t['ran']}, skipped {t['skipped']}, {t['seconds']} s)"]
    if summary["qc"]:
        lines += ["", "## QC tables", "", "PASS = evaluated and passed; NOT CHECKED = not evaluated (never counted as PASS); "
                  "INFORMATIONAL = design notes, flags or raw values.", "",
                  "| Table | PASS | FAIL | NOT CHECKED | INFORMATIONAL |", "|---|---:|---:|---:|---:|"]
        for rel, c in summary["qc"].items():
            lines.append(f"| {rel} | {c.get('PASS', 0)} | {c.get('FAIL', 0) + c.get('MISSING TABLE', 0)} | "
                         f"{c.get('NOT CHECKED', 0)} | {c.get('INFORMATIONAL', 0)} |")
        lines.append(f"| **Total** | {totals['PASS']} | {qc_fail} | {totals['NOT CHECKED']} | {totals['INFORMATIONAL']} |")
    vdir = root / SUBDIRS["validation"]
    (vdir / "run_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (vdir / "run_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\n{summary['status']}: QC PASS {totals['PASS']}, FAIL {qc_fail}, NOT CHECKED {totals['NOT CHECKED']}"
          f" -> {vdir / 'run_summary.md'}")
    return 0 if ok else 1


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("step", nargs="?", default="all", choices=("all", *EXPORTS, "diagram", "figures"))
    p.add_argument("--out", default=None, help="output directory (all: the output root); default biorefineries/ATT/results/...")
    p.add_argument("--skip-tests", action="store_true", help="all: do not run the ATT unit tests")
    p.add_argument("--real-system-test", action="store_true",
                   help="all: also run the real-flowsheet smoke test (ATT_RUN_REAL_SYSTEM_TEST=1)")
    p.add_argument("--format", default="svg", help="diagram: svg, png or pdf")
    p.add_argument("--dry-feed", type=float, default=1.0, help="diagram: dry Sargassum basis [kg/h]")
    p.add_argument("--dark", action="store_true", help="diagram: use the dark theme instead of light")
    p.add_argument("--no-hxn", action="store_true", help="diagram: omit the BioSTEAM HeatExchangerNetwork facility")
    args = p.parse_args(argv)
    if args.step == "all":
        return run_all(args.out, args.skip_tests, args.real_system_test)
    run_step(args.step, args.out, args.format, args.dry_feed, args.dark, not args.no_hxn)
    return 0


if __name__ == "__main__":
    sys.exit(main())
