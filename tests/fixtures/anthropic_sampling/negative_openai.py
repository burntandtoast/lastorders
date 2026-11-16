from openai import OpenAI

client = OpenAI()
client.chat.completions.create(
    model="gpt-6-luna",
    temperature=0.2,
    messages=[],
)
