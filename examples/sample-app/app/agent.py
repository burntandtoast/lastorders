"""Booking assistant that calls tools."""
import json
import os

from openai import OpenAI

client = OpenAI()
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

TOOLS = [{
    "type": "function",
    "function": {
        "name": "book_table",
        "description": "Book a restaurant table",
        "parameters": {
            "type": "object",
            "properties": {
                "date": {"type": "string"},
                "time": {"type": "string"},
                "party_size": {"type": "integer"},
            },
            "required": ["date", "time", "party_size"],
        },
    },
}]


def handle(message: str):
    resp = client.chat.completions.create(model=MODEL, messages=[{"role": "user", "content": message}], tools=TOOLS)
    return resp.choices[0].message.tool_calls


def classify_intent(message: str) -> str:
    # Fine-tuned classifier trained on our historic chat logs
    resp = client.chat.completions.create(
        model="ft:gpt-4o-mini-2024-07-18:acme-widgets:intent-v3:9xYzAbC1",
        messages=[{"role": "user", "content": message}],
    )
    return resp.choices[0].message.content
