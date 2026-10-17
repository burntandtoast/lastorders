def get_llm_config(session: dict[str, Any]) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    provider = session.get("provider_override", "OpenAI")
    model_name = (session.get("model_name") or "gpt-4.1-mini").strip() or "gpt-4.1-mini"
