#' Interpret Epidemiological Data or Visualisations using LLMs
#'
#' **Supported LLM Providers and Models:**
#' - **OpenAI**: Utilises OpenAI's models via `chat_openai()`. Applicable models include:
#'   - `"gpt-4.1-nano"`
#' - **Google Gemini**: Applicable models include:
#'   - `"gemini-2.5-flash-lite"`
#' - **Anthropic Claude**: Applicable models include:
#'   - `"claude-sonnet-4-20250514"`
#'
#' @section Tested Models:
#' As of October 2025, this function has been tested and verified to work with the following models:
#' - OpenAI: gpt-4.1-nano
#' - Anthropic: claude-sonnet-4-20250514
#' - Google Gemini: gemini-2.5-flash-lite
llm_interpret <- function(input, prompt_extension = NULL) {
  # The real function reads LLM_MODEL from the environment. This string is here
  # so the fixture covers a model ID in R code, not only in roxygen.
  chat <- chat_openai(model = "gpt-4.1-nano")
  chat
}
