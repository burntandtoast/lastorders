"""Product naming in ONE place. The product name is undecided (candidates: Last Orders,
Sunsetter, ModelMove), so everything user-visible reads from here.

To rename: run `python scripts/rename_product.py "New Name" newcli` which updates this
file plus the static places Python can't read at build time (pyproject.toml, action.yml,
workflows, README)."""
import os

PRODUCT_NAME = "ModelMigrate"          # working title / placeholder
CLI_NAME = "modelmigrate"              # console command + PyPI distribution name
ENV_PREFIX = "MODELMIGRATE"            # env vars: MODELMIGRATE_OFFLINE, MODELMIGRATE_LICENCE, ...
COMPANY = "Burnt & Toast Studios"
SERVICE_URL = "https://packs.burntandtoast.com"    # planned host of server/ (pack site + licence API); NOT deployed yet
PACKS_URL = f"{SERVICE_URL}/v1"
LICENCE_URL = f"{SERVICE_URL}/api/licence/verify"   # override: $MODELMIGRATE_LICENCE_URL
BUY_URL = f"{SERVICE_URL}/buy"                      # Stripe Checkout (append ?repo=github.com/owner/name to prefill)
CACHE_DIR_NAME = CLI_NAME


def env_name(key: str) -> str:
    return f"{ENV_PREFIX}_{key}"


def env(key: str, default: str = "") -> str:
    return os.environ.get(env_name(key), default)
