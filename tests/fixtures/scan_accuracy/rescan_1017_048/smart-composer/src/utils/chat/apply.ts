// Excerpt: glowingjade/obsidian-smart-composer src/utils/chat/apply.ts:15-24
const MAX_CHAT_HISTORY_MESSAGES = 10

const PREDICTED_OUTPUTS_SUPPORTED_MODELS = [
  'gpt-4o',
  'gpt-4o-mini',
  'gpt-4.1',
  'gpt-4.1-mini',
  'gpt-4.1-nano',
]

export const supportsPrediction = (model: string) => PREDICTED_OUTPUTS_SUPPORTED_MODELS.includes(model)
