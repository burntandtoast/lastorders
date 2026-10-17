# Excerpt: i-dot-ai/themefinder src/themefinder/llm_batch_processor.py:332-347
import os

import tiktoken


def calculate_string_token_length(input_text: str, model: str = None) -> int:
    """
    Calculates the number of tokens in a given string using the specified model's tokenizer.

    Args:
        model: The model name used for tokenization. Defaults to MODEL_NAME env var or "gpt-4o".
    """
    # Use the MODEL_NAME env var if no model is provided; otherwise default to "gpt-4o"
    model = model or os.environ.get("MODEL_NAME", "gpt-4o")
    tokenizer_encoding = tiktoken.encoding_for_model(model)
    return len(tokenizer_encoding.encode(input_text))


def other(model="gpt-4o"):
    return tiktoken.encoding_for_model("gpt-4o-mini")
