import OpenAI from "openai";

const openai = new OpenAI();
const MODEL = process.env.CLASSIFIER_MODEL ?? 'gpt-4.1-mini-2025-04-14';

export async function classify(text) {
  const response = await openai.responses.create({
    model: MODEL,
    input: `Classify the sentiment of: ${text}`,
  });
  return response.output_text;
}

export async function embed(text) {
  // Embeddings are unaffected by this migration
  return openai.embeddings.create({ model: "text-embedding-3-small", input: text });
}
