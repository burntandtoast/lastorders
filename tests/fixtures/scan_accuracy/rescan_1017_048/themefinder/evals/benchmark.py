#!/usr/bin/env python
"""Excerpt: i-dot-ai/themefinder evals/benchmark.py:1-25,214-222,310-312,945-1018.

Usage:
    uv run python benchmark.py --models gpt-4o gemini-2.5-flash claude-haiku-4.5
"""
import argparse

AZURE_MODELS = [
    ModelConfig(name="gpt-4o", deployment="gpt-4o-2024-08-06-sweden"),
    ModelConfig(name="gpt-4.1", deployment="gpt-4.1-sweden-2025-03"),
    ModelConfig(name="gpt-4.1-mini", deployment="gpt-4.1-mini"),
    ModelConfig(name="gpt-5-nano", deployment="gpt-5-nano", reasoning_effort="low"),
]
JUDGE = ModelConfig(name="gpt-4.1-nano", deployment="gpt-4.1-nano")
judge_deployment: str | None = (
    None  # Azure deployment name for judge LLM (e.g. "gpt-4o-2024-08-06")
)


def main():
    parser = argparse.ArgumentParser(
        description="Run ThemeFinder benchmark across Azure and Vertex AI models",
        epilog="""
Examples:
  uv run python benchmark.py --models gpt-4o gemini-2.5-flash --runs 2
""",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Quick CI smoke test: gambling_XS dataset, 1 run, azure provider, gpt-4.1 only.",
    )
    args = parser.parse_args()
    if args.quick:
        args.models = ["gpt-4.1"]
