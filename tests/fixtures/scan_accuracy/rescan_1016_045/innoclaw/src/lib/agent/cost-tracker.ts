  ["gemini-3", TIER_GEMINI_FLASH],
  ["gemini-2.5-flash", TIER_GEMINI_FLASH],
  ["gemini-2.5-pro", TIER_GEMINI_PRO],
];

const DEFAULT_TIER = TIER_3_15;

function tierForModel(model: string): PricingTier | null {
  const modelLower = model.toLowerCase();
  for (const [prefix, tier] of MODEL_PRICING) {
    if (modelLower.includes(prefix)) {
      return tier;
    }
  }
  // Unknown non-Claude model
  if (modelLower.startsWith("gpt-") || modelLower.startsWith("o1") || modelLower.startsWith("o3") || modelLower.startsWith("o4")) {
    return null;
  }
  return DEFAULT_TIER;
}

