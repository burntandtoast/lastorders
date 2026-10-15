"""Formatting and argument variants."""
import os

from openai import OpenAI

client = OpenAI()
TOOLS = [{"type": "function", "function": {"name": "lookup", "parameters": {"type": "object", "properties": {}}}}]


def responses_sampling(text):
    # temperature on the Responses API -> reasoning.effort none
    return client.responses.create(model="gpt-4.1", input=text, temperature=0.7, max_output_tokens=200)


def responses_existing_reasoning(text):
    return client.responses.create(
        model="gpt-4.1-2025-04-14",
        input=text,
        top_p=0.9,
        reasoning={"summary": "auto"},
    )


def with_kwargs(text, **extra):
    return client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": text}],
                                          temperature=0.5, max_tokens=100, **extra)


def unknown_model(text, model_name):
    return client.chat.completions.create(model=model_name, messages=[{"role": "user", "content": text}], tools=TOOLS)


def already_new(text):
    return client.chat.completions.create(
        model="gpt-6-luna",
        messages=[{"role": "user", "content": text}],
        max_tokens=100,
        tools=TOOLS,
    )


def temperature_one(text):
    return client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": text}], temperature=1)


def conflict(text):
    return client.chat.completions.create(model="gpt-4o", messages=[], tools=TOOLS, reasoning_effort="low")


def single_arg_multiline(text):
    return client.chat.completions.create(
        model=os.environ.get("CHAT_MODEL", "gpt-4o-mini"),
        tools=TOOLS
    )


def already_ok(text):
    return client.chat.completions.create(model="gpt-4o", messages=[], tools=TOOLS, reasoning_effort="none")
