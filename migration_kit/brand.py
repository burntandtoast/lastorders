"""Product naming in ONE place: everything user-visible reads from here.

The product is "Last Orders" (CLI, package and PyPI name `lastorders`, env prefix LASTORDERS_),
chosen 15 Oct 2026. To rename again, run `python scripts/rename_product.py "New Name" newcli`, which
updates this file plus every static place Python can't read at build time (pyproject.toml,
action.yml, workflows, docs, tests, examples, site/ and server/)."""
import os

PRODUCT_NAME = "Last Orders"
CLI_NAME = "lastorders"                # console command, package and PyPI distribution name
ENV_PREFIX = "LASTORDERS"              # env vars: LASTORDERS_OFFLINE, LASTORDERS_LICENCE, ...
COMPANY = "Burnt & Toast Studios"
SERVICE_URL = "https://packs.burntandtoast.com"    # CLI-facing: licence API, pack files (server/)
SITE_URL = "https://lastorders.burntandtoast.com"  # customer-facing: landing page, buy, terms
PACKS_URL = f"{SERVICE_URL}/v1"
LICENCE_URL = f"{SERVICE_URL}/api/licence/verify"   # override: $LASTORDERS_LICENCE_URL
BUY_URL = f"{SITE_URL}/buy"                         # Stripe Checkout (append ?repo=github.com/owner/name to prefill)
TERMS_URL = f"{SITE_URL}/terms"                     # licence terms and refund policy
CACHE_DIR_NAME = CLI_NAME


def env_name(key: str) -> str:
    return f"{ENV_PREFIX}_{key}"


def env(key: str, default: str = "") -> str:
    return os.environ.get(env_name(key), default)
