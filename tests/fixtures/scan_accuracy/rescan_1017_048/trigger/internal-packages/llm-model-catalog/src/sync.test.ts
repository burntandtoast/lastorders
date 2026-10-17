// Excerpt: triggerdotdev/trigger.dev internal-packages/llm-model-catalog/src/sync.test.ts:5-14
import { defaultModelPrices } from "./defaultPrices.js";

function getGpt4oDefinition() {
  const def = defaultModelPrices.find((m) => m.modelName === "gpt-4o");
  if (def === undefined) {
    throw new Error("expected gpt-4o in defaultModelPrices");
  }
  return def;
}
const MODEL = "gpt-4o";
