"""Client-facing report (Markdown + self-contained HTML). Generic: all provider facts,
deadlines and advice come from the migration packs."""
from __future__ import annotations

import datetime as dt
import html
import json
from pathlib import Path

from . import brand
from .packs import PackSet, load_packs
from .scanner import CAT_LABEL

RISK_ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}


def _cost_line(ev: dict) -> str:
    u = ev.get("usage") or {}
    parts = []
    for side in ("old", "new"):
        r = u.get(side)
        if r:
            c = f" (~${r['est_cost_usd']:.4f})" if "est_cost_usd" in r else ""
            parts.append(f"{r['model']}: {r['input_tokens']} in / {r['output_tokens']} out tokens{c}")
    return ("Tokens: " + "; ".join(parts) + ".") if parts else ""


def _explain(c: dict) -> str:
    ch = c["checks"]
    parts = []
    if "schema_valid" in ch and not ch["schema_valid"]["new"]:
        parts.append("new model output failed the schema: " + "; ".join(ch["schema_errors"]["new"][:2]))
    if ch.get("field_diff"):
        parts.append("fields differ: " + ", ".join(f"{d['path']} ({d['change']})" for d in ch["field_diff"][:4]))
    if "tool_names" in ch and not ch["tool_names"]["match"]:
        parts.append(f"called {ch['tool_names']['new']} instead of {ch['tool_names']['old']}")
    for d in ch.get("argument_diff", []):
        parts.append(f"{d['tool']} args: " + ", ".join(
            f"{x['path']} {json.dumps(x.get('old'))} -> {json.dumps(x.get('new'))}" for x in d["diff"][:3]))
    if ch.get("errors", {}).get("new"):
        parts.append("; ".join(ch["errors"]["new"][:2]))
    if "similarity" in ch and c["type"] == "text":
        parts.append(f"text similarity {ch['similarity']}")
    if ch.get("missing_phrases"):
        parts.append(f"missing {ch['missing_phrases']}")
    return ("; ".join(parts) or "no material difference").replace("|", "/")



class Ctx:
    """Everything the templates need, derived from the scan + packs."""

    def __init__(self, client, scan, swap, diff, ev, today, label, packs: PackSet, fix=None, fix_verify=None):
        self.client, self.scan, self.swap, self.diff, self.ev, self.today, self.label = client, scan, swap, diff, ev, today, label
        self.fix, self.fix_verify = fix, fix_verify
        self.s = scan["summary"]
        self.findings = sorted(scan["findings"], key=lambda f: (RISK_ORDER.get(f["risk"], 9), f["file"], f["line"]))
        used = {f["provider"] for f in scan["findings"]}
        self.packs = [p for p in packs if p.provider in used] or list(packs)
        heads = []
        for p in self.packs:
            if any(f["provider"] == p.provider and f["category"] in ("in_scope", "fine_tune") for f in scan["findings"]):
                hit = {f.get("migration") for f in scan["findings"] if f["provider"] == p.provider}
                ms = [m for m in p.headline_migrations if m["id"] in hit] or p.headline_migrations
                heads += [(m["shutdown"], m["title"], p) for m in ms]
        self.deadlines = sorted(heads, key=lambda h: h[0])
        self.deadline = self.deadlines[0] if heads else None

    def days(self, d):
        return (dt.date.fromisoformat(d[0]) - self.today).days

    @property
    def days_left(self):
        return self.days(self.deadline) if self.deadline else None

    def ft(self):
        return [f for f in self.findings if f["category"] == "fine_tune"]

    def ft_advice(self, provider):
        p = next((p for p in self.packs if p.provider == provider), None)
        return ((p.data.get("report") or {}).get("fine_tune_advice") or []) if p else []

    def next_steps(self):
        steps = []
        for p in self.packs:
            for st in (p.data.get("report") or {}).get("next_steps", []):
                steps.append((p, st))
        return steps


