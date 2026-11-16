import { generateText } from "ai";
import { openai } from "@ai-sdk/openai";

const result = await generateText({
  model: openai("gpt-6-luna"),
  temperature: 0.4,
  prompt: "Hello",
});
