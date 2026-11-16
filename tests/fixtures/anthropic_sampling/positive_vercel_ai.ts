import { generateText } from "ai";
import { anthropic } from "@ai-sdk/anthropic";

const result = await generateText({
  model: anthropic("claude-sonnet-5-5"),
  temperature: 0.4,
  prompt: "Hello",
});
