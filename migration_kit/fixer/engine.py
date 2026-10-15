"""Fixer engine: evaluates pack rules per call site and turns their `fix` specs into edits.

Pipeline: (1) swap model IDs with the pack mapping (same engine as `swap`), (2) find API
calls in the swapped code with the language adapters, (3) work out which model each call
ends up on, (4) evaluate every pack rule against the call's own arguments, (5) apply the
rule's `fix` (rename / remove / set) or record a manual item, (6) emit one unified diff.

Everything provider-specific (endpoints, parameter names, values, evidence) is pack data.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..scanner import mark_output as _mark
from .. import brand
from ..packs import Pack, PackSet, load_packs
from ..scanner import _rule_applies, iter_files, scan
from ..swapper import Mapping, _unified, mapping_from_packs
from ..swapper import plan as swap_plan
from . import jsfix, pyfix
from .callsite import UNRES, CallSite, Edit

AUTO_CONFIDENCE = {"confirmed", "live-tested"}
CODE_LANGS = {"python", "javascript", "typescript"}


@dataclass
class FixItem:
    file: str
    line: int
    provider: str
    rule: str                 # rule id, or "fine-tune" / "model-unknown" / "model-swap"
    status: str               # fixed | fixed-coupled | manual | info
    message: str
    change: str = ""          # human-readable description of the edit (or the edit we did NOT make)
    model: str | None = None  # model the call uses after the patch
    target: str | None = None
    endpoint: str | None = None
    confidence: str = ""
    notes: list[str] = field(default_factory=list)


@dataclass
class CallRecord:
    """A fixed call, before and after, for verification (eval)."""
    file: str
    line_before: int
    line_after: int
    lang: str
    provider: str
    endpoint: str | None
    old_model: str | None
    new_model: str | None
    params_before: dict
    params_after: dict
    rules: list[str]
    args_before: list[str] = field(default_factory=list)   # every argument name, literal or not
    args_after: list[str] = field(default_factory=list)


@dataclass
class FixResult:
    root: str
    items: list[FixItem]
    diff: str
    new_contents: dict[str, str]
    swap_changes: int
    calls: list[CallRecord]
    packs: list[dict]
    options: dict

    def counts(self) -> dict:
        c: dict[str, int] = {}
        for i in self.items:
            c[i.status] = c.get(i.status, 0) + 1
        return c

    def to_dict(self) -> dict:
        return {"tool": brand.CLI_NAME, "root": Path(self.root).name, "packs": self.packs, "options": self.options,
                "summary": {"files_changed": len(self.new_contents), "model_id_replacements": self.swap_changes,
                            "items": self.counts()},
                "items": [asdict(i) for i in self.items], "calls": [asdict(c) for c in self.calls]}


# ------------------------------------------------------------------ pack helpers
class _PackCalls:
    """Call-level view of one pack's signals."""

    def __init__(self, pack: Pack):
        self.pack = pack
        self.endpoints: dict[str, list[str]] = {}       # signal id -> callee patterns
        self.params: list[tuple[str, dict]] = []        # (signal id, call spec)
        for s in pack.data.get("signals", []):
            call = s.get("call")
            if not call:
                continue
            if call.get("callees"):
                self.endpoints.setdefault(s["id"], []).extend(call["callees"])
            if call.get("params") or call.get("param_values"):
                self.params.append((s["id"], call))
        self.replacements = {m.replacement for m in list(pack.exact.values()) + pack.prefixes if m.replacement}
        for r in pack.data.get("rules", []):
            self.replacements.update((r.get("applies_to") or {}).get("replacements") or [])

    @property
    def callees(self) -> list[str]:
        return [c for cs in self.endpoints.values() for c in cs]

    def endpoint_of(self, dotted: str) -> tuple[str | None, int]:
        best, ln = None, -1
        for sid, pats in self.endpoints.items():
            p = pyfix.callee_matches(dotted, pats)
            if p and len(p) > ln:
                best, ln = sid, len(p)
        return best, ln

    def call_signals(self, cs: CallSite, endpoint: str) -> set[str]:
        sig = {endpoint}
        for sid, spec in self.params:
            ign = spec.get("ignore_values") or {}
            for p in spec.get("params") or []:
                a = cs.get(p)
                if a is not None and not (a.value is not UNRES and _in(a.value, ign.get(p, []))):
                    sig.add(sid)
            for p, vals in (spec.get("param_values") or {}).items():
                a = cs.get(p)
                if a is not None and a.value is not UNRES and _in(a.value, vals):
                    sig.add(sid)
        return sig


