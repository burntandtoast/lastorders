// Excerpt: Lapis0x0/obsidian-yolo src/settings/schema/migrations/0_to_1.ts:5-14
export const migrateFrom0To1 = (data: Record<string, unknown>) => {
  const newData = { ...data }
  if ('chatModel' in newData && typeof newData.chatModel === 'string') {
    const CHAT_MODEL_MAP: Record<string, string> = {
      'gpt-4o': 'openai/gpt-4o',
      'gpt-4o-mini': 'openai/gpt-4o-mini',
    }
    newData.chatModelId = CHAT_MODEL_MAP[newData.chatModel] ?? newData.chatModel
  }
  return newData
}
