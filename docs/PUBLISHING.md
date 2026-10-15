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
- Tag `v0.4.0` and move the major tag `v0` to it. Optionally list it on the GitHub Marketplace (needs `branding`, which is already in action.yml).

## 3. PyPI
- Create a PyPI account (2FA required) and register the project with **Trusted Publishing** from GitHub Actions
  (no API token stored).
- Add a release workflow: build with `python -m build`, then `pypa/gh-action-pypi-publish`.
- Test on TestPyPI first. The version comes from `migration_kit/__init__.py`.

## 4. Pack hosting (packs.burntandtoast.com)
```bash
modelmigrate packs build-site --out site
```
- **Default:** the licence-server Worker in `server/` serves `site/` as static assets, so one `wrangler deploy`
  covers packs and licensing. See [LICENCE-SERVER.md](LICENCE-SERVER.md).
- Alternatives for packs only: **Vercel** (root `site/`, no build, `vercel.json` sets headers) or
  **Cloudflare Pages** (output `site/`, `_headers`).
- Check: `curl https://packs.burntandtoast.com/v1/index.json`, then `modelmigrate packs list` should say `(remote)`.
- Updating a pack: bump `version`, run `packs validate`, rebuild the site, redeploy. Clients pick it up within 24 hours.

## 5. Licence service and Stripe
Built and tested locally in `server/` (Cloudflare Worker + D1). Follow [LICENCE-SERVER.md](LICENCE-SERVER.md) for
the Stripe keys, webhook settings, Resend, D1, secrets and the deploy steps. Before the first CLI release:
- [ ] `npm run keys`. Put the private key into `LICENCE_SIGNING_KEY` and the public key into `PUBLIC_KEYS` in `migration_kit/licence.py`.
- [ ] The Worker is deployed and `/healthz` responds at `brand.SERVICE_URL`.
- [ ] A test-mode purchase, verify, refund and revoke all work end to end.
