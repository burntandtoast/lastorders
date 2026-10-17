# excerpt: i-dot-ai/themefinder evals/benchmark.py (shallow clone 16 Oct 2026), lines 217-220 and 1013-1030
AZURE_MODELS = [
    ModelConfig(name="gpt-4o", deployment="gpt-4o-2024-08-06-sweden"),
    ModelConfig(name="gpt-4.1", deployment="gpt-4.1-sweden-2025-03"),
    ModelConfig(name="gpt-4.1-mini", deployment="gpt-4.1-mini"),
]


def main(args):
    if args.quick:
        args.dataset = "gambling_XS"
        args.provider = "azure"
        args.models = ["gpt-4.1"]
    models = [m for m in AZURE_MODELS if m.name in args.models]
    if not models:
        print("No matching models")
        return
