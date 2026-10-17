// excerpt: glowingjade/obsidian-smart-composer src/utils/llm/price-calculator.ts, lines 19-21
import { OPENAI_PRICES } from '../../constants'
export const price = (model: { model: string }) => OPENAI_PRICES[model.model] ?? null
