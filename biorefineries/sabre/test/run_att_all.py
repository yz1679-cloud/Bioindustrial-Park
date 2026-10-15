"""
Regenerate every ATT result in dependency order, run the tests and tally the QC checks.

    python -m biorefineries.sabre.test.run_att_all [--out DIR] [--skip-tests] [--real-system-test]

Works from any working directory (``python path/to/run_att_all.py`` also
works). Each step runs in its own Python process, exactly as when the runners
are called one by one, with ATT_OUTPUTS_DIR set to the output root (default
att_outputs/ at the repository root). Order:

 1 baseline_1kg      1 kg/h mass and energy audit
 2 inventory         full-scale mass/energy inventory
 3 tea               MSP           (read by the cross-checks of 5, 6 and 8)
 4 lca               GWP100        (read by the cross-checks of 5, 6 and 8)
 5 consolidated      full-scale summary
 6 final             comparison workbook incl. D7 gas scenarios (C sheets -> summary)
 7 gas_scenarios     Gas-C / Gas-Cprime / Gas-A TEA and LCA (QC 14 checks against D7 of 7)
 8 documentation     master model documentation
 9 heat_integration  heat-recovery screening and HEN report (JSON)
10 diagram_svg/png   process flow diagrams

The scenarios run after final because their QC compares with final's D7.
Then the ATT unit tests (unless --skip-tests) and a tally of every exported
QC table are written to validation/run_summary.md and run_summary.json. The
exit status is 1 if a step or a test fails or any QC row is FAIL. QC rows that
were not evaluated are counted as NOT CHECKED, never as PASS.
"""
import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:  # run as a script without the package installed
    sys.path.insert(0, str(_ROOT))

from biorefineries.sabre.analyses.att.paths import PROJECT_ROOT, SUBDIRS, outputs_root  # noqa: E402

STEPS = (
    ("baseline_1kg", "run_att_1kgph_audit", ()),
    ("inventory", "run_att_inventory", ()),
    ("tea", "run_att_tea", ()),
    ("lca", "run_att_lca", ()),
    ("consolidated", "run_att_consolidated", ()),
    ("final", "run_att_final", ()),
    ("gas_scenarios", "run_att_gas_scenarios", ()),
    ("documentation", "run_att_documentation", ()),
    ("heat_integration", "run_att_heat_integration", ("--hen", "--json-out", "{heat_integration}/att_heat_report.json")),
    ("diagram_svg", "run_att_diagram", ("--format", "svg")),
    ("diagram_png", "run_att_diagram", ("--format", "png")),
)
# Exported tables whose status column holds check results.
QC_TABLES = (
    "baseline_1kg/14_Limitations_Checks.csv",
    "full_scale/mass_energy/17_stream_sanity_check.csv",
    "full_scale/mass_energy/22_utility_consistency.csv",
    "full_scale/tea/05_checks.csv",
    "full_scale/lca/08_checks.csv",
    "full_scale/summary/08_consistency_checks.csv",
    "full_scale/summary/C13_TEA_LCA_Consistency.csv",
    "scenarios/gas_yield/14_QC_Checks.csv",
    "documentation/26_QC_Checks.csv",
)


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


def _run(cmd, log, env, cwd):
    start = time.time()
    with open(log, "w", encoding="utf-8") as f:
        code = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, env=env, cwd=cwd).returncode
    return code, round(time.time() - start, 1)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", default=None, help="output root (default att_outputs/ at the repository root)")
    p.add_argument("--skip-tests", action="store_true", help="do not run the ATT unit tests")
    p.add_argument("--real-system-test", action="store_true",
                   help="also run the real-flowsheet smoke test (ATT_RUN_REAL_SYSTEM_TEST=1)")
    args = p.parse_args(argv)

    root = Path(args.out).resolve() if args.out else outputs_root()
    logs = root / SUBDIRS["validation"] / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, ATT_OUTPUTS_DIR=str(root), PYTHONWARNINGS="ignore",
               PYTHONPATH=os.pathsep.join(x for x in (str(PROJECT_ROOT), os.environ.get("PYTHONPATH")) if x))
    summary = dict(output_root=str(root), python=sys.version.split()[0], steps=[], tests=None, qc=None)
    failed = None
    for name, module, extra in STEPS:
        extra = [a.format(**{k: str(root / v) for k, v in SUBDIRS.items()}) for a in extra]
        cmd = [sys.executable, "-m", f"biorefineries.sabre.test.{module}", *extra]
        print(f"[{len(summary['steps']) + 1:2d}/{len(STEPS)}] {name} ...", end=" ", flush=True)
        code, seconds = _run(cmd, logs / f"{name}.log", env, root)
        summary["steps"].append(dict(step=name, module=module, exit_code=code, seconds=seconds,
                                     log=str((logs / f"{name}.log").relative_to(root))))
        print("ok" if code == 0 else f"FAILED (exit {code}, see {logs / f'{name}.log'})", f"{seconds} s")
        if code != 0:
            failed = name
            break

    if not args.skip_tests and failed is None:
        test_env = dict(env, ATT_RUN_REAL_SYSTEM_TEST="1") if args.real_system_test else env
        cmd = [sys.executable, "-m", "unittest", "discover", "-s", str(PROJECT_ROOT / "biorefineries/sabre/test"),
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


if __name__ == "__main__":
    sys.exit(main())
