// Excerpt: Lapis0x0/obsidian-yolo src/utils/llm/openrouter-model-capabilities.ts:7-10,231-246,495-505
export const OPENROUTER_MODEL_CAPABILITIES: Record<
  string,
  OpenRouterChatModelCapability
> = {
  'gpt-3.5-turbo': { context: 16385, modalities: ['text'] },
  'gpt-3.5-turbo:batch': { context: 16385, modalities: ['text'] },
  'gpt-4.1': { context: 1047576, modalities: ['vision', 'text'] },
  'gpt-4.1-mini': { context: 1047576, modalities: ['vision', 'text'] },
  'gpt-4.1-mini:batch': { context: 1047576, modalities: ['vision', 'text'] },
  'gpt-4.1-nano': { context: 1047576, modalities: ['vision', 'text'] },
  'gpt-4.1:batch': { context: 1047576, modalities: ['vision', 'text'] },
  o1: { context: 200000, modalities: ['text', 'vision'] },
  'o3-mini': { context: 200000, modalities: ['text'] },
  'o4-mini': { context: 200000, modalities: ['vision', 'text'] },
}
