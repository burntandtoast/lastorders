# Publishing checklist (nothing below has been done yet)

Everything is built and tested locally. Nothing has been pushed, published or deployed.

## 1. Name (decided 15 Oct 2026)
The product is **Last Orders**. The package, CLI and PyPI name is `lastorders`, and the env vars are `LASTORDERS_*`.
`lastorders`, `last-orders` and `last_orders` were all unregistered on PyPI on 15 Oct 2026
(`https://pypi.org/pypi/<name>/json` returned 404). That can change at any time, so set up the pending
publisher (section 3) promptly; it reserves the name on first upload. PyPI can still refuse a name it thinks is
too similar to an existing project, and only an upload settles that.
To rename again: `python scripts/rename_product.py "New Name" newname`, then `pytest -q`.

## 2. GitHub repo
- A public repo `burntandtoast/lastorders` (needed for `uses: burntandtoast/lastorders@v0`). `action.yml` must be at the root.
  If the repo lives elsewhere, update the owner and repo in section 3 and in the README's `uses:` lines.
- Choose a licence and fill in `license` in `pyproject.toml` plus a `LICENSE` file. If the paid features
  should stay closed, consider source-available, or split them into a private package later.
- Tag `v0.4.0` and move the major tag `v0` to it. Optionally list it on the GitHub Marketplace (needs `branding`, which is already in action.yml).

## 3. PyPI with Trusted Publishing (no API token, ever)
`.github/workflows/release.yml` publishes using GitHub's OIDC identity. PyPI trusts that one workflow in that one
repo, so there's no `PYPI_API_TOKEN` to create, store, share or leak. Setup, all in web UIs:

1. **PyPI account** for Leigh (or a Burnt & Toast org account), with 2FA on. Optionally create a PyPI
   *Organisation* so that teammates can be added later without sharing logins.
2. **Pending publisher on PyPI:** go to https://pypi.org/manage/account/publishing/ → "Add a new pending publisher" → GitHub, and enter:
   - PyPI project name: `lastorders`
   - Owner: `burntandtoast` (the GitHub org/user that will own the repo)
   - Repository name: `lastorders`
   - Workflow name: `release.yml`
   - Environment name: `pypi`

   The project is created, and the name claimed, on the first successful upload.
3. **The same on TestPyPI** (a separate account): go to https://test.pypi.org/manage/account/publishing/ and enter the same values,
   but with the environment name `testpypi`.
4. **GitHub environments:** repo → Settings → Environments.
   - Create `testpypi`.
   - Create `pypi` with **Required reviewers: Leigh**, so every real release needs a click. Optionally restrict it to
     tags matching `v*`.
5. **Release:**
   1. Bump `__version__` in `migration_kit/__init__.py` and the CHANGELOG, then commit.
   2. `git tag v0.4.0 && git push origin v0.4.0`.
   3. The workflow tests, checks that the tag matches the version, checks that the licence public key is embedded, builds, uploads to TestPyPI and then waits for approval before uploading to PyPI.

   "Run workflow" in the Actions tab does a TestPyPI-only dry run.
6. **Check:** `pipx install lastorders && lastorders --version`. For TestPyPI, use
   `pip install -i https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ lastorders`;
   the extra index is needed because the dependencies aren't on TestPyPI.

If a token is ever needed (it shouldn't be), use a project-scoped one in a GitHub secret, never in chat or email.

## 4. Pack hosting (packs.burntandtoast.com)
```bash
lastorders packs build-site --out site
```
- **Default:** the licence-server Worker in `server/` serves `site/` as static assets, so one `wrangler deploy`
  covers packs and licensing. See [LICENCE-SERVER.md](LICENCE-SERVER.md).
- Alternatives for packs only: **Vercel** (root `site/`, no build, `vercel.json` sets headers) or
  **Cloudflare Pages** (output `site/`, `_headers`).
- Check: `curl https://packs.burntandtoast.com/v1/index.json`, then `lastorders packs list` should say `(remote)`.
- Updating a pack: bump `version`, run `packs validate`, rebuild the site, redeploy. Clients pick it up within 24 hours.

## 5. Licence service and Stripe
Built and tested locally in `server/` (Cloudflare Worker + D1). Follow [LICENCE-SERVER.md](LICENCE-SERVER.md) for
the Stripe keys, webhook settings, Resend, D1, secrets and the deploy steps. Before the first CLI release:
- [ ] `npm run keys`. Put the private key into `LICENCE_SIGNING_KEY` and the public key into `PUBLIC_KEYS` in `migration_kit/licence.py`.
- [ ] The Worker is deployed and `/healthz` responds at `brand.SERVICE_URL`.
- [ ] A test-mode purchase, verify, refund and revoke all work end to end.
