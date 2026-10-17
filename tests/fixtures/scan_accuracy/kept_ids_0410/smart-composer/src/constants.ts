// excerpt: glowingjade/obsidian-smart-composer src/constants.ts (shallow clone 16 Oct 2026), lines 56-62, 371-374, 486-490
export const DEFAULT_APPLY_MODEL_ID = 'gpt-4.1-mini'
export const RECOMMENDED_MODELS_FOR_APPLY = ['gpt-4.1-mini']

export const DEFAULT_CHAT_MODELS = [
  {
    providerType: 'openai',
    id: 'gpt-4.1-mini',
    model: 'gpt-4.1-mini',
  },
]

export const OPENAI_PRICES: Record<string, { input: number; output: number }> = {
  'gpt-4.1': { input: 2.0, output: 8.0 },
  'gpt-4.1-mini': { input: 0.4, output: 1.6 },
  'gpt-4.1-nano': { input: 0.1, output: 0.4 },
  'gpt-4o': { input: 2.5, output: 10 },
  'gpt-4o-mini': { input: 0.15, output: 0.6 },
}
