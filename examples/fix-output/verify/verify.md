# Fix verification

- Overall: **PASS**
- Unexpected API rejections of patched calls: **0**
- Patch applies to a clean copy: **PASS**
- Syntax of changed files: **PASS**
- Re-running the fixer on the patched code changes nothing: **PASS**

## Eval (live)

Each fixed call is sent as before the patch (old model, old arguments) and as after it (new model, patched arguments).

| Suite | API | Cases | Old rejected | New rejected | Results |
|---|---|---|---|---|---|
| fix-verify-chat | chat | 3 | 0 | 0 | drift 3 |
| fix-verify-responses | responses | 1 | 0 | 0 | pass 1 |

### Control: unpatched arguments on the new model

| Case | Arguments | Result |
|---|---|---|
| `agent-29` | `{"max_completion_tokens": 300}` | rejected: HTTP 400: { "error": { "message": "Function tools with reasoning_effort are not supported for gpt-6-luna in /v1/chat/completions. To use function tools, use /v1/responses or set reasoning_effort to 'n |
| `summarise-19` | `{"temperature": 0.2, "max_tokens": 400}` | rejected: HTTP 400: { "error": { "message": "Unsupported parameter: 'max_tokens' is not supported with this model. Use 'max_completion_tokens' instead.", "type": "invalid_request_error", "param": "max_tokens",  |
| `chat-6` | `{"max_completion_tokens": 300}` | rejected: HTTP 400: { "error": { "message": "Function tools with reasoning_effort are not supported for gpt-6-luna in /v1/chat/completions. To use function tools, use /v1/responses or set reasoning_effort to 'n |

Not replayed:
- app/claude_fallback.py:8: no eval adapter for anthropic yet

Drift on smoke prompts is expected: they check that the API accepts the patched request. Behaviour is checked by your own suite (`init-evals`, then `--evals`).
