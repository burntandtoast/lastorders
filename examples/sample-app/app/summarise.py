"""Summarise support tickets into structured JSON."""
from openai import OpenAI

client = OpenAI()

TICKET_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "priority": {"type": "string", "enum": ["low", "medium", "high"]},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "priority", "tags"],
    "additionalProperties": False,
}


def summarise(ticket: str) -> str:
    resp = client.chat.completions.create(
        model="gpt-4o-2024-08-06",
        temperature=0.2,
        max_tokens=400,
        messages=[{"role": "user", "content": ticket}],
        response_format={"type": "json_schema", "json_schema": {"name": "ticket", "schema": TICKET_SCHEMA, "strict": True}},
    )
    return resp.choices[0].message.content
