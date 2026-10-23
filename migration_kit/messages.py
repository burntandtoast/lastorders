"""User-facing copy for the free scan and the free fix/swap preview, in ONE place.

Edit the wording here; the code that prints it only fills in the {placeholders}. Product names and
URLs come from brand.py. Kept plain and neutral: no claims about automatic fixes. The paid licence
is "a reviewable patch plus a must-review list".

Links: passive output (terminal scan, scan.md, the Action job summary, the fix/swap preview) points
at the pricing section, never at /buy, because /buy creates a Checkout session when fetched.
`licence buy` and the "needs a licence" error print the /buy link, because the user asked to buy.
"""
from . import brand

PRICE = "£179"
SITE_SHORT = brand.SITE_URL.removeprefix("https://")          # lastorders.burntandtoast.com
PRICING_URL = f"{brand.SITE_URL}/#pricing"
PRICING_SHORT = f"{SITE_SHORT}/#pricing"
REMIND_URL = f"{brand.SITE_URL}/#remind"
REMIND_SHORT = f"{SITE_SHORT}/#remind"
CONTACT_EMAIL = "hello@burntandtoast.com"
DONE_FOR_YOU = "from £1,500"
CLI = brand.CLI_NAME

# ---------------------------------------------------------------- terminal: `scan`
# Rows shown in the terminal before "and N more in scan.md".
SCAN_MAX_ROWS = 5

SCAN_FOUND = "Found {n} retiring model {ids} in {files} {file_word} ({risks}). Fine-tunes: {fine_tunes}."
SCAN_SOONEST = "Soonest shutdown: {model} on {date}, in {days} {day_word}. Calls to it fail after that."
SCAN_ALREADY = "Already shut down: {model} on {date}. Calls to it fail now."
SCAN_ROW = "  {where:<{w1}}  {change:<{w2}}  {date}"
SCAN_MORE = "  and {n} more in {md}"
SCAN_REPORT = "Full report: {md} (and {json_name})"
SCAN_NEXT_STEPS = (
    "Next steps\n"
    "  See what the fix would change (free):  " + CLI + " fix {repo}\n"
    "  Get a reviewable patch plus a must-review list for this repo, " + PRICE + " one-off:\n"
    "  " + PRICING_SHORT)

SCAN_CLEAN_IDS = "Scanned {files} {file_word}: no retiring model IDs found. Nothing to do today."
SCAN_CLEAN_UNLISTED = "{n} model {ids} {is_are} not on any retirement list yet ({models}). Details: {md}"
SCAN_CLEAN_NONE = "Scanned {files} {file_word}: no AI model IDs found, so nothing here is retiring."
SCAN_CLEAN_BLIND_SPOT = ("The scan can't see model names built at runtime or stored in a database. "
                         "If you set the model that way, check its live value.")
SCAN_REMIND = "Want an email before the next shutdown date? " + REMIND_SHORT
SCAN_PARAM_ONLY = "{n} API parameter {item_word} to check (not a retiring model ID). Details: {md}"
SCAN_PACKS = "  packs: {packs}"      # printed with --verbose (always in scan.md)

# ---------------------------------------------------------------- scan.md and the Action job summary
MD_NEXT_STEPS = [
    "## Next steps",
    "",
    "- **See what the fix would change, free:** `" + CLI + " fix .` shows the real per-file count. It skips docs "
    "unless you pass `--include-docs`, and it leaves alone any ID it can't rename safely (for example where renaming "
    "would create a duplicate entry), so it can be smaller than the table above.",
    "- **Get the patch for this repo:** a reviewable patch plus a must-review list of anything it couldn't safely "
    "change, with a before-and-after report. " + PRICE + " one-off, tax included: <" + PRICING_URL + ">",
    "- **Or have us do it:** " + DONE_FOR_YOU + ". Email " + CONTACT_EMAIL + ".",
]
# {next} is filled from the packs' headline migrations, e.g. "Anthropic retires Claude Sonnet 4.5 on the
# Claude API, 30 November 2026".
MD_CLEAN = ("**No retiring model IDs found.** Nothing to do today. Next announced shutdown: {next}. "
            "Get an email before the next one: <" + REMIND_URL + ">")
MD_CLEAN_NO_NEXT = ("**No retiring model IDs found.** Nothing to do today. "
                    "Get an email before the next shutdown date: <" + REMIND_URL + ">")
SUMMARY_FOOTER = ("<sub>" + brand.PRODUCT_NAME + " free scan · scanned {scanned_on} · Reviewable patch plus "
                  "must-review list for this repo, " + PRICE + ": " + PRICING_SHORT + " · packs: {packs}</sub>")

# ---------------------------------------------------------------- `fix` / `swap` preview without a licence
PREVIEW_COUNT = "{n} {change_word} in {files} {file_word}. Anything the fix can't change safely goes on a must-review list instead of being guessed."
PREVIEW_PITCH = (
    "To get the reviewable patch plus the must-review list for this repo (" + PRICE + " one-off, tax included):\n"
    "  " + CLI + " licence buy          or  " + PRICING_SHORT + "\n"
    "Then run: " + CLI + " fix {repo} --verify --apply   and review the diff before you merge.")

# ---------------------------------------------------------------- paid command without a key
NEEDS_LICENCE_TAIL = ("The free `scan` needs no licence. A licence is " + PRICE + " per repo, one-off: run `"
                      + CLI + " licence buy` or go to " + brand.BUY_URL)

# ---------------------------------------------------------------- `--help`
HELP_SCAN = "free: find retiring model IDs in a repo"
HELP_FIX = "free preview of what would change; the reviewable patch needs a licence (" + PRICE + " per repo)"
HELP_SWAP = "free preview of model ID changes; the reviewable patch needs a licence (" + PRICE + " per repo)"
HELP_VERBOSE = "also print the migration packs used"


def plural(n: int, one: str, many: str | None = None) -> str:
    return one if n == 1 else (many or one + "s")