def _in(v: Any, vals: list) -> bool:
    return any(v == x and type(v) is not bool or v is x for x in vals) if not isinstance(v, bool) else v in [x for x in vals if isinstance(x, bool)]


def _describe(e: Edit) -> str:
    if e.op == "rename":
        return f"rename `{e.path}` -> `{e.new_name}`"
    if e.op == "remove":
        return f"remove `{e.path}`"
    return f"set `{e.path}` = {json.dumps(e.value)}"


def _edits_for(fix: dict, cs: CallSite, endpoint: str) -> tuple[list[Edit], str | None]:
    """Edits for a rule's fix spec on this call, or (.., reason) when it must be manual."""
    act = fix.get("action")
    if act == "rename_param":
        frm = fix["from"]
        to = fix.get("to")
        new = to.get(endpoint) if isinstance(to, dict) else to
        if not cs.has(frm):
            return [], "parameter not passed explicitly here (set via a variable or **kwargs?)"
        if not new:
            return [], f"no automatic rename defined for this call type ({endpoint})"
        if cs.has(new):
            return [], f"`{new}` is already set as well; remove `{frm}` by hand"
        return [Edit("rename", frm, new_name=new)], None
    if act == "remove_param":
        es = [Edit("remove", p) for p in fix.get("params") or [] if cs.has(p)]
        return es, (None if es else "parameters not passed explicitly here")
    if act == "set_param":
        spec = (fix.get("per_endpoint") or {}).get(endpoint)
        if spec is None and "param" in fix:
            spec = {"param": fix["param"], "value": fix.get("value")}
        if spec is None:
            return [], f"no automatic fix defined for this call type ({endpoint})"
        cur = cs.get(spec["param"])
        if cur is not None:
            if cur.value == spec["value"]:
                return [], None
            return [], f"`{spec['param']}` is already set to `{cur.src}`; decide which value you need"
        if cs.opaque:
            return [], "the call also passes **kwargs / a spread object; adding the argument could duplicate it"
        head = spec["param"].split(".")[0]
        if "." in spec["param"] and cs.has(head) and cs.get(head).nested is None:
            return [], f"`{head}` is built dynamically; add `{spec['param']}` by hand"
        return [Edit("set", spec["param"], value=spec["value"])], None
    if act == "move_endpoint":
        return [], f"move this call to `{fix.get('to')}` (not automated)"
    return [], fix.get("note") or "needs a manual decision"


# ------------------------------------------------------------------ main
def _adapter(lang: str):
    return pyfix if lang == "python" else jsfix


def _find(lang: str, text: str, rel: str, callees: list[str]) -> list[CallSite]:
    if lang == "python":
        return pyfix.find_calls(text, rel, callees)
    return jsfix.find_calls(text, rel, callees, lang)


def _apply(lang: str, text: str, edits: dict, callees: list[str]):
    if lang == "python":
        return pyfix.apply_edits(text, edits)
    return jsfix.apply_edits(text, edits, callees)


SKIP_PARAMS = {"model"}      # the eval adapter decides which of the rest it replays