FIX_LABEL = {"fixed": "Fixed in the patch", "fixed-coupled": "Fixed; ship with the model switch",
             "manual": "Needs a decision", "info": "Info"}


def _fix_glance(c: Ctx) -> str | None:
    if not c.fix:
        return None
    n = c.fix["summary"]["items"]
    txt = (f"{n.get('fixed', 0)} code fixes in the patch, {n.get('fixed-coupled', 0)} that must ship with the model switch, "
           f"{n.get('manual', 0)} items that need a decision")
    v = c.fix_verify
    if v:
        txt += f"; verification **{'PASS' if v['ok'] else 'FAIL'}** ({'live API' if v['live'] else 'mock'})"
    return txt


def _verify_lines(v: dict) -> list[str]:
    s = v["steps"]
    out = [f"Patch applies cleanly: {'yes' if s['patch_applies'] else 'NO'}. Changed files parse: "
           f"{'yes' if s['syntax']['ok'] else 'NO'}. Re-running the fixer changes nothing: {'yes' if s['idempotent']['ok'] else 'NO'}."]
    for run in s["eval"]["runs"]:
        a = run["acceptance"]
        exp = sum(1 for e in a["new_errors"] if e.get("expected"))
        out.append(f"{run['api']}: {a['cases']} fixed call(s) replayed old vs new ({'live' if v['live'] else 'mock'}); "
                   f"new model rejected {len(a['new_errors'])}" + (f" ({exp} expected: open decision items)" if exp else "") + ".")
    ctrl = s.get("control") or []
    if ctrl:
        out.append(f"Control: {sum(c['rejected'] for c in ctrl)} of {len(ctrl)} calls are rejected by the new model "
                   "without the fix, so these fixes are required, not cosmetic.")
    return out


