// Excerpt: Lapis0x0/obsidian-yolo src/constants.ts:552-560,614-650,747-760
export const DEFAULT_CHAT_MODELS: readonly ChatModel[] = [
  {
    providerId: PROVIDER_PRESET_INFO.openai.defaultProviderId,
    id: 'openai/gpt-4.1',
    model: 'gpt-4.1',
    enable: true,
  },
  {
    providerId: PROVIDER_PRESET_INFO.openai.defaultProviderId,
    id: 'openai/gpt-4.1-mini',
    model: 'gpt-4.1-mini',
    enable: true,
  },
  {
    providerId: PROVIDER_PRESET_INFO.openai.defaultProviderId,
    id: 'openai/gpt-4.1-nano',
    model: 'gpt-4.1-nano',
    enable: true,
  },
  {
    providerId: PROVIDER_PRESET_INFO.openai.defaultProviderId,
    id: 'openai/gpt-4o',
    model: 'gpt-4o',
    enable: false,
  },
  {
    providerId: PROVIDER_PRESET_INFO.openai.defaultProviderId,
    id: 'openai/gpt-4o-mini',
    model: 'gpt-4o-mini',
    enable: false,
  },
]

export const OPENAI_PRICES: Record<string, ModelPricing> = {
  'gpt-5': { input: 1.25, output: 10 },
  'gpt-4.1': { input: 2.0, output: 8.0 },
  'gpt-4.1-mini': { input: 0.4, output: 1.6 },
  'gpt-4.1-nano': { input: 0.1, output: 0.4 },
  'gpt-4o': { input: 2.5, output: 10 },
  'gpt-4o-mini': { input: 0.15, output: 0.6 },
  o3: { input: 10, output: 40 },
  o1: { input: 15, output: 60 },
}

export const DEFAULT_CHAT_TITLE_MODEL_ID = 'openai/gpt-4.1-mini'