def plan_fixes(root: str | Path, packs: PackSet | None = None, mapping: Mapping | None = None,
               model_swap: bool = True, assume_model: str | None = None,
               include_inferred: bool = False) -> FixResult:
    root = Path(root).resolve()
    packs = packs or load_packs()
    pcs = [_PackCalls(p) for p in packs]
    callees = sorted({c for pc in pcs for c in pc.callees})
    mapping = mapping or mapping_from_packs(packs)
    swapped = swap_plan(root, mapping, packs) if model_swap else None
    texts = dict(swapped.new_contents) if swapped else {}
    items: list[FixItem] = []
    records: list[CallRecord] = []
    new_contents: dict[str, str] = {}
    diffs: list[str] = []
    parsed_providers: dict[str, set[str]] = {}

    for path, lang in iter_files(root, include_docs=False):
        rel = path.relative_to(root).as_posix()
        try:
            orig = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        cur = texts.get(rel, orig)
        if lang not in CODE_LANGS:
            if cur != orig:
                new_contents[rel] = cur
            continue
        sites = _find(lang, cur, rel, callees)
        before = _find(lang, orig, rel, callees) if cur != orig else sites
        if len(before) != len(sites):
            before = sites
        file_edits: dict[Any, list[Edit]] = {}
        pending: list[tuple[CallSite, CallSite, FixItem | None, list[Edit], _PackCalls, str, str | None, str | None, list[str]]] = []
        for cs, cs0 in zip(sites, before):
            cands = [(pc, *pc.endpoint_of(cs.callee)) for pc in pcs]
            cands = [c for c in cands if c[1]]
            if not cands:
                continue
            pc, endpoint, _ = max(cands, key=lambda c: c[2])
            pack = pc.pack
            parsed_providers.setdefault(rel, set()).add(pack.provider)
            sig = pc.call_signals(cs, endpoint)
            ma, ma0 = cs.get("model"), cs0.get("model")
            model = ma.value if ma is not None and isinstance(ma.value, str) else None
            model0 = ma0.value if ma0 is not None and isinstance(ma0.value, str) else None
            via_env = ma.via_env if ma is not None else None
            if model and pack.fine_tune_base(model) is not None:
                ft = pack.data.get("fine_tune") or {}
                base = pack.fine_tune_base(model)
                bm = pack.lookup(base)
                items.append(FixItem(rel, cs.line, pack.provider, "fine-tune", "manual",
                                     f"Fine-tuned model `{model}` (base `{base}`"
                                     + (f", shuts down {bm.shutdown}" if bm and bm.shutdown else "") + "). Not changed automatically.",
                                     model=model, target=bm.replacement if bm else None, endpoint=endpoint,
                                     notes=list(ft.get("notes", []))))
                continue
            lm = pack.lookup(model) if model else None
            lm0 = pack.lookup(model0) if model0 else None
            if model and model in pc.replacements:
                target = model
            elif lm and lm.replacement:
                target = lm.replacement
            elif model is None and assume_model:
                target = assume_model
            else:
                target = None
            migration = (lm0 or lm).migration if (lm0 or lm) else None
            if target is None:
                if model is None:
                    heads = {m["replacement"] for m in pack.headline_migrations if m.get("replacement")}
                    would = sorted({r["id"] for r in pack.data.get("rules", []) for h in heads
                                    if r.get("fix") and _rule_applies(r, h, None, sig)})
                    if would:
                        items.append(FixItem(rel, cs.line, pack.provider, "model-unknown", "manual",
                                             "The model for this call isn't visible in the code, so no fix was applied. "
                                             f"If it runs on {', '.join(sorted(heads))}, these rules apply: {', '.join(would)}.",
                                             change=f"re-run with --assume-model {sorted(heads)[0]} to apply them",
                                             endpoint=endpoint, notes=[f"model expression: `{ma.src}`" if ma else "no model argument"]))
                continue
            ready = (model == target) or (model is None and assume_model == target)
            applicable = [r for r in pack.data.get("rules", []) if _rule_applies(r, target, migration, sig)]
            keep = [r for r in applicable if (r.get("fix") or {}).get("keep_model")]
            kept = False
            if keep and model0 and model0 != model:
                literal = ma is not None and ma.src.strip()[:1] in "\"'`"
                if literal:
                    file_edits.setdefault(cs.key, []).append(Edit("replace", "model", value=model0))
                    kept, model = True, model0
                    for r in keep:
                        items.append(FixItem(rel, cs.line, pack.provider, r["id"], "manual", r["message"],
                                             change=f"kept on `{model0}` in the patch (not swapped to {target}). "
                                                    + (r["fix"].get("note") or ""),
                                             model=model0, target=target, endpoint=endpoint,
                                             confidence=r.get("confidence", "")))
                else:
                    items.append(FixItem(rel, cs.line, pack.provider, keep[0]["id"], "manual",
                                         f"{target} can't serve this call, but its model comes from `{ma.src if ma else '?'}`, "
                                         "which the patch switches for other calls too.",
                                         change="give this call its own model setting before applying the swap",
                                         model=model, target=target, endpoint=endpoint))
            rules_hit = []
            for rule in applicable:
                rules_hit.append(rule["id"])
                fix = rule.get("fix")
                conf = rule.get("confidence", "")
                base_item = dict(file=rel, line=cs.line, provider=pack.provider, rule=rule["id"], model=model or assume_model,
                                 target=target, endpoint=endpoint, confidence=conf)
                if kept:
                    if rule not in keep:
                        items.append(FixItem(**base_item, status="info" if rule["risk"] == "info" else "manual",
                                             message=rule["message"], change="fix this when you move the call"))
                    continue
                if not fix:
                    items.append(FixItem(**base_item, status="info" if rule["risk"] == "info" else "manual",
                                         message=rule["message"]))
                    continue
                edits, why = _edits_for(fix, cs, endpoint)
                notes = [f"Alternative: {fix['alternative']}."] if fix.get("alternative") else []
                if why is None and not edits:
                    continue                                    # already compliant
                if why:
                    items.append(FixItem(**base_item, status="manual", message=rule["message"], change=why,
                                         notes=([fix["note"]] if fix.get("note") and fix["note"] != why else []) + notes))
                    continue
                desc = "; ".join(_describe(e) for e in edits)
                if conf not in AUTO_CONFIDENCE and not include_inferred:
                    items.append(FixItem(**base_item, status="manual", message=rule["message"],
                                         change=f"suggested: {desc} (rule confidence '{conf}'; pass --include-inferred to apply)",
                                         notes=notes))
                    continue
                status = "fixed"
                if fix.get("requires_new_model"):
                    if not ready:
                        items.append(FixItem(**base_item, status="manual", message=rule["message"],
                                             change=f"suggested: {desc}, but only together with switching this call to "
                                                    f"{target}; the current model would reject it",
                                             notes=notes + [fix.get("requires_new_model_evidence", "")]))
                        continue
                    if via_env or (model is None and assume_model):
                        status = "fixed-coupled"
                        notes.append((f"The model comes from ${via_env} (default now {model}). " if via_env else
                                      "The model isn't visible in the code (fixed because of --assume-model). ")
                                     + f"Deploy this change together with switching the model to {target}: "
                                     + (fix.get("requires_new_model_evidence") or "the old model rejects it."))
                elif via_env:
                    notes.append(f"The model comes from ${via_env}; this change is safe on the old model too.")
                fresh = [e for e in edits if not any((x.op, x.path) == (e.op, e.path) for x in file_edits.get(cs.key, []))]
                if not fresh:
                    notes.append("Same change as another rule on this call.")
                file_edits.setdefault(cs.key, []).extend(fresh)
                items.append(FixItem(**base_item, status=status, message=rule["message"], change=desc, notes=notes))
            if not kept:
                pending.append((cs, cs0, model0, model or assume_model, pack.provider, endpoint, rules_hit))
        if file_edits:
            cur2, applied = _apply(lang, cur, file_edits, callees)
            done = {(k, e.op, e.path) for k, e in applied}
            for k, es in file_edits.items():
                for e in es:
                    if (k, e.op, e.path) not in done:
                        for it in items:
                            if it.file == rel and it.status.startswith("fixed") and _describe(e) in it.change:
                                it.status, it.change = "manual", f"could not apply automatically: {it.change}"
            cur = cur2
        if pending:
            after_sites = _find(lang, cur, rel, callees)
            # match by order: edits never add or remove calls
            for (cs, cs0, m0, m1, prov, ep, rules_hit), ca in zip(pending, _match_after(sites, after_sites, [p[0] for p in pending])):
                if not rules_hit and m0 == m1:
                    continue
                records.append(CallRecord(rel, cs0.line, ca.line if ca else cs.line, lang, prov, ep, m0, m1,
                                          cs0.literal_params(SKIP_PARAMS), (ca or cs).literal_params(SKIP_PARAMS), rules_hit,
                                          sorted(cs0.args), sorted((ca or cs).args)))
        if cur != orig:
            new_contents[rel] = cur
    for rel in sorted(new_contents):
        o = (root / rel).read_text(encoding="utf-8").splitlines(keepends=True)
        diffs.append(_unified(o, new_contents[rel].splitlines(keepends=True), rel))

    _file_level_items(root, packs, items, parsed_providers, swapped)
    items.sort(key=lambda i: (i.file, i.line, i.rule))
    return FixResult(str(root), items, "".join(diffs), new_contents, len(swapped.changes) if swapped else 0, records,
                     packs.info(), {"model_swap": model_swap, "assume_model": assume_model,
                                    "include_inferred": include_inferred, "mapping": mapping.source})