def build_markdown(c: Ctx) -> str:
    s = c.s
    o = [f"# Model migration report: {c.client}", "", f"Prepared by Burnt & Toast Studios on {c.today:%d %B %Y}.", ""]
    if c.label:
        o += [f"> **{c.label}**", ""]
    o += ["## At a glance", ""]
    for d in c.deadlines:
        o.append(f"- **Deadline:** {d[1]}: **{dt.date.fromisoformat(d[0]):%d %B %Y}** "
                 f"({c.days(d)} days from this report).")
    o += [f"- **Model references found:** {s['total_findings']} across {s['files_with_findings']} files "
          f"({c.scan['files_scanned']} files scanned).",
          f"- **High risk:** {s['by_risk'].get('high', 0)} | **Medium:** {s['by_risk'].get('medium', 0)} | "
          f"**Low:** {s['by_risk'].get('low', 0)} | **Info:** {s['by_risk'].get('info', 0)}",
          f"- **Providers:** " + ", ".join(f"{k} ({v})" for k, v in sorted(s.get("by_provider", {}).items())),
          f"- **Fine-tuned models:** {len(s['fine_tuned_models'])} (need a separate decision)"]
    if s["env_var_model_refs"]:
        o.append("- **Models set by environment variable:** " + ", ".join(f"`{v}`" for v in s["env_var_model_refs"])
                 + " (check the live values on your servers)")
    if c.fix:
        fs = c.fix["summary"]
        o.append(f"- **Proposed patch:** {fs['files_changed']} files, {fs['model_id_replacements']} model ID replacements "
                 "plus the code fixes below")
    elif c.swap:
        o.append(f"- **Proposed patch:** {c.swap['replacements']} replacements in {c.swap['files_changed']} files, "
                 f"{len(c.swap['skipped_fine_tunes'])} fine-tuned references left untouched")
    if _fix_glance(c):
        o.append(f"- **Automatic fixes:** {_fix_glance(c)}")
    if c.ev:
        o.append(f"- **Regression eval ({c.ev['mode']}):** " + ", ".join(f"{v} {k}" for k, v in sorted(c.ev["summary"].items())))
    for p in c.packs:
        f = p.data.get("facts") or {}
        srcs = ", ".join(f"[{x.get('title', x['url'])}]({x['url']})" for x in p.data["sources"] if "://" in x["url"])
        o += ["", f"## {p.data['name']}: what's confirmed", "",
              f"Migration pack `{p.provider}` v{p.version} ({p.data['status']}). Sources: {srcs}.", ""]
        o += [f"- {x}" for x in f.get("confirmed", [])]
        if f.get("live"):
            o += ["", f"**Confirmed by our own live API checks ({f.get('live_checked_on', '')}):**", ""] + [f"- {x}" for x in f["live"]]
        if f.get("unconfirmed"):
            o += ["", "**Not confirmed:**", ""] + [f"- {x}" for x in f["unconfirmed"]]
    o += ["", "## Findings", "", "| Risk | File | Line | Current model | Suggested | Category | Notes |", "|---|---|---|---|---|---|---|"]
    for f in c.findings:
        sug = f"`{f['suggested']}`" if f["suggested"] else "decision needed"
        if f["confidence"] == "inferred" and f["suggested"]:
            sug += " (inferred)"
        notes = "<br>".join(n.replace("|", "\\|") for n in f["notes"])
        o.append(f"| **{f['risk']}** | `{f['file']}` | {f['line']} | `{f['model']}` | {sug} | {CAT_LABEL[f['category']]} | {notes} |")
    if c.ft():
        o += ["", "## Fine-tuned models", "", "These can't be swapped automatically. For each one, choose to:", ""]
        for prov in sorted({f["provider"] for f in c.ft()}):
            o += [f"{i}. {a}" for i, a in enumerate(c.ft_advice(prov), 1)]
        o.append("")
        o += [f"- `{f['model']}` in `{f['file']}` line {f['line']}" for f in c.ft()]
    if c.fix:
        o += ["", "## Automatic fixes", "",
              "Generated from the migration-pack rules for each API call (not from text search).", ""]
        o += ["| Status | File | Rule | Change | Why |", "|---|---|---|---|---|"]
        for i in c.fix["items"]:
            if i["status"] == "info":
                continue
            why = (i["message"] + " " + " ".join(n for n in i.get("notes", []) if n)).strip().replace("|", "/")
            o.append(f"| **{FIX_LABEL.get(i['status'], i['status'])}** | `{i['file']}:{i['line']}` | {i['rule']} | "
                     f"{(i['change'] or '').replace('|', '/')} | {why} |")
        if c.fix_verify:
            o += ["", "**Verification:**", ""] + [f"- {x}" for x in _verify_lines(c.fix_verify)]
    if c.diff is not None:
        o += ["", "## Proposed code change", "", "Nothing has been changed in your repository. This is the patch for review:",
              "", "```diff", c.diff.strip(), "```"]
    if c.ev:
        ev = c.ev
        o += ["", f"## Regression eval: `{ev['old_model']}` vs `{ev['new_model']}`", ""]
        if ev["mode"] == "mock":
            o += ["> **Demo run.** These results use simulated outputs to show the format. A real engagement runs the "
                  "same suite against both models with the client's API key.", ""]
        else:
            o += [f"> **Live run** against the provider API ({ev['api']} endpoint), {ev['run_at']}. {_cost_line(ev)} "
                  "DRIFT means the new model's output differs and needs a human look; it is not automatically a failure.", ""]
        o += ["| Case | Type | Status | What changed |", "|---|---|---|---|"]
        o += [f"| `{x['id']}` | {x['type']} | **{x['status'].upper()}** | {_explain(x)} |" for x in ev["cases"]]
    steps = c.next_steps()
    if steps:
        o += ["", "## Next steps", ""] + [f"{i}. {st}" for i, (_p, st) in enumerate(steps, 1)]
    o += ["", f"_Migration packs: " + ", ".join(f"{p.provider} v{p.version}" for p in c.packs) + "._", ""]
    return "\n".join(o)


