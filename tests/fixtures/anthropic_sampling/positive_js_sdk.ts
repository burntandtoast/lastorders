import Anthropic from "@anthropic-ai/sdk";

const client = new Anthropic();
await client.messages.create({
  model: "claude-sonnet-5-5",
  max_tokens: 100,
  top_p: 0.8,
  messages: [],
});
