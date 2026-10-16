package langchain

import "testing"

func TestEffectiveTemperatureOpenAIOSeriesUsesOne(t *testing.T) {
	t.Parallel()

	p := &LangchainProvider{
		providerType:   "openai",
		modelName:      "o4-mini",
		temperature:    0.4,
		temperatureSet: true,
	}

	if got := p.effectiveTemperature(); got != 1.0 {
		t.Fatalf("expected temperature 1.0 for OpenAI o-series, got %v", got)
	}
}

func TestEffectiveTemperatureNonOpenAIDefault(t *testing.T) {
	t.Parallel()

	p := &LangchainProvider{
		providerType:   "gemini",
		modelName:      "gemini-2.5-flash",
		temperature:    0,
		temperatureSet: false,
	}

	if got := p.effectiveTemperature(); got != 0.4 {
// The OpenAI default was "o4-mini".
