"""Migration packs: provider-neutral data that drives the scanner, fixer and report.

Load order per provider (highest version wins, never downgrades below the bundled copy):
  1. fresh local cache (< CACHE_TTL)            ~/.cache/<cli>/packs/<provider>.json
  2. remote  <PACKS_URL>/index.json -> pack file (sha256-checked, schema-validated)
  3. bundled copy shipped inside the wheel        migration_kit/pack_data/<provider>.json

Remote fetching is skipped with --offline or <PREFIX>_OFFLINE=1. The URL can be
overridden with <PREFIX>_PACKS_URL. This GET (and the licence check in licence.py, key + repo only) are the
ONLY network calls the tool makes to us: no telemetry, no code or prompt upload. Packs are data only; regexes are length-capped
by the schema and compiled here.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import time
import urllib.request
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

from . import brand

PACK_FORMAT = 1
# Planned home for the hosted packs. NOT DEPLOYED YET (see site/ and README).
DEFAULT_PACKS_URL = brand.PACKS_URL
CACHE_TTL = 24 * 3600
FETCH_TIMEOUT = 3
MAX_PACK_BYTES = 2_000_000


def _bundled_dir():
    return resources.files("migration_kit") / "pack_data"


def bundled_providers() -> list[str]:
    return sorted(p.name[:-5] for p in _bundled_dir().iterdir()
                  if p.name.endswith(".json") and p.name != "pack.schema.json")


def schema() -> dict:
    return json.loads((_bundled_dir() / "pack.schema.json").read_text(encoding="utf-8"))


def validate(data: dict) -> None:
    """Raise ValueError if `data` isn't a valid pack."""
    try:
        import jsonschema
    except ImportError:  # pragma: no cover - jsonschema is a declared dependency
        jsonschema = None
    if jsonschema is not None:
        errs = sorted(jsonschema.Draft202012Validator(schema()).iter_errors(data), key=lambda e: list(e.path))
        if errs:
            e = errs[0]
            raise ValueError(f"invalid pack at {'/'.join(map(str, e.path)) or '(root)'}: {e.message}")
    elif data.get("pack_format") != PACK_FORMAT:
        raise ValueError("unsupported pack_format")
    # every regex must compile
    for p in data.get("id_patterns", []):
        re.compile(p["pattern"])
    for s in data.get("signals", []):
        re.compile(s["pattern"])
    if data.get("fine_tune"):
        re.compile(data["fine_tune"]["pattern"])


def _vkey(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in v.split("."))


# ------------------------------------------------------------------ compiled pack
B = r"(?<![A-Za-z0-9._:/-])"
E = r"(?![A-Za-z0-9._:-])"


@dataclass
class Model:
    id: str
    shutdown: str | None
    replacement: str | None
    migration: str | None
    confidence: str
    note: str
    kind: str
    map_automatically: bool
    section: str


@dataclass
class Pack:
    data: dict
    source: str = "bundled"            # bundled | cache | remote
    source_detail: str = ""
    exact: dict = field(default_factory=dict)
    prefixes: list = field(default_factory=list)
    id_res: list = field(default_factory=list)          # (compiled, quoted_only)
    ft_re: re.Pattern | None = None
    signals: list = field(default_factory=list)         # (id, compiled, languages, sdk)

    def __post_init__(self):
        d = self.data
        for m in d.get("models", []):
            mod = Model(m["id"], m.get("shutdown"), m.get("replacement"), m.get("migration"),
                        m.get("confidence", "confirmed"), m.get("note", ""), m.get("kind", "snapshot"),
                        m.get("map_automatically", True), m.get("section", ""))
            if m.get("match") == "prefix":
                self.prefixes.append(mod)
            else:
                self.exact[m["id"]] = mod
        self.prefixes.sort(key=lambda x: len(x.id), reverse=True)
        self.id_res = [(re.compile(B + "(" + p["pattern"] + ")" + E), bool(p.get("quoted_only")))
                       for p in d["id_patterns"]]
        if d.get("fine_tune"):
            self.ft_re = re.compile(d["fine_tune"]["pattern"])
        self.signals = [(s["id"], re.compile(s["pattern"]), set(s.get("languages") or []), s.get("sdk"))
                        for s in d.get("signals", [])]

    # -- accessors
    @property
    def provider(self) -> str:
        return self.data["provider"]

    @property
    def version(self) -> str:
        return self.data["version"]

    @property
    def headline_migrations(self) -> list[dict]:
        return [m for m in self.data.get("migrations", []) if m.get("headline")]

    def migration(self, mid: str | None) -> dict | None:
        return next((m for m in self.data.get("migrations", []) if m["id"] == mid), None)

    @property
    def urgent_days(self) -> int:
        return int((self.data.get("risk_policy") or {}).get("urgent_days", 30))

    def lookup(self, model_id: str) -> Model | None:
        if model_id in self.exact:
            return self.exact[model_id]
        for p in self.prefixes:
            if model_id.startswith(p.id + "-"):
                return Model(model_id, p.shutdown, p.replacement, p.migration, "inferred",
                             f"Matched by family prefix '{p.id}'. {p.note}".strip(), "family",
                             p.map_automatically, p.section)
        return None

    def fine_tune_override(self, base: str) -> dict | None:
        """A fine_tune.bases entry for this base model (exact, or prefix on a '-' boundary), if any."""
        for b in (self.data.get("fine_tune") or {}).get("bases", []):
            if base == b["base"] or (b.get("match") == "prefix" and base.startswith(b["base"] + "-")):
                return b
        return None

    def fine_tune_base(self, model_id: str) -> str | None:
        if not self.ft_re:
            return None
        m = self.ft_re.match(model_id)
        return m.group(self.data["fine_tune"]["base_group"]) if m else None

    def default_mapping(self, migration_ids: list[str] | None = None) -> dict[str, str]:
        """Model -> replacement for automatic swaps (headline migrations by default)."""
        mids = set(migration_ids or [m["id"] for m in self.headline_migrations])
        return {m.id: m.replacement for m in self.exact.values()
                if m.migration in mids and m.replacement and m.map_automatically}

    def info(self) -> dict:
        return {"provider": self.provider, "name": self.data["name"], "version": self.version,
                "status": self.data["status"], "source": self.source, "detail": self.source_detail}


