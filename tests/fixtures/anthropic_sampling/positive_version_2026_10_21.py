import anthropic

client = anthropic.Anthropic(default_headers={"anthropic-version": "2026-10-21"})
resp = client.messages.create(
    model="claude-sonnet-5-5",
    max_tokens=100,
    temperature=0.2,
    messages=[],
)
