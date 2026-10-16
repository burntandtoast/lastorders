}

const LLM_PROVIDERS: &[LlmProvider] = &[
    LlmProvider {
        name: "OpenAI",
        env_var: "OPENAI_API_KEY",
        base_url: "https://api.openai.com/v1",
        probe_model: "gpt-4.1-nano",
    },
    LlmProvider {
        name: "Gemini",
        env_var: "GEMINI_API_KEY",
        base_url: "https://generativelanguage.googleapis.com/v1beta/openai",
        probe_model: "gemini-2.5-flash-lite",
    },
    LlmProvider {
