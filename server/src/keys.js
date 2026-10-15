// Licence keys and signed verification tokens.
import { b64url, b64urlDecode, enc } from "./util.js";

// 32 symbols: A-Z without I and O, plus 2-9 (no 0/1), so keys survive being read aloud. 60 bits per key.
const ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
export const KEY_RE = /^BTM-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$/;

export function generateKey() {
  const out = [];
  const buf = new Uint8Array(24);
  crypto.getRandomValues(buf);
  let i = 0;
  while (out.length < 12) {
    if (i >= buf.length) { crypto.getRandomValues(buf); i = 0; }
    const v = buf[i++];
    if (v < 256 - (256 % ALPHABET.length)) out.push(ALPHABET[v % ALPHABET.length]);   // no modulo bias
  }
  return `BTM-${out.slice(0, 4).join("")}-${out.slice(4, 8).join("")}-${out.slice(8).join("")}`;
}

// LICENCE_SIGNING_KEY secret: JSON {"kid": "...", "d": <b64url 32-byte seed>, "x": <b64url public>} (see scripts/gen-signing-key.mjs)
export async function loadSigningKey(secret) {
  if (!secret) throw new Error("LICENCE_SIGNING_KEY is not configured");
  const j = typeof secret === "string" ? JSON.parse(secret) : secret;
  const key = await crypto.subtle.importKey("jwk", { kty: "OKP", crv: "Ed25519", d: j.d, x: j.x }, { name: "Ed25519" }, false, ["sign"]);
  return { kid: j.kid, key, x: j.x };
}

// Token: "v1.<b64url(JSON payload)>.<b64url(Ed25519 signature over 'v1.<payload>')>"
export async function signToken(signing, payload) {
  const body = b64url(enc.encode(JSON.stringify({ ...payload, kid: signing.kid })));
  const msg = `v1.${body}`;
  const sig = await crypto.subtle.sign({ name: "Ed25519" }, signing.key, enc.encode(msg));
  return `${msg}.${b64url(sig)}`;
}

export async function verifyToken(token, publicX) {
  const [v, body, sig] = String(token).split(".");
  if (v !== "v1" || !body || !sig) return null;
  const pub = await crypto.subtle.importKey("jwk", { kty: "OKP", crv: "Ed25519", x: publicX }, { name: "Ed25519" }, false, ["verify"]);
  const ok = await crypto.subtle.verify({ name: "Ed25519" }, pub, b64urlDecode(sig), enc.encode(`v1.${body}`));
  return ok ? JSON.parse(new TextDecoder().decode(b64urlDecode(body))) : null;
}
