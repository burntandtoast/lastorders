    model_name = request.POST.get("model_name")
    if model_name in {"gpt-4.1-mini", "gpt-4.1"}:
        session["model_name"] = model_name

        "openrouter_api_key": session.get("openrouter_api_key", ""),
        "openai_base_url": session.get("openai_base_url", ""),
        "openrouter_base_url": session.get("openrouter_base_url", "https://openrouter.ai/api/v1"),
        "model_name": session.get("model_name", "gpt-4.1-mini"),
        "max_parallel_workers": normalise_parallel_workers(session.get("max_parallel_workers")),
        "report_start_date": session.get("report_start_date", date(2013, 1, 1).isoformat()),
