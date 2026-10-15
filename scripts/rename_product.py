#!/usr/bin/env python3
"""Rename the product in one go.

    python scripts/rename_product.py "Last Orders" lastorders [--env-prefix LASTORDERS] [--dry-run]

Reads the current values from migration_kit/brand.py and rewrites them in every git-tracked
text file (brand.py, pyproject.toml, action.yml, workflows, docs, tests, examples, site/,
and server/: Worker name, D1 database name, product code, email/page copy). It also renames the
output-folder marker files (.<old>-output -> .<new>-output). Files owned by other agents
(PROTECTED) are never touched. Review with `git diff` afterwards, then run the tests.
Env vars change with the prefix (e.g. OLD_LICENCE -> NEW_LICENCE).
"""
import argparse
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SELF = "scripts/rename_product.py"
# Other agents' files: never rewritten, even if tracked.
PROTECTED = ("landing.", "launch/", "launch-backup-prename/", "onboarding.", "client-report-sample.html")


def current():
    src = (ROOT / "migration_kit" / "brand.py").read_text()
    get = lambda k: re.search(rf'^{k} = "([^"]*)"', src, re.M).group(1)
    return get("PRODUCT_NAME"), get("CLI_NAME"), get("ENV_PREFIX")


def tracked() -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [f for f in out.split("\0") if f and f != SELF and not f.startswith(PROTECTED)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("cli", help="lower-case command / PyPI name, e.g. lastorders")
    ap.add_argument("--env-prefix", help="default: CLI upper-cased with - -> _")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if not re.fullmatch(r"[a-z][a-z0-9-]*", a.cli):
        raise SystemExit("cli must be lower-case letters, digits and hyphens")
    prefix = a.env_prefix or a.cli.upper().replace("-", "_")
    old_name, old_cli, old_prefix = current()
    if (old_name, old_cli, old_prefix) == (a.name, a.cli, prefix):
        raise SystemExit("already named that")
    pairs = [(f"{old_prefix}_", f"{prefix}_"), (old_name, a.name), (old_cli, a.cli)]
    changed = 0
    for rel in tracked():
        p = ROOT / rel
        if not p.is_file():
            continue
        try:
            s = p.read_text()
        except (UnicodeDecodeError, OSError):
            continue                      # binary (png, wheel, ...)
        s2 = s.replace(f'ENV_PREFIX = "{old_prefix}"', f'ENV_PREFIX = "{prefix}"')
        for o, n in pairs:
            s2 = s2.replace(o, n)
        if s2 != s:
            changed += 1
            print(f"updated {rel}")
            if not a.dry_run:
                p.write_text(s2)
        if p.name == f".{old_cli}-output":
            print(f"renamed {rel} -> .{a.cli}-output")
            if not a.dry_run:
                subprocess.run(["git", "mv", rel, str(Path(rel).with_name(f".{a.cli}-output"))], cwd=ROOT, check=True)
    print(f"{old_name}/{old_cli}/{old_prefix} -> {a.name}/{a.cli}/{prefix}: {changed} file(s). Now run the tests.")


if __name__ == "__main__":
    main()
