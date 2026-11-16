import anthropic

client = anthropic.Anthropic()
client.messages.create(model="claude-sonnet-5-5", max_tokens=50, messages=[])
