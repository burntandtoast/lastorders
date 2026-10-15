"""PLACEHOLDER licence check.

!!! NOT real licensing. It only checks the *shape* of a key so paid features can be
!!! gated now and wired to Stripe later.

Terms (product decision): ONE licence covers ONE GitHub repository, including monorepos
(every sub-folder/package of that repo is covered). The repo is identified from
$GITHUB_REPOSITORY (in Actions) or the git `origin` remote, normalised to host/owner/repo.

Free:  scan (always), swap without --apply (writes a reviewable .diff)
Paid:  swap --apply, init-evals, eval, report

Phase 2: if brand.LICENCE_URL is set, POST {key, repo_id, version} to it and cache the
signed answer. That request and the pack download are the ONLY network calls to us; no
telemetry, no code or prompts are ever sent. Nothing is sent while LICENCE_URL is empty.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import brand

ENV_VAR = brand.env_name("LICENCE")
KEY_RE = re.compile(r"^BTM-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$")
# Pricing ladder says the licence unlocks the patch too. Flip to True to gate the
# .diff from `swap` as well (phase-1 brief gates only `swap --apply`).
GATE_SWAP_PATCH = False

GATE_FIX_PATCH = GATE_SWAP_PATCH   # same policy for the fixer's patch: previewing it is free

PAID_FEATURES = {"swap-apply": "applying the patch in place", "fix-apply": "applying the automatic fixes in place", "init-evals": "generating a starter eval suite",
                 "eval": "the regression eval", "report": "the client report"}


class LicenceError(RuntimeError):
    pass


@dataclass
class Licence:
    key: str | None
    valid: bool
    source: str          # flag | env | none
    repo_id: str | None  # host/owner/repo the licence is used for
    verified: bool = False  # True only once a real licence server confirms (phase 2)


def _normalise_remote(url: str) -> str | None:
    url = url.strip()
    m = re.match(r"^(?:git@|ssh://git@)([^:/]+)[:/](.+?)(?:\.git)?/?$", url) or \
        re.match(r"^https?://(?:[^@/]+@)?([^/]+)/(.+?)(?:\.git)?/?$", url)
    return f"{m.group(1).lower()}/{m.group(2).lower()}" if m else None


def repo_identity(path: str | Path = ".") -> str | None:
    """host/owner/repo for the repository containing `path` (monorepo-safe: any sub-path
    resolves to the same repo). No network access."""
    import os
    gh = os.environ.get("GITHUB_REPOSITORY")
    if gh:
        return f"github.com/{gh.lower()}"
    p = Path(path).resolve()
    cwd = p if p.is_dir() else p.parent
    try:
        url = subprocess.run(["git", "config", "--get", "remote.origin.url"], cwd=cwd, capture_output=True,
                             text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return _normalise_remote(url) if url.strip() else None


def resolve(flag_value: str | None = None, repo_path: str | Path = ".") -> Licence:
    repo = repo_identity(repo_path)
    if flag_value:
        return Licence(flag_value, bool(KEY_RE.match(flag_value.strip())), "flag", repo)
    key = brand.env("LICENCE").strip()
    if key:
        return Licence(key, bool(KEY_RE.match(key)), "env", repo)
    return Licence(None, False, "none", repo)


def require(feature: str, flag_value: str | None = None, repo_path: str | Path = ".") -> Licence:
    lic = resolve(flag_value, repo_path)
    if not lic.valid:
        what = PAID_FEATURES.get(feature, feature)
        why = "no licence key found" if lic.source == "none" else "licence key format not recognised"
        raise LicenceError(
            f"{what.capitalize()} needs a {brand.PRODUCT_NAME} licence ({why}). One licence covers one GitHub repo "
            f"(monorepos included). Set {ENV_VAR}=BTM-XXXX-XXXX-XXXX or pass --licence. "
            f"The free `scan` needs no licence. Licences: {brand.BUY_URL}")
    # PLACEHOLDER: a real check would bind lic.key to lic.repo_id via brand.LICENCE_URL.
    return lic


def describe(lic: Licence) -> str:
    repo = lic.repo_id or "unknown repo (no git origin / GITHUB_REPOSITORY)"
    return f"licence {lic.key[:8]}... for {repo} [placeholder check, not verified]"
