"""Client-facing report (Markdown + self-contained HTML)."""
from __future__ import annotations

import datetime as dt
import html
import json
from pathlib import Path

from . import catalogue as cat
from .scanner import CAT_LABEL

RISK_ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}

CONFIRMED = [
    f"OpenAI announced on 14 Oct 2026 that these GPT-4 series snapshots will be removed from the API on "
    f"14 Jan 2027: gpt-4o-2024-08-06, gpt-4o-2024-11-20, gpt-4o-mini-2024-07-18, gpt-4.1-2025-04-14, "
    f"gpt-4.1-mini-2025-04-14.",
    "OpenAI's recommended replacement for all five is gpt-6-luna.",
    *cat.FINE_TUNE_FACTS,
    "gpt-6-luna supports Chat Completions, Responses, Batch, structured outputs and function calling; "
    "on Chat Completions, function calling works only with reasoning_effort set to 'none'.",
    "gpt-6-luna does not support the Assistants API or legacy /v1/completions.",
    "Shutdown dates can be checked per account via GET /v1/models (the shutdown_date field).",
]
UNCONFIRMED = [
    "Whether the undated aliases (gpt-4o, gpt-4o-mini, gpt-4.1, gpt-4.1-mini) stop working on 14 Jan 2027 or are "
    "re-pointed. The page lists the families by name with dated snapshots only; we treat the aliases as affected.",
    "Which sampling/length parameters (temperature, top_p, max_tokens, logprobs) gpt-6-luna accepts. It is a "
    "reasoning model; we test rather than assume.",
    "Output quality, latency and cost on the client's own workload. Only the regression eval below can show that.",
]


def _days_left(today: dt.date) -> int:
    return (dt.date.fromisoformat(cat.PRIMARY_SHUTDOWN) - today).days


def build_markdown(client: str, scan: dict, swap: dict | None, diff: str | None, ev: dict | None,
                   today: dt.date) -> str:
    s = scan["summary"]
    findings = sorted(scan["findings"], key=lambda f: (RISK_ORDER.get(f["risk"], 9), f["file"], f["line"]))
    o = [f"# OpenAI model migration report: {client}", "",
         f"Prepared by Burnt & Toast Studios on {today:%d %B %Y}.", "",
         "## At a glance", "",
         f"- **Deadline:** OpenAI removes GPT-4o, GPT-4o mini, GPT-4.1 and GPT-4.1 mini from the API on "
         f"**14 January 2027** ({_days_left(today)} days from this report).",
         f"- **Model references found:** {s['total_findings']} across {s['files_with_findings']} files "
         f"({scan['files_scanned']} files scanned).",
         f"- **High risk:** {s['by_risk'].get('high', 0)} | **Medium:** {s['by_risk'].get('medium', 0)} | "
         f"**Low:** {s['by_risk'].get('low', 0)} | **Info:** {s['by_risk'].get('info', 0)}",
         f"- **Fine-tuned models:** {len(s['fine_tuned_models'])} (need a separate decision)"]
    if s["env_var_model_refs"]:
        o.append(f"- **Models set by environment variable:** {', '.join('`'+v+'`' for v in s['env_var_model_refs'])} "
                 "(check the live values on your servers)")
    if swap:
        o.append(f"- **Proposed patch:** {swap['replacements']} replacements in {swap['files_changed']} files, "
                 f"{len(swap['skipped_fine_tunes'])} fine-tuned references left untouched")
    if ev:
        summ = ", ".join(f"{v} {k}" for k, v in sorted(ev["summary"].items()))
        o.append(f"- **Regression eval ({ev['mode']}):** {summ}")
    o += ["", "## What OpenAI has confirmed", "",
          f"Source: [{cat.DEPRECATIONS_URL}]({cat.DEPRECATIONS_URL}) and "
          f"[gpt-6-luna model page]({cat.LUNA_URL}), checked {cat.CHECKED_ON}.", ""]
    o += [f"- {x}" for x in CONFIRMED]
    o += ["", "## What we have not been able to confirm", ""] + [f"- {x}" for x in UNCONFIRMED]
    o += ["", "## Findings", "", "| Risk | File | Line | Current model | Suggested | Category | Notes |",
          "|---|---|---|---|---|---|---|"]
    for f in findings:
        sug = f"`{f['suggested']}`" if f["suggested"] else "decision needed"
        if f["confidence"] == "inferred" and f["suggested"]:
            sug += " (inferred)"
        notes = "<br>".join(n.replace("|", "\\|") for n in f["notes"])
        o.append(f"| **{f['risk']}** | `{f['file']}` | {f['line']} | `{f['model']}` | {sug} | "
                 f"{CAT_LABEL[f['category']]} | {notes} |")
    ft = [f for f in findings if f["category"] == "fine_tune"]
    if ft:
        o += ["", "## Fine-tuned models", "",
              "These can't be swapped automatically. gpt-6-luna can't be fine-tuned, so for each one you choose to:", "",
              "1. replace it with gpt-6-luna plus a stronger prompt and examples, proven with the regression eval, or",
              "2. re-train on another fine-tunable model, before new fine-tuning jobs close on 6 January 2027.", ""]
        o += [f"- `{f['model']}` in `{f['file']}` line {f['line']}" for f in ft]
    if diff is not None:
        o += ["", "## Proposed code change", "",
              "Nothing has been changed in your repository. This is the patch for review:", "", "```diff", diff.strip(), "```"]
    if ev:
        o += ["", f"## Regression eval: `{ev['old_model']}` vs `{ev['new_model']}`", ""]
        if ev["mode"] == "mock":
            o += ["> **Demo run.** These results use simulated outputs to show the format. A real engagement runs the "
                  "same suite against both models with the client's API key.", ""]
        o += ["| Case | Type | Status | What changed |", "|---|---|---|---|"]
        for c in ev["cases"]:
            o.append(f"| `{c['id']}` | {c['type']} | **{c['status'].upper()}** | {_explain(c)} |")
    o += ["", "## Next steps", "",
          "1. **Scan:** confirm the findings above, including environment variables set outside the repo.",
          "2. **Swap:** review and apply the patch on a branch; add `reasoning_effort: \"none\"` (Chat Completions + "
          "tools) or move those calls to the Responses API.",
          "3. **Eval:** run the regression suite against live models; fix prompts or schemas for any DRIFT or FAIL.",
          "4. **Handoff:** merge, deploy, update environment variables, check with GET /v1/models that no model you "
          "still call has a shutdown_date, and check your API usage for any remaining calls to retired models.", ""]
    return "\n".join(o)


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


