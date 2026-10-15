"""bt-migrate: scan | swap | eval | report | demo"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__, evaluator, report, scanner, swapper

HERE = Path(__file__).resolve().parent.parent


def cmd_scan(a) -> int:
    res = scanner.scan(a.repo, include_docs=not a.no_docs)
    j, m = scanner.write_reports(res, a.out)
    s = scanner.summarise(res)
    print(f"Scanned {res.files_scanned} files: {s['total_findings']} model references "
          f"({s['by_risk']}). Fine-tunes: {len(s['fine_tuned_models'])}.")
    print(f"  {m}\n  {j}")
    return 2 if a.fail_on_high and s["by_risk"].get("high") else 0


def cmd_swap(a) -> int:
    mapping = swapper.load_mapping(a.mapping)
    if a.include_docs:
        mapping.include_docs = True
    res = swapper.plan(a.repo, mapping)
    p, s = swapper.write(res, a.out)
    print(f"{len(res.changes)} replacements in {len(res.new_contents)} files; "
          f"{len(res.skipped_fine_tunes)} fine-tuned references left alone.")
    print(f"  patch:   {p}\n  summary: {s}")
    if a.apply:
        n = swapper.apply_in_place(a.repo, res)
        print(f"Applied in place to {n} files (--apply).")
    else:
        print(f"Nothing changed on disk. Review, then: git -C {a.repo} apply {Path(p).resolve()}")
    return 0


def cmd_eval(a) -> int:
    suite = evaluator.load_suite(a.suite)
    if a.api:
        suite["api"] = a.api
    provider, warn = evaluator.make_provider(suite, a.dry_run)
    if warn:
        print(warn, file=sys.stderr)
    res = evaluator.run_suite(suite, provider, a.old, a.new)
    j, m = evaluator.write(res, a.out)
    print(f"{res['mode']} run of {len(res['cases'])} cases: {res['summary']}")
    print(f"  {m}\n  {j}")
    bad = res["summary"].get("fail", 0) + res["summary"].get("error", 0)
    return 3 if a.fail_on_regression and bad else 0


def cmd_report(a) -> int:
    md, ht = report.generate(a.client, a.scan, a.out, a.swap_summary, a.diff, a.eval)
    print(f"  {ht}\n  {md}")
    return 0


def cmd_demo(a) -> int:
    """Run the full pipeline on examples/ (offline)."""
    ex = HERE / "examples"
    out = Path(a.out)
    repo = ex / "sample-app"
    for args in (["scan", str(repo), "--out", str(out)],
                 ["swap", str(repo), "--mapping", str(HERE / "mappings" / "gpt4-series-to-gpt-6-luna.yaml"), "--out", str(out)],
                 ["eval", str(ex / "evals" / "sample-suite.yaml"), "--dry-run", "--out", str(out)],
                 ["report", "--client", "Acme Widgets Ltd (sample)", "--scan", str(out / "scan.json"),
                  "--swap-summary", str(out / "swap-summary.json"), "--diff", str(out / "model-swap.diff"),
                  "--eval", str(out / "eval.json"), "--out", str(out)]):
        print(f"$ bt-migrate {' '.join(args)}")
        rc = main(args)
        if rc not in (0,):
            return rc
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bt-migrate", description="Burnt & Toast Studios OpenAI API migration kit")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="find model IDs in a repo")
    s.add_argument("repo")
    s.add_argument("--out", default="migration-out")
    s.add_argument("--no-docs", action="store_true", help="skip .md/.txt files")
    s.add_argument("--fail-on-high", action="store_true", help="exit 2 if any high-risk finding (for CI)")
    s.set_defaults(fn=cmd_scan)

    w = sub.add_parser("swap", help="write a reviewable patch from a mapping file")
    w.add_argument("repo")
    w.add_argument("--mapping", required=True)
    w.add_argument("--out", default="migration-out")
    w.add_argument("--include-docs", action="store_true")
    w.add_argument("--apply", action="store_true", help="ALSO edit files in place (off by default)")
    w.set_defaults(fn=cmd_swap)

    e = sub.add_parser("eval", help="regression-test old vs new model")
    e.add_argument("suite")
    e.add_argument("--old")
    e.add_argument("--new")
    e.add_argument("--api", choices=["chat", "responses"])
    e.add_argument("--dry-run", "--mock", dest="dry_run", action="store_true", help="no API calls; simulated outputs")
    e.add_argument("--out", default="migration-out")
    e.add_argument("--fail-on-regression", action="store_true", help="exit 3 on any fail/error")
    e.set_defaults(fn=cmd_eval)

    r = sub.add_parser("report", help="build the client report (HTML + Markdown)")
    r.add_argument("--client", required=True)
    r.add_argument("--scan", required=True)
    r.add_argument("--swap-summary")
    r.add_argument("--diff")
    r.add_argument("--eval")
    r.add_argument("--out", default="migration-out")
    r.set_defaults(fn=cmd_report)

    d = sub.add_parser("demo", help="run everything on examples/ offline")
    d.add_argument("--out", default=str(HERE / "examples" / "demo-output"))
    d.set_defaults(fn=cmd_demo)
    return p


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