@dataclass
class PackSet:
    packs: list[Pack]

    def __iter__(self):
        return iter(self.packs)

    def get(self, provider: str) -> Pack | None:
        return next((p for p in self.packs if p.provider == provider), None)

    def info(self) -> list[dict]:
        return [p.info() for p in self.packs]


# ------------------------------------------------------------------ loading
def _cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / brand.CACHE_DIR_NAME / "packs"


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": brand.CLI_NAME})
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as r:
        data = r.read(MAX_PACK_BYTES + 1)
    if len(data) > MAX_PACK_BYTES:
        raise ValueError("pack too large")
    return data


def _load_bundled(provider: str) -> dict:
    return json.loads((_bundled_dir() / f"{provider}.json").read_text(encoding="utf-8"))


def _try_cache(provider: str) -> tuple[dict | None, bool]:
    f = _cache_dir() / f"{provider}.json"
    if not f.exists():
        return None, False
    try:
        data = json.loads(f.read_text())
        validate(data)
        fresh = (time.time() - f.stat().st_mtime) < CACHE_TTL
        return data, fresh
    except Exception:  # noqa: BLE001 - a bad cache is just ignored
        return None, False


def _fetch_remote(base: str, providers: list[str]) -> tuple[dict[str, dict], str | None]:
    out: dict[str, dict] = {}
    try:
        index = json.loads(_get(f"{base.rstrip('/')}/index.json"))
    except Exception as e:  # noqa: BLE001
        return out, f"remote unavailable ({type(e).__name__})"
    for entry in index.get("packs", []):
        prov = entry.get("provider")
        if prov not in providers or entry.get("pack_format") != PACK_FORMAT:
            continue
        try:
            url = entry["url"] if "://" in entry["url"] else f"{base.rstrip('/')}/{entry['url'].lstrip('/')}"
            raw = _get(url)
            if entry.get("sha256") and hashlib.sha256(raw).hexdigest() != entry["sha256"]:
                raise ValueError("sha256 mismatch")
            data = json.loads(raw)
            validate(data)
            if data["provider"] != prov:
                raise ValueError("provider mismatch")
            out[prov] = data
            c = _cache_dir()
            c.mkdir(parents=True, exist_ok=True)
            (c / f"{prov}.json").write_bytes(raw)
        except Exception:  # noqa: BLE001 - skip a bad pack, keep the rest
            continue
    return out, None


def load_packs(providers: list[str] | None = None, offline: bool | None = None,
               url: str | None = None, extra_files: list[str] | None = None) -> PackSet:
    """Load packs. `extra_files` loads local pack files (e.g. a pack under development)."""
    providers = providers or bundled_providers()
    if offline is None:
        offline = brand.env("OFFLINE").lower() in ("1", "true", "yes")
    base = url or brand.env("PACKS_URL") or DEFAULT_PACKS_URL
    chosen: dict[str, tuple[dict, str, str]] = {}
    for prov in providers:
        try:
            chosen[prov] = (_load_bundled(prov), "bundled", "")
        except FileNotFoundError:
            pass
    if not offline:
        stale = []
        for prov in list(chosen):
            data, fresh = _try_cache(prov)
            if data and _vkey(data["version"]) > _vkey(chosen[prov][0]["version"]):
                chosen[prov] = (data, "cache", "")
            if not fresh:
                stale.append(prov)
        if stale:
            remote, err = _fetch_remote(base, stale)
            for prov, data in remote.items():
                if _vkey(data["version"]) > _vkey(chosen[prov][0]["version"]):
                    chosen[prov] = (data, "remote", base)
            if err:
                for prov in stale:
                    d, s, _ = chosen[prov]
                    chosen[prov] = (d, s, err)
    for f in extra_files or []:
        data = json.loads(Path(f).read_text())
        validate(data)
        chosen[data["provider"]] = (data, "file", str(f))
    return PackSet([Pack(d, s, det) for d, s, det in (chosen[p] for p in sorted(chosen))])


def build_index(pack_dir: Path, base_path: str = "packs") -> dict:
    """index.json for hosting: provider, version, url (relative), sha256."""
    entries = []
    for f in sorted(Path(pack_dir).glob("*.json")):
        if f.name == "pack.schema.json":
            continue
        raw = f.read_bytes()
        d = json.loads(raw)
        validate(d)
        entries.append({"provider": d["provider"], "name": d["name"], "version": d["version"],
                        "status": d["status"], "pack_format": d["pack_format"],
                        "url": f"{base_path}/{f.name}", "sha256": hashlib.sha256(raw).hexdigest()})
    return {"index_format": 1, "generated": dt.date.today().isoformat(), "packs": entries}
