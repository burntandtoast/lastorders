// Run the Worker in plain Node with an in-memory D1 (sql.js) and a fake Stripe, for local trials and
// the Python end-to-end test. No Cloudflare account, Stripe keys or network needed.
//   node scripts/local-server.mjs [--port 0] [--issue N]
// Prints one JSON line: {"url", "public_keys": {kid: x}, "keys": [issued licence keys]}
import http from "node:http";
import { createApp } from "../src/index.js";
import { devSigningKey, fakeNetwork, makeEnv, paidSessionEvent, harness } from "../test/helpers.js";

const arg = (name, dflt) => { const i = process.argv.indexOf(name); return i > 0 ? process.argv[i + 1] : dflt; };
const port = Number(arg("--port", "0"));
const issueN = Number(arg("--issue", "1"));

const signing = await devSigningKey("dev");
const net = fakeNetwork();
const env = await makeEnv({ LICENCE_SIGNING_KEY: JSON.stringify(signing), EMAIL_PROVIDER: "none", PUBLIC_BASE_URL: "" });
const h = harness(env, net);
const keys = [];
for (let i = 0; i < issueN; i++) {
  const id = `cs_test_local${i}`;
  await h.webhook(paidSessionEvent(id, { email: `buyer${i}@example.com`, pi: `pi_local${i}` }));
  keys.push((await env.DB.prepare("SELECT key FROM licences WHERE stripe_session_id = ?").bind(id).first()).key);
}
const app = createApp({ fetch: net.fetch });

const server = http.createServer(async (req, res) => {
  const chunks = [];
  for await (const c of req) chunks.push(c);
  const url = `http://${req.headers.host}${req.url}`;
  const init = { method: req.method, headers: req.headers };
  if (!["GET", "HEAD"].includes(req.method)) init.body = Buffer.concat(chunks);
  const r = await app.fetch(new Request(url, init), { ...env, PUBLIC_BASE_URL: `http://${req.headers.host}` });
  res.writeHead(r.status, Object.fromEntries(r.headers));
  res.end(Buffer.from(await r.arrayBuffer()));
});
server.listen(port, "127.0.0.1", () => {
  const { port: p } = server.address();
  console.log(JSON.stringify({ url: `http://127.0.0.1:${p}`, public_keys: { [signing.kid]: signing.x }, keys }));
});
