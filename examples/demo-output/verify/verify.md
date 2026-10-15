# Fix verification

- Overall: **PASS** (mock eval: request shapes and pipeline only, no real model calls)
- Unexpected API rejections of patched calls: **0**
- Patch applies to a clean copy: **PASS**
- Syntax of changed files: **PASS**
- Re-running the fixer on the patched code changes nothing: **PASS**

## Eval (mock)

Each fixed call is sent as before the patch (old model, old arguments) and as after it (new model, patched arguments).

| Suite | API | Cases | Old rejected | New rejected | Results |
|---|---|---|---|---|---|
| fix-verify-chat | chat | 3 | 0 | 0 | pass 3 |
| fix-verify-responses | responses | 1 | 0 | 0 | pass 1 |

Not replayed:
- app/claude_fallback.py:8: no eval adapter for anthropic yet

Drift on smoke prompts is expected: they check that the API accepts the patched request. Behaviour is checked by your own suite (`init-evals`, then `--evals`).
