"""Licence check for the paid features.

Terms (product decision): ONE licence covers ONE GitHub repository, monorepos included
(every sub-folder/package of that repo is covered). The repo is identified from
$GITHUB_REPOSITORY (in Actions), else the git `origin` remote, else $<PREFIX>_REPO, and is
normalised to host/owner/repo. The licence server binds a key to the first repo it is used on.

Free:  scan (always). swap/fix with no licence key print a per-file model-id summary only.
Paid:  the swap/fix patch (diff, plan, simulated verify), swap --apply, fix --apply,
       fix --verify --live, init-evals, eval, report

How the check works
  1. Online: POST {"key", "repo"} to the licence server (only those two fields: no code, prompts,
     file names or telemetry). It answers with a short-lived token (7 days by default) signed with
     Ed25519. The CLI checks the signature against the public key(s) embedded below and caches
     the token under $XDG_CACHE_HOME/<cli>/licence/.
  2. While a cached token is under REFRESH_AFTER old, no request is made at all.
  3. If the server can't be reached, a cached token keeps working until GRACE after it expired.
  4. --offline (or <PREFIX>_OFFLINE=1) never contacts the server: only a cached token (plus grace)
     is accepted. The free scan never touches any of this.
  A definitive "no" from the server (unknown key, revoked/refunded, bound to another repo) clears
  the cache straight away.

This is honest-customer licensing for an open CLI, not DRM.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from . import __version__, brand
from . import messages

ENV_VAR = brand.env_name("LICENCE")
REPO_ENV_VAR = brand.env_name("REPO")
KEY_RE = re.compile(r"^BTM-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$")

# The patch is paid. There is no flag or environment variable that writes it without a licence.
PAID_FEATURES = {"swap-patch": "the model-swap patch", "fix-patch": "the fix patch",
                 "swap-apply": "applying the patch in place", "fix-apply": "applying the fixes in place",
                 "init-evals": "generating a starter eval suite", "eval": "the regression eval", "report": "the client report"}

# Ed25519 public keys (kid -> base64url raw 32-byte key) that may sign licence tokens.
# Generate the pair with `cd server && npm run keys`; the private half goes into the Worker secret
# LICENCE_SIGNING_KEY, the public half is pasted here. Keep old kids here while rotating.
PUBLIC_KEYS: dict[str, str] = {
    "k20261015": "n2qke10mwj6KK8HoIVzWyd4-7GpRGGLV9bYYHTlFiek",
}

TIMEOUT = 5.0                    # seconds for the verify request
REFRESH_AFTER = 24 * 3600        # re-check online once a cached token is a day old (if reachable)
GRACE = 14 * 24 * 3600           # keep working this long after token expiry when the server is unreachable
MAX_RESPONSE = 64 * 1024


class LicenceError(RuntimeError):
    pass


@dataclass
class Licence:
    key: str | None
    valid: bool                  # key has the right shape
    source: str                  # flag | env | none
    repo_id: str | None          # host/owner/repo the licence is used for
    verified: bool = False       # a signed token for this key+repo was checked
    mode: str = ""               # online | cached | grace | offline-cache | offline-grace
    expires: int | None = None   # token exp (unix)
    test: bool = False           # issued from a Stripe test-mode purchase


# ------------------------------------------------------------------ repo identity
def _normalise_remote(url: str) -> str | None:
    url = url.strip()
    m = re.match(r"^(?:git@|ssh://git@)([^:/]+)[:/](.+?)(?:\.git)?/?$", url) or \
        re.match(r"^https?://(?:[^@/]+@)?([^/]+)/(.+?)(?:\.git)?/?$", url)
    return f"{m.group(1).lower()}/{m.group(2).lower()}" if m else None


def _normalise_id(value: str) -> str | None:
    v = value.strip().lower()
    if re.match(r"^[a-z0-9_.-]+/[a-z0-9_.-]+$", v):
        v = f"github.com/{v}"
    return v if re.match(r"^[a-z0-9.-]+/[a-z0-9_.-]+/[a-z0-9_.-]+$", v) else _normalise_remote(value)


def repo_identity(path: str | Path = ".") -> str | None:
    """host/owner/repo for the repository containing `path` (monorepo-safe: any sub-path
    resolves to the same repo). No network access."""
    gh = os.environ.get("GITHUB_REPOSITORY")
    if gh:
        return f"github.com/{gh.lower()}"
    p = Path(path).resolve()
    cwd = p if p.is_dir() else p.parent
    url = ""
    if cwd.exists():
        try:
            url = subprocess.run(["git", "config", "--get", "remote.origin.url"], cwd=cwd, capture_output=True,
                                 text=True, timeout=5).stdout
        except (OSError, subprocess.SubprocessError):
            url = ""
    if url.strip():
        return _normalise_remote(url)
    override = os.environ.get(REPO_ENV_VAR, "")
    return _normalise_id(override) if override else None


def resolve(flag_value: str | None = None, repo_path: str | Path = ".") -> Licence:
    repo = repo_identity(repo_path)
    if flag_value:
        k = flag_value.strip().upper()
        return Licence(k, bool(KEY_RE.match(k)), "flag", repo)
    key = brand.env("LICENCE").strip().upper()
    if key:
        return Licence(key, bool(KEY_RE.match(key)), "env", repo)
    return Licence(None, False, "none", repo)


# ------------------------------------------------------------------ tokens
def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _key_hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[:32]


def _dev_keys() -> dict[str, str]:
    """Extra public keys for testing against a local `wrangler dev` server only."""
    raw = brand.env("LICENCE_DEV_PUBLIC_KEYS")
    host = urllib.parse.urlparse(licence_url()).hostname or ""
    if raw and host in ("localhost", "127.0.0.1", "::1"):
        try:
            return {str(k): str(v) for k, v in json.loads(raw).items()}
        except (ValueError, AttributeError):
            return {}
    return {}


def verify_token(token: str, key: str, repo: str) -> dict | None:
    """Claims if `token` is a genuine, untampered token for this key+repo (expiry NOT checked here)."""
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError as e:   # pragma: no cover - dependency of the package
        raise LicenceError("the `cryptography` package is needed for licence checks (pip install cryptography)") from e
    try:
        v, body, sig = token.split(".")
        if v != "v1":
            return None
        claims = json.loads(_b64d(body))
        pub = {**PUBLIC_KEYS, **_dev_keys()}.get(claims.get("kid", ""))
        if not pub:
            return None
        Ed25519PublicKey.from_public_bytes(_b64d(pub)).verify(_b64d(sig), f"v1.{body}".encode())
    except (ValueError, TypeError, InvalidSignature, json.JSONDecodeError):
        return None
    if claims.get("v") != 1 or claims.get("repo") != repo or claims.get("lic") != _key_hash(key):
        return None
    if not isinstance(claims.get("exp"), int) or not isinstance(claims.get("iat"), int):
        return None
    return claims


# ------------------------------------------------------------------ cache
def _cache_file(key: str, repo: str) -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    name = hashlib.sha256(f"{key}\n{repo}".encode()).hexdigest()[:24]
    return Path(base) / brand.CACHE_DIR_NAME / "licence" / f"{name}.json"


def _load_cached(key: str, repo: str) -> tuple[str, dict] | None:
    f = _cache_file(key, repo)
    try:
        token = json.loads(f.read_text())["token"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    claims = verify_token(token, key, repo)
    return (token, claims) if claims else None


def _save(key: str, repo: str, token: str) -> None:
    f = _cache_file(key, repo)
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps({"token": token, "saved_at": int(time.time())}))
        os.chmod(tmp, 0o600)
        tmp.replace(f)
    except OSError:
        pass   # a read-only cache just means checking online next time


def clear_cache(key: str, repo: str) -> None:
    try:
        _cache_file(key, repo).unlink()
    except OSError:
        pass


# ------------------------------------------------------------------ network
def licence_url() -> str:
    return brand.env("LICENCE_URL") or brand.LICENCE_URL


class _Unreachable(Exception):
    pass


def _http_post(url: str, payload: dict) -> tuple[int, dict]:
    """POST JSON; returns (status, body). Raises _Unreachable for network errors and 5xx."""
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": f"{brand.CLI_NAME}/{__version__}"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, json.loads(r.read(MAX_RESPONSE) or b"{}")
    except urllib.error.HTTPError as e:
        if e.code >= 500 or e.code == 429:
            raise _Unreachable(f"licence server returned {e.code}") from e
        try:
            body = json.loads(e.read(MAX_RESPONSE) or b"{}")
        except ValueError:
            body = {}
        return e.code, body
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise _Unreachable(str(getattr(e, "reason", e))) from e


_transport = _http_post   # tests replace this


def _online(key: str, repo: str) -> dict:
    url = licence_url()
    if not url:
        raise _Unreachable("no licence server configured in this build")
    status, body = _transport(url, {"key": key, "repo": repo})
    if status == 200 and body.get("status") == "ok" and body.get("token"):
        claims = verify_token(body["token"], key, repo)
        if not claims:
            if not (PUBLIC_KEYS or _dev_keys()):
                raise _Unreachable("this build has no licence public key embedded (release step: docs/LICENCE-SERVER.md)")
            raise _Unreachable("licence server answered with a token this CLI can't verify (update the CLI?)")
        _save(key, repo, body["token"])
        return claims
    clear_cache(key, repo)
    code = body.get("status") or f"http_{status}"
    msg = body.get("error") or "licence rejected"
    if code == "bound_to_other_repo":
        raise LicenceError(f"This licence is already bound to {body.get('bound_repo', 'another repo')}; one licence covers one repo "
                           f"(monorepos included). To move it, reply to your licence email. Buy another: {brand.BUY_URL}")
    if code == "revoked":
        raise LicenceError(f"This licence has been revoked ({msg}). Licences: {brand.BUY_URL}")
    if code == "not_found":
        raise LicenceError(f"Licence key not recognised. Check it against your licence email. Licences: {brand.BUY_URL}")
    raise LicenceError(f"Licence check failed: {msg} ({code}).")


def buy_url(repo: str | None = None) -> str:
    return brand.BUY_URL + (f"?repo={urllib.parse.quote(repo, safe='/')}" if repo else "")


# ------------------------------------------------------------------ public API
def _offline_requested(offline: bool | None) -> bool:
    if offline is not None:
        return bool(offline)
    return brand.env("OFFLINE").lower() in ("1", "true", "yes")


def check(lic: Licence, offline: bool | None = None, now: float | None = None) -> Licence:
    """Verify a well-formed key for lic.repo_id. Raises LicenceError if it can't be confirmed."""
    now = time.time() if now is None else now
    key, repo = lic.key, lic.repo_id
    cached = _load_cached(key, repo)
    claims = cached[1] if cached else None

    def done(c: dict, mode: str) -> Licence:
        lic.verified, lic.mode, lic.expires, lic.test = True, mode, c["exp"], bool(c.get("test"))
        return lic

    if _offline_requested(offline):
        if claims and now < claims["exp"]:
            return done(claims, "offline-cache")
        if claims and now < claims["exp"] + GRACE:
            return done(claims, "offline-grace")
        why = "the cached verification has run out" if claims else "there's no cached verification for this repo yet"
        raise LicenceError(f"--offline: {why}. Run once with network access (it sends only the key and the repo name), "
                           f"then offline use works for {int(GRACE / 86400)} days after the token expires.")

    if claims and now < claims["exp"] and now - claims["iat"] < REFRESH_AFTER:
        return done(claims, "cached")
    try:
        return done(_online(key, repo), "online")
    except _Unreachable as e:
        if claims and now < claims["exp"]:
            return done(claims, "cached")
        if claims and now < claims["exp"] + GRACE:
            return done(claims, "grace")
        raise LicenceError(f"Couldn't reach the licence server ({e}) and there's no recent verification cached for "
                           f"{repo}. Try again when online.") from e


