import click

@click.option("--model", default=None, help="Override the provider model. For OpenRouter, pass any OpenRouter model id, for example openai/gpt-4.1-nano.")
def consolidate(model):
    pass