def _match_after(before: list[CallSite], after: list[CallSite], wanted: list[CallSite]) -> list[CallSite | None]:
    idx = {id(c): i for i, c in enumerate(before)}
    return [after[idx[id(w)]] if len(after) == len(before) else None for w in wanted]


def _file_level_items(root: Path, packs: PackSet, items: list[FixItem], parsed: dict[str, set[str]], swapped) -> None:
    """Rules the scanner found in files where no call could be parsed (configs, raw HTTP, ...)
    and fine-tunes outside parsed calls: listed for a manual decision."""
    res = scan(root, include_docs=False, packs=packs)
    have_ft = {(i.file, i.model) for i in items if i.rule == "fine-tune"}
    seen = set()
    for f in res.findings:
        pack = packs.get(f.provider)
        if f.category == "fine_tune" and (f.file, f.model) not in have_ft:
            have_ft.add((f.file, f.model))
            items.append(FixItem(f.file, f.line, f.provider, "fine-tune", "manual",
                                 f"Fine-tuned model `{f.model}` referenced here ({f.kind}). Not changed automatically.",
                                 model=f.model, notes=list(((pack.data.get("fine_tune") or {}).get("notes") or []) if pack else [])))
        if f.provider in parsed.get(f.file, set()):
            continue
        for rid in f.rules:
            rule = next((r for r in pack.data.get("rules", []) if r["id"] == rid), None) if pack else None
            if not rule or rule["risk"] == "info" or (f.file, rid) in seen:
                continue
            seen.add((f.file, rid))
            items.append(FixItem(f.file, f.line, f.provider, rid, "manual", rule["message"],
                                 change="found by the file-level scan, but no SDK call in this file could be parsed: "
                                        "check where this value is used", model=f.model, target=f.suggested,
                                 confidence=rule.get("confidence", "")))


