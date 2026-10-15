"""CLI: scan | swap | fix | init-evals | eval | report | packs | mapping | licence | demo"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__, brand, licence, scanner
from .packs import load_packs

HERE = Path(__file__).resolve().parent.parent


def _packs(a):
    provs = [p.strip() for x in (a.pack or []) for p in x.split(",") if p.strip()] or None
    return load_packs(provs, offline=a.offline or None, url=a.packs_url, extra_files=a.pack_file)


def _off(a):
    """--offline if given, else None so <PREFIX>_OFFLINE decides."""
    return True if getattr(a, "offline", False) else None


def cmd_licence(a) -> int:
    if a.action == "buy":
        print(licence.buy_url(licence.repo_identity(a.repo)))
        return 0
    lic = licence.resolve(a.licence, a.repo)
    if a.action == "forget":
        if lic.key and lic.repo_id:
            licence.clear_cache(lic.key, lic.repo_id)
        print("Cleared the cached licence verification for this repo." if lic.key else "No licence key set.")
        return 0
    lic = licence.require("licence check", a.licence, a.repo, offline=_off(a))
    print(licence.describe(lic))
    return 0


def cmd_scan(a) -> int:
    packs = _packs(a)
    res = scanner.scan(a.repo, include_docs=not a.no_docs, packs=packs)
    j, m = scanner.write_reports(res, a.out)
    s = scanner.summarise(res)
    if a.summary_file:
        Path(a.summary_file).parent.mkdir(parents=True, exist_ok=True)
        with open(a.summary_file, "a", encoding="utf-8") as fh:
            fh.write(scanner.to_summary_markdown(res) + "\n")
    if a.annotations:
        for line in scanner.github_annotations(res):
            print(line)
    if a.format == "json":
        print(json.dumps(res.to_dict()["summary"], indent=2))
    else:
        packs_s = ", ".join(f"{p['provider']} v{p['version']} ({p['source']}"
                            + (f"; {p['detail']}" if p["detail"] else "") + ")" for p in res.packs)
        print(f"Scanned {res.files_scanned} files: {s['total_findings']} model references {s['by_risk']}. "
              f"Fine-tunes: {len(s['fine_tuned_models'])}.\n  packs: {packs_s}\n  {m}\n  {j}")
    return 2 if a.fail_on_high and s["by_risk"].get("high") else 0


def cmd_swap(a) -> int:
    from . import swapper
    if a.apply or licence.GATE_SWAP_PATCH:
        print(licence.describe(licence.require("swap-apply", a.licence, a.repo, offline=_off(a))), file=sys.stderr)
    packs = _packs(a)
    mapping = swapper.load_mapping(a.mapping) if a.mapping else swapper.mapping_from_packs(packs)
    if a.include_docs:
        mapping.include_docs = True
    res = swapper.plan(a.repo, mapping, packs)
    p, s = swapper.write(res, a.out)
    print(f"{len(res.changes)} replacements in {len(res.new_contents)} files; "
          f"{len(res.skipped_fine_tunes)} fine-tuned references left alone. Mapping: {mapping.source or a.mapping}")
    print(f"  patch:   {p}\n  summary: {s}")
    if a.apply:
        n = swapper.apply_in_place(a.repo, res)
        print(f"Applied in place to {n} files (--apply).")
    else:
        print(f"Nothing changed on disk. Review, then: git -C {a.repo} apply {Path(p).resolve()}")
    return 0


def _dirty(repo: str, files: list[str]) -> list[str]:
    """Touched files with uncommitted changes (only when the repo is a git checkout)."""
    import shutil
    import subprocess
    git = shutil.which("git")
    if not git or not files:
        return []
    r = subprocess.run([git, "-C", repo, "status", "--porcelain", "--", *files], capture_output=True, text=True)
    return [ln[3:] for ln in r.stdout.splitlines()] if r.returncode == 0 else []


def cmd_fix(a) -> int:
    from . import fixer, swapper
    from .fixer import verify as fverify
    if a.apply or licence.GATE_FIX_PATCH:
        print(licence.describe(licence.require("fix-apply", a.licence, a.repo, offline=_off(a))), file=sys.stderr)
    if a.verify and a.live and not a._demo:
        print(licence.describe(licence.require("eval", a.licence, a.repo, offline=_off(a))), file=sys.stderr)
    packs = _packs(a)
    mapping = swapper.load_mapping(a.mapping) if a.mapping else None
    res = fixer.plan_fixes(a.repo, packs, mapping=mapping, model_swap=not a.no_model_swap,
                           assume_model=a.assume_model, include_inferred=a.include_inferred)
    paths = fixer.write(res, a.out)
    c = res.counts()
    print(f"{len(res.new_contents)} files changed ({res.swap_changes} model ID replacements). "
          + ", ".join(f"{k}: {v}" for k, v in sorted(c.items())))
    print(f"  patch: {paths['diff']}\n  plan:  {paths['md']}")
    ok = True
    if a.verify:
        rep = fverify.verify(a.repo, res, packs, Path(a.out) / "verify", live=a.live, suite_path=a.evals,
                             assume_model=a.assume_model, include_inferred=a.include_inferred)
        ok = rep["ok"]
        print(f"  verify: {'PASS' if ok else 'FAIL'} ({'live' if a.live else 'mock'} eval) -> {Path(a.out) / 'verify' / 'verify.md'}")
    if a.apply:
        if not ok:
            print("Not applied: verification failed (see verify.md).", file=sys.stderr)
            return 6
        dirty = _dirty(a.repo, sorted(res.new_contents))
        if dirty and not a.force:
            print("Not applied: these files have uncommitted changes (commit or stash them, or pass --force): "
                  + ", ".join(dirty), file=sys.stderr)
            return 7
        n = fixer.engine.apply_in_place(a.repo, res)
        print(f"Applied in place to {n} files (--apply).")
    else:
        print(f"Nothing changed on disk. Review, then: git -C {a.repo} apply {Path(paths['diff']).resolve()}")
    return 0 if ok else 6


def cmd_init_evals(a) -> int:
    from . import initevals
    if not a._demo:
        print(licence.describe(licence.require("init-evals", a.licence, a.repo, offline=_off(a))), file=sys.stderr)
    packs = _packs(a)
    suite, skipped = initevals.build_suite(a.repo, packs=packs)
    out = initevals.write_suite(suite, skipped, a.out)
    todos = sum(1 for c in suite["cases"] if "todo" in c or "TODO" in str(c.get("prompt", "")))
    print(f"Wrote {out}: {len(suite['cases'])} case(s) from call sites ({todos} need your input). "
          f"Old {suite['models']['old']} -> new {suite['models']['new']}.")
    for s in skipped:
        print(f"  not covered: {s}")
    return 0


def cmd_eval(a) -> int:
    from . import evaluator
    if not a._demo:
        print(licence.describe(licence.require("eval", a.licence, ".", offline=_off(a))), file=sys.stderr)
    suite = evaluator.load_suite(a.suite)
    if a.api:
        suite["api"] = a.api
    todo = [c["id"] for c in suite["cases"] if "TODO" in str(c.get("prompt", "")) and not c.get("skip")]
    provider, warn = evaluator.make_provider(suite, a.dry_run)
    if todo and provider.name != "mock":
        print(f"{len(todo)} case(s) still have TODO prompts ({', '.join(todo[:5])}). Replace them with real inputs "
              "(or set `skip: true`) before a live run; nothing was sent.", file=sys.stderr)
        return 5
    if warn:
        print(warn, file=sys.stderr)
    res = evaluator.run_suite(suite, provider, a.old, a.new)
    j, m = evaluator.write(res, a.out)
    print(f"{res['mode']} run of {len(res['cases'])} cases: {res['summary']}\n  {m}\n  {j}")
    bad = res["summary"].get("fail", 0) + res["summary"].get("error", 0)
    return 3 if a.fail_on_regression and bad else 0


def cmd_report(a) -> int:
    from . import report
    if not a._demo:
        root = json.loads(Path(a.scan).read_text()).get("root", ".")
        print(licence.describe(licence.require("report", a.licence, root if Path(root).exists() else ".", offline=_off(a))), file=sys.stderr)
    md, ht = report.generate(a.client, a.scan, a.out, a.swap_summary, a.diff, a.eval, label=a.label, packs=_packs(a),
                             fix_plan_path=a.fix_plan, fix_verify_path=a.fix_verify)
    print(f"  {ht}\n  {md}")
    return 0


def cmd_packs(a) -> int:
    from . import packs as pk
    if a.action == "list":
        for i in _packs(a).info():
            print(f"{i['provider']:<10} v{i['version']:<12} {i['status']:<7} {i['source']}"
                  + (f" ({i['detail']})" if i["detail"] else "") + f"  {i['name']}")
    elif a.action == "validate":
        for f in a.files:
            if Path(f).name == "pack.schema.json":
                continue
            pk.validate(json.loads(Path(f).read_text()))
            print(f"OK  {f}")
    elif a.action == "build-site":
        from .site import build_site
        out = build_site(Path(a.out))
        print(f"Static site written to {out}")
    return 0


def cmd_mapping(a) -> int:
    from . import swapper
    import yaml
    m = swapper.mapping_from_packs(_packs(a), a.migration or None)
    text = (f"# {m.source}\n" + yaml.safe_dump({"source": m.source, "mappings": m.replacements,
                                                "fine_tuned": {}, "include_docs": False}, sort_keys=False))
    if a.out:
        Path(a.out).write_text(text)
        print(f"Wrote {a.out}")
    else:
        print(text)
    return 0


def cmd_demo(a) -> int:
    """Run the whole pipeline on examples/ offline (source checkout only; no licence needed)."""
    ex = HERE / "examples"
    if not ex.exists():
        print("demo needs a source checkout (examples/ not found)", file=sys.stderr)
        return 1
    out = Path(a.out)
    repo = ex / "sample-app"
    steps = [["scan", str(repo), "--out", str(out), "--offline"],
             ["swap", str(repo), "--mapping", str(HERE / "mappings" / "gpt4-series-to-gpt-6-luna.yaml"), "--out", str(out), "--offline"],
             ["fix", str(repo), "--out", str(out), "--verify", "--offline"],
             ["eval", str(ex / "evals" / "sample-suite.yaml"), "--dry-run", "--out", str(out)],
             ["report", "--client", "Acme Widgets Ltd (sample)", "--scan", str(out / "scan.json"),
              "--swap-summary", str(out / "swap-summary.json"), "--diff", str(out / "fix.diff"),
              "--fix-plan", str(out / "fix-plan.json"), "--fix-verify", str(out / "verify" / "verify.json"),
              "--eval", str(out / "eval.json"), "--out", str(out), "--offline",
              "--label", "Demo: simulated eval outputs on a fictional sample repo"]]
    for args in steps:
        print(f"$ {brand.CLI_NAME} {' '.join(args)}")
        rc = main(args, _demo=True)
        if rc:
            return rc
    return 0


def _pack_opts(p):
    g = p.add_argument_group("migration packs")
    g.add_argument("--pack", action="append", help="provider pack(s) to use, e.g. openai,anthropic (default: all)")
    g.add_argument("--pack-file", action="append", help="load a local pack JSON (overrides same provider)")
    g.add_argument("--offline", action="store_true",
                   help=f"no network at all: use the bundled pack (or ${brand.env_name('OFFLINE')}=1)")
    g.add_argument("--packs-url", help=f"base URL for hosted packs (default: ${brand.env_name('PACKS_URL')} or built-in)")


def _lic_opt(p):
    p.add_argument("--licence", "--license", dest="licence", help=f"licence key (or set ${licence.ENV_VAR})")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=brand.CLI_NAME, description=f"{brand.PRODUCT_NAME}: find and fix retiring AI model IDs in your code.")
    p.add_argument("--version", action="version", version=f"{brand.CLI_NAME} {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="free: find retiring model IDs in a repo")
    s.add_argument("repo", nargs="?", default=".")
    s.add_argument("--out", default=f"{brand.CLI_NAME}-out")
    s.add_argument("--no-docs", action="store_true", help="skip .md/.txt files")
    s.add_argument("--fail-on-high", action="store_true", help="exit 2 if any high-risk finding (for CI)")
    s.add_argument("--summary-file", help="append a compact markdown summary (e.g. $GITHUB_STEP_SUMMARY)")
    s.add_argument("--annotations", action="store_true", help="print GitHub Actions annotations")
    s.add_argument("--format", choices=["text", "json"], default="text", help="stdout format")
    _pack_opts(s)
    s.set_defaults(fn=cmd_scan)

    w = sub.add_parser("swap", help="write a reviewable patch (--apply needs a licence)")
    w.add_argument("repo")
    w.add_argument("--mapping", help="mapping YAML (default: generated from the packs' headline migrations)")
    w.add_argument("--out", default=f"{brand.CLI_NAME}-out")
    w.add_argument("--include-docs", action="store_true")
    w.add_argument("--apply", action="store_true", help="ALSO edit files in place [licence]")
    _lic_opt(w)
    _pack_opts(w)
    w.set_defaults(fn=cmd_swap)

    fx = sub.add_parser("fix", help="automatic fixes from the pack rules, as a reviewable patch (--apply needs a licence)")
    fx.add_argument("repo", nargs="?", default=".")
    fx.add_argument("--out", default=f"{brand.CLI_NAME}-out")
    fx.add_argument("--mapping", help="mapping YAML for the model swap (default: generated from the packs)")
    fx.add_argument("--no-model-swap", action="store_true",
                    help="only fix arguments; fixes that need the new model are then listed, not applied")
    fx.add_argument("--assume-model", help="model to assume for calls whose model isn't visible in the code")
    fx.add_argument("--include-inferred", action="store_true", help="also apply rules marked 'inferred' in the pack")
    fx.add_argument("--verify", action="store_true",
                    help="apply to a scratch copy, check syntax + idempotence, and replay each fixed call old vs new")
    fx.add_argument("--live", action="store_true", help="with --verify: real API calls with YOUR key [licence]")
    fx.add_argument("--evals", help="with --verify: also run your eval suite, with the fixed arguments on matching cases")
    fx.add_argument("--apply", action="store_true", help="ALSO edit files in place [licence]")
    fx.add_argument("--force", action="store_true", help="with --apply: allow files with uncommitted changes")
    _lic_opt(fx)
    _pack_opts(fx)
    fx.set_defaults(fn=cmd_fix)

    ie = sub.add_parser("init-evals", help="[licence] generate a starter eval suite from the scan's call sites")
    ie.add_argument("repo", nargs="?", default=".")
    ie.add_argument("--out", default="evals/regression.yaml")
    _lic_opt(ie)
    _pack_opts(ie)
    ie.set_defaults(fn=cmd_init_evals)

    e = sub.add_parser("eval", help="[licence] regression-test old vs new model (uses YOUR provider key)")
    e.add_argument("suite")
    e.add_argument("--old")
    e.add_argument("--new")
    e.add_argument("--api", choices=["chat", "responses"])
    e.add_argument("--dry-run", "--mock", dest="dry_run", action="store_true", help="no API calls; simulated outputs")
    e.add_argument("--out", default=f"{brand.CLI_NAME}-out")
    e.add_argument("--fail-on-regression", action="store_true", help="exit 3 on any fail/error")
    _lic_opt(e)
    e.set_defaults(fn=cmd_eval)

    r = sub.add_parser("report", help="[licence] client report (HTML + Markdown)")
    r.add_argument("--client", required=True)
    r.add_argument("--scan", required=True)
    r.add_argument("--swap-summary")
    r.add_argument("--diff")
    r.add_argument("--eval")
    r.add_argument("--label", help="banner at the top of the report")
    r.add_argument("--fix-plan", help="fix-plan.json from `fix` (adds the automatic-fixes section)")
    r.add_argument("--fix-verify", help="verify/verify.json from `fix --verify`")
    r.add_argument("--out", default=f"{brand.CLI_NAME}-out")
    _lic_opt(r)
    _pack_opts(r)
    r.set_defaults(fn=cmd_report)

    k = sub.add_parser("packs", help="list / validate migration packs, or build the static hosting site")
    k.add_argument("action", choices=["list", "validate", "build-site"])
    k.add_argument("files", nargs="*", help="pack files (validate)")
    k.add_argument("--out", default="site", help="output folder (build-site)")
    _pack_opts(k)
    k.set_defaults(fn=cmd_packs)

    mp = sub.add_parser("mapping", help="print the default swap mapping generated from the packs")
    mp.add_argument("--migration", action="append", help="migration id(s) (default: headline migrations)")
    mp.add_argument("--out")
    _pack_opts(mp)
    mp.set_defaults(fn=cmd_mapping)

    li = sub.add_parser("licence", aliases=["license"], help="check this repo's licence, print the buy link, or forget the cached check")
    li.add_argument("action", choices=["status", "buy", "forget"])
    li.add_argument("repo", nargs="?", default=".")
    li.add_argument("--offline", action="store_true", help="use only the cached verification")
    _lic_opt(li)
    li.set_defaults(fn=cmd_licence)

    d = sub.add_parser("demo", help="run everything on examples/ offline (source checkout)")
    d.add_argument("--out", default=str(HERE / "examples" / "demo-output"))
    d.set_defaults(fn=cmd_demo)
    return p


def main(argv: list[str] | None = None, _demo: bool = False) -> int:
    a = build_parser().parse_args(argv)
    a._demo = _demo
    try:
        return a.fn(a)
    except licence.LicenceError as e:
        print(f"{brand.CLI_NAME}: {e}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
