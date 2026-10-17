#!/usr/bin/env bash
# Excerpt: triggerdotdev/trigger.dev internal-packages/llm-model-catalog/scripts/generate-model-catalog.sh:1-12
set -euo pipefail
# Options:
#   --filter <pattern>   Only research models matching this ERE pattern (e.g. "gpt-4o|claude")
MODEL="gpt-4o"   # default model to research