# ------------------------------------------------------------------ HTML
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
.note{background:#fff8e6;border-left:4px solid #e0a800;padding:.6rem .9rem;margin:1rem 0}
pre.diff{background:#1e1e1e;color:#ddd;padding:1rem;overflow:auto;font-size:.8rem;border-radius:6px}
pre.diff .add{color:#7ee787}pre.diff .del{color:#ff7b72}pre.diff .hdr{color:#79c0ff}
footer{margin-top:3rem;color:#777;font-size:.8rem;border-top:1px solid #eee;padding-top:.75rem}
"""


def _e(x) -> str:
    return html.escape(str(x))


def build_html(client: str, scan: dict, swap: dict | None, diff: str | None, ev: dict | None, today: dt.date) -> str:
    s = scan["summary"]
    findings = sorted(scan["findings"], key=lambda f: (RISK_ORDER.get(f["risk"], 9), f["file"], f["line"]))
    h = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
         f"<title>OpenAI migration report - {_e(client)}</title><style>{CSS}</style></head><body>",
         f"<header><div class='brand'>Burnt &amp; Toast Studios</div><h1>OpenAI model migration report</h1>"
         f"<div>{_e(client)} &middot; {today:%d %B %Y}</div></header>",
         "<h2>At a glance</h2><div class='cards'>",
         f"<div class='card'><div class='n'>{_days_left(today)}</div><div class='l'>days until 14 Jan 2027 shutdown</div></div>",
         f"<div class='card'><div class='n'>{s['total_findings']}</div><div class='l'>model references in {s['files_with_findings']} files</div></div>",
         f"<div class='card'><div class='n'>{s['by_risk'].get('high', 0)}</div><div class='l'>high-risk findings</div></div>",
         f"<div class='card'><div class='n'>{len(s['fine_tuned_models'])}</div><div class='l'>fine-tuned models needing a decision</div></div>"]
    if ev:
        ok = ev["summary"].get("pass", 0) + ev["summary"].get("improved", 0)
        h.append(f"<div class='card'><div class='n'>{ok}/{len(ev['cases'])}</div><div class='l'>eval cases passing{' (demo)' if ev['mode']=='mock' else ''}</div></div>")
    h.append("</div>")
    if s["env_var_model_refs"]:
        h.append("<div class='note'>Some models are chosen by environment variable ("
                 + ", ".join(f"<code>{_e(v)}</code>" for v in s["env_var_model_refs"])
                 + "). Their live values are set outside the code and must be checked on your servers.</div>")
    h.append(f"<h2>What OpenAI has confirmed</h2><p>Source: <a href='{cat.DEPRECATIONS_URL}'>OpenAI deprecations</a> and "
             f"<a href='{cat.LUNA_URL}'>gpt-6-luna model page</a>, checked {cat.CHECKED_ON}.</p><ul>"
             + "".join(f"<li>{_e(x)}</li>" for x in CONFIRMED) + "</ul>")
    h.append("<h2>What we have not been able to confirm</h2><ul>" + "".join(f"<li>{_e(x)}</li>" for x in UNCONFIRMED) + "</ul>")
    h.append("<h2>Findings</h2><table><tr><th>Risk</th><th>File</th><th>Line</th><th>Current model</th>"
             "<th>Suggested</th><th>Category</th><th>Notes</th></tr>")
    for f in findings:
        sug = f"<code>{_e(f['suggested'])}</code>" if f["suggested"] else "<em>decision needed</em>"
        if f["confidence"] == "inferred" and f["suggested"]:
            sug += " <small>(inferred)</small>"
        h.append(f"<tr><td><span class='risk {f['risk']}'>{f['risk']}</span></td><td><code>{_e(f['file'])}</code></td>"
                 f"<td>{f['line']}</td><td><code>{_e(f['model'])}</code></td><td>{sug}</td>"
                 f"<td>{_e(CAT_LABEL[f['category']])}</td><td>{'<br>'.join(_e(n) for n in f['notes'])}</td></tr>")
    h.append("</table>")
    ft = [f for f in findings if f["category"] == "fine_tune"]
    if ft:
        h.append("<h2>Fine-tuned models</h2><p>These can't be swapped automatically, because gpt-6-luna can't be "
                 "fine-tuned. For each one, choose to:</p><ol><li>replace it with gpt-6-luna plus a stronger prompt and "
                 "examples, proven with the regression eval, or</li><li>re-train on another fine-tunable model before new "
                 "fine-tuning jobs close on 6 January 2027.</li></ol><ul>"
                 + "".join(f"<li><code>{_e(f['model'])}</code> in <code>{_e(f['file'])}</code> line {f['line']}</li>" for f in ft)
                 + "</ul>")
    if diff is not None:
        lines = []
        for ln in diff.splitlines():
            cls = "hdr" if ln.startswith(("---", "+++", "@@")) else "add" if ln.startswith("+") else "del" if ln.startswith("-") else ""
            lines.append(f"<span class='{cls}'>{_e(ln)}</span>" if cls else _e(ln))
        extra = f" {swap['replacements']} replacements in {swap['files_changed']} files." if swap else ""
        h.append(f"<h2>Proposed code change</h2><p>Nothing has been changed in your repository. This patch is for review.{extra}</p>"
                 f"<pre class='diff'>{chr(10).join(lines)}</pre>")
    if ev:
        h.append(f"<h2>Regression eval: <code>{_e(ev['old_model'])}</code> vs <code>{_e(ev['new_model'])}</code></h2>")
        if ev["mode"] == "mock":
            h.append("<div class='note'><strong>Demo run.</strong> These results use simulated outputs to show the format. "
                     "A real engagement runs the same suite against both models with the client's API key.</div>")
        h.append("<table><tr><th>Case</th><th>Type</th><th>Status</th><th>What changed</th></tr>")
        for c in ev["cases"]:
            h.append(f"<tr><td><code>{_e(c['id'])}</code></td><td>{_e(c['type'])}</td>"
                     f"<td><span class='risk {c['status']}'>{_e(c['status'])}</span></td><td>{_e(_explain(c))}</td></tr>")
        h.append("</table>")
    h.append("<h2>Next steps</h2><ol>"
             "<li><strong>Scan:</strong> confirm the findings, including environment variables set outside the repo.</li>"
             "<li><strong>Swap:</strong> review and apply the patch on a branch; add <code>reasoning_effort: \"none\"</code> "
             "for Chat Completions calls that use tools, or move them to the Responses API.</li>"
             "<li><strong>Eval:</strong> run the regression suite against live models and fix any DRIFT or FAIL.</li>"
             "<li><strong>Handoff:</strong> merge, deploy, update environment variables, check with "
             "<code>GET /v1/models</code> that no model you still call has a <code>shutdown_date</code>, and check your "
             "API usage for any remaining calls to retired models.</li></ol>")
    h.append(f"<footer>Generated by the Burnt &amp; Toast Studios OpenAI migration kit. Deprecation data checked {cat.CHECKED_ON}; "
             "re-verify against OpenAI's documentation before acting.</footer></body></html>")
    return "\n".join(h)


def generate(client: str, scan_path: str | Path, out_dir: str | Path, swap_path=None, diff_path=None,
             eval_path=None, today: dt.date | None = None) -> tuple[Path, Path]:
    today = today or dt.date.today()
    scan = json.loads(Path(scan_path).read_text())
    swap = json.loads(Path(swap_path).read_text()) if swap_path else None
    diff = Path(diff_path).read_text() if diff_path else None
    ev = json.loads(Path(eval_path).read_text()) if eval_path else None
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    md, ht = out / "client-report.md", out / "client-report.html"
    md.write_text(build_markdown(client, scan, swap, diff, ev, today))
    ht.write_text(build_html(client, scan, swap, diff, ev, today))
    return md, ht
