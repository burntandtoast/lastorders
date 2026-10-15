# Publishing checklist (nothing below has been done yet)

Everything is built and tested locally. Nothing has been pushed, published or deployed.

## 1. Pick the name (once)
Candidates: Last Orders, Sunsetter, ModelMove. The placeholder is ModelMigrate / `modelmigrate`.
```bash
python scripts/rename_product.py "Sunsetter" sunsetter   # rewrites brand.py, pyproject, action, workflows, docs, tests
pytest -q
```
PyPI names checked free on 15 Oct 2026: modelmigrate, model-migrate, modelmove, sunsetter, last-orders,
lastorders. This can change at any time, so register promptly.
`ENV_PREFIX` also changes the env vars (for example `SUNSETTER_OFFLINE`).

## 2. GitHub repo
- A public repo, e.g. `burntandtoast/<name>` (needed for `uses: burntandtoast/<name>@v0`). `action.yml` must be at the root.
- Choose a licence and fill in `license` in `pyproject.toml` plus a `LICENSE` file. If the paid features
  should stay closed, consider source-available, or split them into a private package later.
- Tag `v0.2.0` and move the major tag `v0` to it. Optionally list it on the GitHub Marketplace (needs `branding`, which is already in action.yml).

## 3. PyPI
- Create a PyPI account (2FA required) and register the project with **Trusted Publishing** from GitHub Actions
  (no API token stored).
- Add a release workflow: build with `python -m build`, then `pypa/gh-action-pypi-publish`.
- Test on TestPyPI first. The version comes from `migration_kit/__init__.py`.

## 4. Pack hosting (packs.burntandtoast.com)
```bash
modelmigrate packs build-site --out site
```
- **Vercel:** new project, root `site/`, no build command, framework "Other". `vercel.json` sets the headers.
- **Cloudflare Pages:** output dir `site/`. `_headers` sets the headers.
- DNS: CNAME `packs` → the Vercel or Pages target, in the burntandtoast.com zone.
- Check: `curl https://packs.burntandtoast.com/v1/index.json`, then `modelmigrate packs list` should say `(remote)`.
- Updating a pack: bump `version`, run `packs validate`, rebuild the site, redeploy. Clients pick it up within 24 hours.

## 5. Licence service (with Stripe, later)
- `migration_kit/licence.py` is a **placeholder** that only checks the format. Replace `check()` with a call to
  `brand.LICENCE_URL`. Send only the key and the repo identity (`host/owner/repo`), as the network policy promises.
- Stripe Checkout: £99–£249 per repo. A webhook issues the key and binds it to the repo at first activation.
