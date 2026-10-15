"""Build the static folder that hosts migration packs (Vercel or Cloudflare Pages)."""
from __future__ import annotations

import json
import shutil
from importlib import resources
from pathlib import Path

from . import brand
from .packs import build_index, bundled_providers

INDEX_HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>__PRODUCT__ migration packs</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{font-family:system-ui,sans-serif;max-width:760px;margin:3rem auto;padding:0 1rem;line-height:1.5}code{background:#f3f3f3;padding:0 .3rem}</style>
</head><body><h1>__PRODUCT__ migration packs</h1>
<p>Machine-readable data about retiring AI models (IDs, shutdown dates, replacements, parameter rules) used by
<code>__CLI__</code>, the free model-retirement scanner from Burnt &amp; Toast Studios.</p>
<ul><li><a href="v1/index.json">v1/index.json</a> (list of packs with versions and SHA-256)</li>
<li><a href="v1/pack.schema.json">v1/pack.schema.json</a> (JSON Schema for the pack format)</li>
__PACKS__</ul><p>Data is checked against the providers' documentation on the date in each pack. Always re-verify before acting.</p>
</body></html>"""

VERCEL = {
    "cleanUrls": False,
    "headers": [
        {"source": "/v1/(.*)", "headers": [
            {"key": "Access-Control-Allow-Origin", "value": "*"},
            {"key": "Cache-Control", "value": "public, max-age=300, s-maxage=3600, stale-while-revalidate=86400"},
            {"key": "Content-Type", "value": "application/json; charset=utf-8"},
            {"key": "X-Content-Type-Options", "value": "nosniff"}]}],
}

CF_HEADERS = """/v1/*
  Access-Control-Allow-Origin: *
  Cache-Control: public, max-age=300, s-maxage=3600, stale-while-revalidate=86400
  Content-Type: application/json; charset=utf-8
  X-Content-Type-Options: nosniff
"""


def build_site(out: Path) -> Path:
    out = Path(out)
    v1 = out / "v1"
    if v1.exists():
        shutil.rmtree(v1)
    (v1 / "packs").mkdir(parents=True)
    src = resources.files("migration_kit") / "pack_data"
    for prov in bundled_providers():
        (v1 / "packs" / f"{prov}.json").write_bytes((src / f"{prov}.json").read_bytes())
    (v1 / "pack.schema.json").write_bytes((src / "pack.schema.json").read_bytes())
    index = build_index(v1 / "packs", base_path="packs")
    (v1 / "index.json").write_text(json.dumps(index, indent=2))
    items = "".join(f'<li><a href="v1/{e["url"]}">{e["name"]}</a> v{e["version"]} ({e["status"]})</li>' for e in index["packs"])
    (out / "index.html").write_text(INDEX_HTML.replace("__PACKS__", items)
                                    .replace("__PRODUCT__", brand.PRODUCT_NAME).replace("__CLI__", brand.CLI_NAME))
    (out / "vercel.json").write_text(json.dumps(VERCEL, indent=2))
    (out / "_headers").write_text(CF_HEADERS)
    # Cloudflare Workers static assets (server/wrangler.toml) must not publish the Vercel config.
    (out / ".assetsignore").write_text("vercel.json\n")
    return out