# ------------------------------------------------------------------ output
STATUS_LABEL = {"fixed": "Fixed", "fixed-coupled": "Fixed (deploy with the model switch)",
                "manual": "Needs a decision", "info": "Info"}


def to_markdown(res: FixResult) -> str:
    c = res.counts()
    out = [f"# Automatic fix plan", "",
           f"- Repo: `{Path(res.root).name}`",
           f"- Packs: " + ", ".join(f"{p['provider']} v{p['version']}" for p in res.packs),
           f"- Files changed: **{len(res.new_contents)}** | model ID replacements: {res.swap_changes}",
           f"- Items: " + ", ".join(f"{STATUS_LABEL.get(k, k)}: **{v}**" for k, v in sorted(c.items())),
           "", "Nothing has been changed on disk. Review `fix.diff`, then apply it with `git apply` "
           f"or `{brand.CLI_NAME} fix --apply` (licensed).", ""]
    for status in ("fixed", "fixed-coupled", "manual", "info"):
        its = [i for i in res.items if i.status == status]
        if not its:
            continue
        out += [f"## {STATUS_LABEL[status]} ({len(its)})", "", "| File | Rule | Change | Why |", "|---|---|---|---|"]
        for i in its:
            why = i.message + ("" if not i.notes else " " + " ".join(n for n in i.notes if n))
            out.append(f"| `{i.file}:{i.line}` | {i.rule} | {i.change.replace('|', '/')} | {why.replace('|', '/')} |")
        out.append("")
    return "\n".join(out)


def write(res: FixResult, out_dir: str | Path) -> dict[str, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    _mark(out)
    paths = {"diff": out / "fix.diff", "json": out / "fix-plan.json", "md": out / "fix-plan.md"}
    paths["diff"].write_text(res.diff)
    paths["json"].write_text(json.dumps(res.to_dict(), indent=2, default=str))
    paths["md"].write_text(to_markdown(res))
    return paths


def apply_in_place(root: str | Path, res: FixResult) -> int:
    root = Path(root).resolve()
    for rel, text in res.new_contents.items():
        (root / rel).write_text(text, encoding="utf-8")
    return len(res.new_contents)
