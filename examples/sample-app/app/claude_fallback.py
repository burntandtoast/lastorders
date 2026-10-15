"""Fallback summariser on Claude (shows the scanner is provider-neutral)."""
import anthropic

client = anthropic.Anthropic()


def summarise_with_claude(ticket: str) -> str:
    msg = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=400,
        temperature=0.3,
        messages=[{"role": "user", "content": ticket}],
    )
    return msg.content[0].text
