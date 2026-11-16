const res = await fetch("https://api.anthropic.com/v1/messages", {
  method: "POST",
  headers: {
    "content-type": "application/json",
    "anthropic-version": "2023-06-01",
    "x-api-key": process.env.ANTHROPIC_API_KEY,
  },
  body: JSON.stringify({
    model: "claude-sonnet-5-5",
    max_tokens: 100,
    top_k: 20,
    messages: [],
  }),
});
