            if provider_val not in [Provider.MISTRAL.value]:  # Example: Don't return Mistral if it might be OpenRouter/Groq
                return provider_val

    # 2. Common Model Name Prefixes (Lower Priority)
    if lname.startswith("gpt-") or lname.startswith("o1-") or lname.startswith("o3-"):
        return Provider.OPENAI.value
    if lname.startswith("claude-"):
