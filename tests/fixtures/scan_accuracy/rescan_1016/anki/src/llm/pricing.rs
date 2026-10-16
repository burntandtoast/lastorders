/// Per-model pricing in USD per million tokens.
pub struct ModelPricing {
    pub input_cost_per_million: f64,
    pub output_cost_per_million: f64,
}

/// Returns pricing for a known model, or `None` for unknown models.
pub fn model_pricing(model: &str) -> Option<ModelPricing> {
    let (input, output) = match model {
        // GPT-4.1 family
        "gpt-4.1" => (2.0, 8.0),
        "gpt-4.1-mini" => (0.4, 1.6),
        "gpt-4.1-nano" => (0.1, 0.4),
        // GPT-4o family
        "gpt-4o" => (2.5, 10.0),
