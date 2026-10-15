import OpenAI from "openai";

const client = new OpenAI();

export async function spread(input: string, opts: Record<string, unknown>) {
  return client.responses.create({ model: "gpt-4.1-mini", input, temperature: 0.2, ...opts });
}

export async function viaVariable(params: OpenAI.Responses.ResponseCreateParams) {
  return client.responses.create(params);
}

export async function nested(input: string) {
  return client.responses.create({
    model: "gpt-4.1-mini",
    input,
    top_p: 0.5,
    reasoning: { summary: "auto" }
  });
}
