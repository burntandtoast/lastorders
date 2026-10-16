  modelIdOrName: string,
): 'openai' | 'gemini' | 'anthropic' | 'none' {
  const s = (modelIdOrName || '').toLowerCase()
  if (!s) return 'none'

  // Prefer explicit gemini match
  if (s.includes('gemini')) return 'gemini'

  // Claude / Anthropic
  if (s.includes('claude')) return 'anthropic'

  // Common OpenAI patterns: gpt*, o1/o3/o4 (including variants like o4mini), gpt5
  if (
    s.includes('gpt') ||
    s.includes('o1') ||
    s.includes('o3') ||
    s.includes('o4') ||
    s.includes('gpt5') ||
    s.includes('gpt-5')
  ) {
    return 'openai'
  }

  if (s.includes('deepseek-v4')) {
    return 'openai'
  }
