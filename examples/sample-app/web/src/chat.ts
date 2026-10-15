import OpenAI from "openai";

const openai = new OpenAI();

export async function reply(history: OpenAI.Chat.ChatCompletionMessageParam[]) {
  const completion = await openai.chat.completions.create({
    model: "gpt-4.1",
    messages: history,
    tools: [
      {
        type: "function",
        function: {
          name: "lookup_order",
          parameters: { type: "object", properties: { order_id: { type: "string" } }, required: ["order_id"] },
        },
      },
    ],
  });
  return completion.choices[0].message;
}

// Voice notes are transcribed separately; keep this on the transcription model
export async function transcribe(file: File) {
  return openai.audio.transcriptions.create({ model: "gpt-4o-transcribe", file });
}
