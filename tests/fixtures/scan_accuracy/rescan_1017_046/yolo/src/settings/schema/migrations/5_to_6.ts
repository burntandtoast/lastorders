  }

  // Add 'reasoning_effort' property for OpenAI reasoning models (o1, o1-mini, o3-mini)
  if ('chatModels' in newData && Array.isArray(newData.chatModels)) {
    newData.chatModels = newData.chatModels.map((model) => {
      if (
        model.providerType === 'openai' &&
        'model' in model &&
        ['o1', 'o1-mini', 'o3-mini'].includes(model.model as string)
      ) {
        model = {
          ...model,
          reasoning_effort: 'medium',
        }
      }
      return model as unknown
    })
