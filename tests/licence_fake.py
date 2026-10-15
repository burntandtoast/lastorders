"""In-process stand-in for the licence server (server/src/index.js verify endpoint) for CLI tests."""
from __future__ import annotations

import base64
import hashlib
import json
import time

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


class FakeLicenceServer:
    def __init__(self, kid: str = "test", ttl: int = 7 * 86400):
        self.kid, self.ttl = kid, ttl
        self._sk = Ed25519PrivateKey.generate()
        self.public_x = b64u(self._sk.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))
        self.keys: dict[str, dict] = {}       # key -> {"repo": str|None, "status": "active"|"revoked"}
        self.calls: list[dict] = []
        self.down = False
        self.clock = time.time

    def add(self, key: str, repo: str | None = None, status: str = "active"):
        self.keys[key] = {"repo": repo, "status": status}

    def token(self, key: str, repo: str, iat: int | None = None, ttl: int | None = None, **extra) -> str:
        iat = int(self.clock()) if iat is None else iat
        claims = {"v": 1, "iss": "fake", "lic": hashlib.sha256(key.encode()).hexdigest()[:32], "repo": repo, "plan": "repo",
                  "features": ["*"], "test": True, "iat": iat, "exp": iat + (self.ttl if ttl is None else ttl), "kid": self.kid, **extra}
        body = b64u(json.dumps(claims).encode())
        return f"v1.{body}.{b64u(self._sk.sign(f'v1.{body}'.encode()))}"

    def transport(self, url: str, payload: dict):
        from migration_kit.licence import _Unreachable
        self.calls.append({"url": url, "payload": dict(payload)})
        if self.down:
            raise _Unreachable("connection refused")
        key, repo = payload["key"], payload["repo"]
        rec = self.keys.get(key)
        if not rec:
            return 404, {"status": "not_found", "error": "unknown licence key"}
        if rec["status"] != "active":
            return 403, {"status": "revoked", "error": "licence revoked (refunded)"}
        if rec["repo"] is None:
            rec["repo"] = repo
        if rec["repo"] != repo:
            return 403, {"status": "bound_to_other_repo", "error": "bound", "bound_repo": rec["repo"]}
        return 200, {"status": "ok", "repo": repo, "token": self.token(key, repo)}
