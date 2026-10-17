// Excerpt: Lapis0x0/obsidian-yolo src/settings/schema/migrations/5_to_6.ts:65-71
export const findO1 = (chatModels: unknown[]) =>
  chatModels.findIndex((model: unknown) => {
    return (model as { id: string }).id === 'o1'
  })
