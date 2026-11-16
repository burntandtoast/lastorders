import anthropic

client = anthropic.Anthropic()
resp = client.messages.create(
    model="claude-sonnet-5-5",
    max_tokens=100,
    temperature=0.2,
    messages=[],
)