CSS = """
body{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1.25rem;color:#222;line-height:1.5}
header{border-bottom:4px solid #c8642a;padding-bottom:.75rem;margin-bottom:1.5rem}
header .brand{color:#c8642a;font-weight:700;letter-spacing:.04em;text-transform:uppercase;font-size:.85rem}
h1{margin:.2rem 0}h2{margin-top:2.2rem;border-bottom:1px solid #eee;padding-bottom:.3rem}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:.75rem}
.card{border:1px solid #e5e5e5;border-radius:8px;padding:.8rem 1rem;background:#fafafa}
.card .n{font-size:1.8rem;font-weight:700}.card .l{font-size:.85rem;color:#555}
table{border-collapse:collapse;width:100%;font-size:.88rem}th,td{border:1px solid #e3e3e3;padding:.45rem .55rem;vertical-align:top;text-align:left}
th{background:#f4f1ee}code{background:#f3f3f3;padding:.05rem .3rem;border-radius:3px;font-size:.85em}
.risk{font-weight:700;padding:.1rem .45rem;border-radius:4px;font-size:.8rem;text-transform:uppercase}
.high{background:#fde2e1;color:#a11}.medium{background:#fff1d6;color:#8a5a00}.low{background:#e8f2ff;color:#1c4f8f}.info{background:#eee;color:#555}
.pass{background:#e2f5e6;color:#17642a}.drift{background:#fff1d6;color:#8a5a00}.fail,.error{background:#fde2e1;color:#a11}.improved{background:#e8f2ff;color:#1c4f8f}
.banner{background:#e8f2ff;border-left-color:#1c4f8f;font-size:1.05rem}
.note{background:#fff8e6;border-left:4px solid #e0a800;padding:.6rem .9rem;margin:1rem 0}
pre.diff{background:#1e1e1e;color:#ddd;padding:1rem;overflow:auto;font-size:.8rem;border-radius:6px}
pre.diff .add{color:#7ee787}pre.diff .del{color:#ff7b72}pre.diff .hdr{color:#79c0ff}
footer{margin-top:3rem;color:#777;font-size:.8rem;border-top:1px solid #eee;padding-top:.75rem}
"""


def _e(x) -> str:
    return html.escape(str(x))


