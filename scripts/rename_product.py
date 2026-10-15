#!/usr/bin/env python3
"""Rename the product in one go (name still undecided: Last Orders / Sunsetter / ModelMove).

    python scripts/rename_product.py "Sunsetter" sunsetter [--env-prefix SUNSETTER]

Reads the current values from migration_kit/brand.py and rewrites them everywhere they
appear statically: brand.py, pyproject.toml (dist name + console script), action.yml,
workflows, README/CHANGELOG/docs, tests. Review with `git diff` afterwards.
Env vars change with the prefix (e.g. MODELMIGRATE_LICENCE -> SUNSETTER_LICENCE).
"""
import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = ["migration_kit/brand.py", "pyproject.toml", "action.yml", ".github/workflows/ci.yml",
         "examples/workflows/model-scan.yml", "README.md", "CHANGELOG.md", "tests/conftest.py",
         "tests/test_product.py", *[str(p.relative_to(ROOT)) for p in (ROOT / "docs").glob("*.md")]]


def current():
    src = (ROOT / "migration_kit" / "brand.py").read_text()
    get = lambda k: re.search(rf'^{k} = "([^"]*)"', src, re.M).group(1)
    return get("PRODUCT_NAME"), get("CLI_NAME"), get("ENV_PREFIX")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("cli", help="lower-case command / PyPI name, e.g. sunsetter or last-orders")
    ap.add_argument("--env-prefix", help="default: CLI upper-cased with - -> _")
    a = ap.parse_args()
    if not re.fullmatch(r"[a-z][a-z0-9-]*", a.cli):
        raise SystemExit("cli must be lower-case letters, digits and hyphens")
    prefix = a.env_prefix or a.cli.upper().replace("-", "_")
    old_name, old_cli, old_prefix = current()
    pairs = [(f"{old_prefix}_", f"{prefix}_"), (old_name, a.name), (old_cli, a.cli)]
    for rel in dict.fromkeys(FILES):
        p = ROOT / rel
        if not p.exists():
            continue
        s = p.read_text()
        s2 = s.replace(f'ENV_PREFIX = "{old_prefix}"', f'ENV_PREFIX = "{prefix}"')
        for o, n in pairs:
            s2 = s2.replace(o, n)
        if s2 != s:
            p.write_text(s2)
            print(f"updated {rel}")
    print(f"{old_name}/{old_cli}/{old_prefix} -> {a.name}/{a.cli}/{prefix}. Now run the tests.")


if __name__ == "__main__":
    main()
