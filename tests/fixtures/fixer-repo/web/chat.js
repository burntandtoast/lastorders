import OpenAI from "openai";

const openai = new OpenAI();
const PATTERN = /[{(]+/g; // regex literal with brackets
const DEFAULT_MODEL = process.env.CHAT_MODEL || "gpt-4o-2024-11-20";

export async function ask(q) {
  // a comment with braces { ( [ and a fake call: openai.chat.completions.create({ max_tokens: 1 })
  const note = "string with }) inside";
  const t = `template ${q} with { brace`;
  const r = await openai.chat.completions.create({ model: "gpt-4o", messages: [{ role: "user", content: q }], max_tokens: 256, temperature: 0.3 });
  return [r, note, t, PATTERN];
}

export async function multi(q) {
  return openai.chat.completions.create({
    model: DEFAULT_MODEL,
    messages: [{ role: "user", content: q }],
    'max_tokens': 64,
  });
}

export async function done(q) {
  return openai.chat.completions.create({ model: "gpt-4o", messages: [], tools: [], reasoning_effort: "none" });
}
