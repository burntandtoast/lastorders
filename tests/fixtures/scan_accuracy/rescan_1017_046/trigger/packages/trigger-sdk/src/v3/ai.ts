   * options so `streamText` uses it directly.
   *
   * The model string should use the `"provider:model-id"` format
   * (e.g. `"openai:gpt-4o"`, `"anthropic:claude-sonnet-4-6"`).
   */
  registry?: { languageModel(modelId: string): unknown };
