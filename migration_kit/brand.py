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
PACKS_URL = "https://packs.burntandtoast.com/v1"   # planned; NOT deployed yet
LICENCE_URL = ""                                   # phase 2: licence-check endpoint (empty = no network check)
BUY_URL = "https://burntandtoast.com"              # phase 2: Stripe checkout link
CACHE_DIR_NAME = CLI_NAME


def env_name(key: str) -> str:
    return f"{ENV_PREFIX}_{key}"


def env(key: str, default: str = "") -> str:
    return os.environ.get(env_name(key), default)