def require(feature: str, flag_value: str | None = None, repo_path: str | Path = ".",
            offline: bool | None = None) -> Licence:
    lic = resolve(flag_value, repo_path)
    what = PAID_FEATURES.get(feature, feature)
    if not lic.valid:
        why = "no licence key found" if lic.source == "none" else "licence key format not recognised"
        raise LicenceError(
            f"{what.capitalize()} needs a {brand.PRODUCT_NAME} licence ({why}). One licence covers one GitHub repo "
            f"(monorepos included). Set {ENV_VAR}=BTM-XXXX-XXXX-XXXX or pass --licence. "
            + messages.NEEDS_LICENCE_TAIL)
    if not lic.repo_id:
        raise LicenceError(
            f"{what.capitalize()} needs to know which repo this licence is for, and there's no git `origin` remote or "
            f"$GITHUB_REPOSITORY here. Add the remote, or set {REPO_ENV_VAR}=github.com/<owner>/<repo>.")
    check(lic, offline=offline)
    return lic


def describe(lic: Licence) -> str:
    when = time.strftime("%Y-%m-%d", time.gmtime(lic.expires)) if lic.expires else "?"
    mode = {"online": f"verified online, token valid to {when}", "cached": f"verified (cached until {when})",
            "grace": f"licence server unreachable; offline grace (token expired {when})",
            "offline-cache": f"--offline: cached verification valid to {when}",
            "offline-grace": f"--offline: in grace period (token expired {when})"}.get(lic.mode, "not verified")
    test = " [TEST-MODE licence]" if lic.test else ""
    return f"licence {(lic.key or '')[:8]}... for {lic.repo_id}: {mode}{test}"
