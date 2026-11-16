import anthropic
from openai import OpenAI

a = anthropic.Anthropic()
a.messages.create(model="claude-sonnet-5-5", max_tokens=50, messages=[])

o = OpenAI()
o.chat.completions.create(model="gpt-6-luna", temperature=0.7, messages=[])
