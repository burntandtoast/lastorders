// excerpt: Lapis0x0/obsidian-yolo src/settings/schema/setting.types.ts, lines 808-811
import { DEFAULT_CHAT_MODELS, DEFAULT_CHAT_TITLE_MODEL_ID } from '../../constants'
export const continuationModelId =
  DEFAULT_CHAT_MODELS.find((v) => v.id === DEFAULT_CHAT_TITLE_MODEL_ID)?.id ?? ''