def build_html(c: Ctx) -> str:
    s = c.s
    h = ["<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
         f"<title>Model migration report - {_e(c.client)}</title><style>{CSS}</style></head><body>",
         f"<header><div class='brand'>Burnt &amp; Toast Studios</div><h1>Model migration report</h1>"
         f"<div>{_e(c.client)} &middot; {c.today:%d %B %Y}</div></header>"]
    if c.label:
        h.append(f"<div class='note banner'><strong>{_e(c.label)}</strong></div>")
    h.append("<h2>At a glance</h2><div class='cards'>")
    for d in c.deadlines:
        h.append(f"<div class='card'><div class='n'>{c.days(d)}</div><div class='l'>days until "
                 f"{dt.date.fromisoformat(d[0]):%d %b %Y}: {_e(d[1])}</div></div>")
    h += [f"<div class='card'><div class='n'>{s['total_findings']}</div><div class='l'>model references in {s['files_with_findings']} files</div></div>",
          f"<div class='card'><div class='n'>{s['by_risk'].get('high', 0)}</div><div class='l'>high-risk findings</div></div>",
          f"<div class='card'><div class='n'>{len(s['fine_tuned_models'])}</div><div class='l'>fine-tuned models needing a decision</div></div>"]
    if c.fix:
        n = c.fix["summary"]["items"]
        h.append(f"<div class='card'><div class='n'>{n.get('fixed', 0) + n.get('fixed-coupled', 0)}</div><div class='l'>code fixes in the patch"
                 + (f" (verified: {'PASS' if c.fix_verify['ok'] else 'FAIL'})" if c.fix_verify else "") + "</div></div>")
        h.append(f"<div class='card'><div class='n'>{n.get('manual', 0)}</div><div class='l'>items needing a decision</div></div>")
    if c.ev:
        ok = c.ev["summary"].get("pass", 0) + c.ev["summary"].get("improved", 0)
        h.append(f"<div class='card'><div class='n'>{ok}/{len(c.ev['cases'])}</div><div class='l'>eval cases passing"
                 f"{' (demo)' if c.ev['mode'] == 'mock' else ''}</div></div>")
    h.append("</div>")
    if s["env_var_model_refs"]:
        h.append("<div class='note'>Some models are chosen by environment variable ("
                 + ", ".join(f"<code>{_e(v)}</code>" for v in s["env_var_model_refs"])
                 + "). Their live values are set outside the code and must be checked on your servers.</div>")
    for p in c.packs:
        f = p.data.get("facts") or {}
        srcs = ", ".join(f"<a href='{_e(x['url'])}'>{_e(x.get('title', x['url']))}</a>" for x in p.data["sources"] if "://" in x["url"])
        h.append(f"<h2>{_e(p.data['name'])}: what's confirmed</h2><p>Migration pack <code>{_e(p.provider)}</code> v{_e(p.version)} "
                 f"({_e(p.data['status'])}). Sources: {srcs}.</p><ul>" + "".join(f"<li>{_e(x)}</li>" for x in f.get("confirmed", [])) + "</ul>")
        if f.get("live"):
            h.append(f"<h3>Confirmed by our own live API checks ({_e(f.get('live_checked_on', ''))})</h3><ul>"
                     + "".join(f"<li>{_e(x)}</li>" for x in f["live"]) + "</ul>")
        if f.get("unconfirmed"):
            h.append("<h3>Not confirmed</h3><ul>" + "".join(f"<li>{_e(x)}</li>" for x in f["unconfirmed"]) + "</ul>")
    h.append("<h2>Findings</h2><table><tr><th>Risk</th><th>File</th><th>Line</th><th>Current model</th>"
             "<th>Suggested</th><th>Category</th><th>Notes</th></tr>")
    for f in c.findings:
        sug = f"<code>{_e(f['suggested'])}</code>" if f["suggested"] else "<em>decision needed</em>"
        if f["confidence"] == "inferred" and f["suggested"]:
            sug += " <small>(inferred)</small>"
        h.append(f"<tr><td><span class='risk {f['risk']}'>{f['risk']}</span></td><td><code>{_e(f['file'])}</code></td>"
                 f"<td>{f['line']}</td><td><code>{_e(f['model'])}</code></td><td>{sug}</td>"
                 f"<td>{_e(CAT_LABEL[f['category']])}</td><td>{'<br>'.join(_e(n) for n in f['notes'])}</td></tr>")
    h.append("</table>")
    if c.ft():
        adv = []
        for prov in sorted({f["provider"] for f in c.ft()}):
            adv += c.ft_advice(prov)
        h.append("<h2>Fine-tuned models</h2><p>These can't be swapped automatically. For each one, choose to:</p><ol>"
                 + "".join(f"<li>{_e(a)}</li>" for a in adv) + "</ol><ul>"
                 + "".join(f"<li><code>{_e(f['model'])}</code> in <code>{_e(f['file'])}</code> line {f['line']}</li>" for f in c.ft())
                 + "</ul>")
    if c.fix:
        h.append("<h2>Automatic fixes</h2><p>Generated from the migration-pack rules for each API call (not from text search).</p>"
                 "<table><tr><th>Status</th><th>File</th><th>Rule</th><th>Change</th><th>Why</th></tr>")
        cls = {"fixed": "pass", "fixed-coupled": "drift", "manual": "fail"}
        for i in c.fix["items"]:
            if i["status"] == "info":
                continue
            why = (i["message"] + " " + " ".join(n for n in i.get("notes", []) if n)).strip()
            h.append(f"<tr><td><span class='risk {cls.get(i['status'], 'info')}'>{_e(FIX_LABEL.get(i['status'], i['status']))}</span></td>"
                     f"<td><code>{_e(i['file'])}:{i['line']}</code></td><td>{_e(i['rule'])}</td><td>{_e(i['change'])}</td><td>{_e(why)}</td></tr>")
        h.append("</table>")
        if c.fix_verify:
            h.append("<div class='note'><strong>Verification.</strong><ul>" + "".join(f"<li>{_e(x)}</li>" for x in _verify_lines(c.fix_verify))
                     + "</ul></div>")
    if c.diff is not None:
        lines = []
        for ln in c.diff.splitlines():
            cls = "hdr" if ln.startswith(("---", "+++", "@@")) else "add" if ln.startswith("+") else "del" if ln.startswith("-") else ""
            lines.append(f"<span class='{cls}'>{_e(ln)}</span>" if cls else _e(ln))
        extra = (f" {c.fix['summary']['files_changed']} files, {c.fix['summary']['model_id_replacements']} model ID replacements plus code fixes."
                 if c.fix else f" {c.swap['replacements']} replacements in {c.swap['files_changed']} files." if c.swap else "")
        h.append(f"<h2>Proposed code change</h2><p>Nothing has been changed in your repository. This patch is for review.{extra}</p>"
                 f"<pre class='diff'>{chr(10).join(lines)}</pre>")
    if c.ev:
        ev = c.ev
        h.append(f"<h2>Regression eval: <code>{_e(ev['old_model'])}</code> vs <code>{_e(ev['new_model'])}</code></h2>")
        if ev["mode"] == "mock":
            h.append("<div class='note'><strong>Demo run.</strong> These results use simulated outputs to show the format. "
                     "A real engagement runs the same suite against both models with the client's API key.</div>")
        else:
            h.append(f"<div class='note'><strong>Live run</strong> against the provider API ({_e(ev['api'])} endpoint), "
                     f"{_e(ev['run_at'])}. {_e(_cost_line(ev))} DRIFT means the new model's output differs and needs a "
                     "human look; it is not automatically a failure.</div>")
        h.append("<table><tr><th>Case</th><th>Type</th><th>Status</th><th>What changed</th></tr>")
        for x in ev["cases"]:
            h.append(f"<tr><td><code>{_e(x['id'])}</code></td><td>{_e(x['type'])}</td>"
                     f"<td><span class='risk {x['status']}'>{_e(x['status'])}</span></td><td>{_e(_explain(x))}</td></tr>")
        h.append("</table>")
    steps = c.next_steps()
    if steps:
        h.append("<h2>Next steps</h2><ol>" + "".join(f"<li>{_e(st)}</li>" for _p, st in steps) + "</ol>")
    h.append(f"<footer>Generated by {_e(brand.PRODUCT_NAME)} ({_e(brand.COMPANY)}). Migration packs: "
             + ", ".join(f"{_e(p.provider)} v{_e(p.version)}" for p in c.packs)
             + ". Re-verify against the providers' documentation before acting.</footer></body></html>")
    return "\n".join(h)


def generate(client: str, scan_path: str | Path, out_dir: str | Path, swap_path=None, diff_path=None,
             eval_path=None, today: dt.date | None = None, label: str | None = None,
             packs: PackSet | None = None, fix_plan_path=None, fix_verify_path=None) -> tuple[Path, Path]:
    today = today or dt.date.today()
    scan = json.loads(Path(scan_path).read_text())
    swap = json.loads(Path(swap_path).read_text()) if swap_path else None
    diff = Path(diff_path).read_text() if diff_path else None
    ev = json.loads(Path(eval_path).read_text()) if eval_path else None
    fix = json.loads(Path(fix_plan_path).read_text()) if fix_plan_path else None
    fv = json.loads(Path(fix_verify_path).read_text()) if fix_verify_path else None
    c = Ctx(client, scan, swap, diff, ev, today, label, packs or load_packs(), fix, fv)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    from .scanner import mark_output
    mark_output(out)
    md, ht = out / "client-report.md", out / "client-report.html"
    md.write_text(build_markdown(c))
    ht.write_text(build_html(c))
    return md, ht
