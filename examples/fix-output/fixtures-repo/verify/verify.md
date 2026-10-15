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
| fix-verify-chat | chat | 10 | 4 | 2 | drift 1, error 2, improved 3, pass 4 |
| fix-verify-responses | responses | 4 | 0 | 1 | error 1, pass 3 |

### Patched calls the API still rejects

- `variants-25` (chat): expected: open manual item (luna-sampling). HTTP 400: { "error": { "message": "Unsupported value: 'temperature' does not support 0.5 with this model. Only the default (1) value is supported.", "type": "invalid_request_error", "param": "temperature", "code": "unsup
- `variants-47` (chat): expected: open manual item (luna-chat-tools-effort). HTTP 400: { "error": { "message": "Function tools with reasoning_effort are not supported for gpt-6-luna in /v1/chat/completions. To use function tools, use /v1/responses or set reasoning_effort to 'none'.", "type": "inv
- `resp-6` (responses): expected: open manual item (luna-sampling). HTTP 400: { "error": { "message": "Unsupported parameter: 'temperature' is not supported with this model.", "type": "invalid_request_error", "param": "temperature", "code": null } }

### Original calls that already failed (before the patch)

- `variants-34` (chat): HTTP 400: { "error": { "message": "Unsupported parameter: 'max_tokens' is not supported with this model. Use 'max_completion_tokens' instead.", "type": "invalid_request_error", "param": "max_tokens", "code": "unsupported
- `variants-47` (chat): HTTP 400: { "error": { "message": "Unrecognized request argument supplied: reasoning_effort", "type": "invalid_request_error", "param": null, "code": null } }
- `variants-58` (chat): HTTP 400: { "error": { "message": "Unrecognized request argument supplied: reasoning_effort", "type": "invalid_request_error", "param": null, "code": null } }
- `chat-24` (chat): HTTP 400: { "error": { "message": "Unrecognized request argument supplied: reasoning_effort", "type": "invalid_request_error", "param": null, "code": null } }

### Control: unpatched arguments on the new model

| Case | Arguments | Result |
|---|---|---|
| `legacy-9` | `{"max_completion_tokens": 300}` | rejected: HTTP 400: { "error": { "message": "Function tools with reasoning_effort are not supported for gpt-6-luna in /v1/chat/completions. To use function tools, use /v1/responses or set reasoning_effort to 'n |
| `variants-25` | `{"temperature": 0.5, "max_tokens": 100}` | rejected: HTTP 400: { "error": { "message": "Unsupported parameter: 'max_tokens' is not supported with this model. Use 'max_completion_tokens' instead.", "type": "invalid_request_error", "param": "max_tokens",  |
| `variants-34` | `{"max_tokens": 100}` | rejected: HTTP 400: { "error": { "message": "Unsupported parameter: 'max_tokens' is not supported with this model. Use 'max_completion_tokens' instead.", "type": "invalid_request_error", "param": "max_tokens",  |
| `variants-51` | `{"max_completion_tokens": 300}` | rejected: HTTP 400: { "error": { "message": "Function tools with reasoning_effort are not supported for gpt-6-luna in /v1/chat/completions. To use function tools, use /v1/responses or set reasoning_effort to 'n |
| `chat-11` | `{"max_tokens": 256, "temperature": 0.3}` | rejected: HTTP 400: { "error": { "message": "Unsupported parameter: 'max_tokens' is not supported with this model. Use 'max_completion_tokens' instead.", "type": "invalid_request_error", "param": "max_tokens",  |
| `chat-16` | `{"max_tokens": 64}` | rejected: HTTP 400: { "error": { "message": "Unsupported parameter: 'max_tokens' is not supported with this model. Use 'max_completion_tokens' instead.", "type": "invalid_request_error", "param": "max_tokens",  |
| `variants-12` | `{"temperature": 0.7, "max_output_tokens": 200}` | rejected: HTTP 400: { "error": { "message": "Unsupported parameter: 'temperature' is not supported with this model.", "type": "invalid_request_error", "param": "temperature", "code": null } } |
| `variants-16` | `{"top_p": 0.9, "reasoning": {"summary": "auto"}, "max_output_tokens": 300}` | rejected: HTTP 400: { "error": { "message": "Unsupported parameter: 'top_p' is not supported with this model.", "type": "invalid_request_error", "param": "top_p", "code": null } } |
| `resp-14` | `{"top_p": 0.5, "reasoning": {"summary": "auto"}, "max_output_tokens": 300}` | rejected: HTTP 400: { "error": { "message": "Unsupported parameter: 'top_p' is not supported with this model.", "type": "invalid_request_error", "param": "top_p", "code": null } } |

Not replayed:
- py/chains.py:3: langchain_openai calls can't be replayed by the eval adapter

Drift on smoke prompts is expected: they check that the API accepts the patched request. Behaviour is checked by your own suite (`init-evals`, then `--evals`).
