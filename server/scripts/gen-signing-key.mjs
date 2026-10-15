// Generate the Ed25519 licence-token signing key.
//   node scripts/gen-signing-key.mjs [kid]
// Prints: (1) the private JSON for `wrangler secret put LICENCE_SIGNING_KEY` and
//         (2) the public entry to paste into migration_kit/licence.py PUBLIC_KEYS.
// Nothing is written to disk.
const kid = process.argv[2] || `k${new Date().toISOString().slice(0, 10).replace(/-/g, "")}`;
const { privateKey } = await crypto.subtle.generateKey({ name: "Ed25519" }, true, ["sign", "verify"]);
const jwk = await crypto.subtle.exportKey("jwk", privateKey);
const secret = JSON.stringify({ kid, d: jwk.d, x: jwk.x });
console.error("# 1) Private signing key. Store it as a Worker secret, then clear your terminal scrollback:");
console.error("#    wrangler secret put LICENCE_SIGNING_KEY   (paste the next line)");
console.log(secret);
console.error("\n# 2) Public key: add to PUBLIC_KEYS in migration_kit/licence.py (safe to commit):");
console.error(`#    "${kid}": "${jwk.x}",`);
