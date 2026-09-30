"""Epic SMART on FHIR R4 authorization-code flow with PKCE."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from dataclasses import asdict, dataclass
from typing import Any, Protocol
from urllib.parse import urlencode, urlsplit

import httpx
from cryptography.fernet import Fernet, InvalidToken
from pydantic import BaseModel, HttpUrl
from redis.asyncio import Redis

from mednexus.integrations.fhir import FHIRClient, FHIRResource


class SmartIntegrationError(RuntimeError):
    """A safe-to-log SMART integration failure without tokens or PHI."""


class SmartDiscovery(BaseModel):
    authorization_endpoint: HttpUrl
    token_endpoint: HttpUrl


class StateStore(Protocol):
    async def put(self, key: str, value: dict[str, Any], ttl_seconds: int) -> None: ...
    async def get(self, key: str) -> dict[str, Any] | None: ...
    async def pop(self, key: str) -> dict[str, Any] | None: ...


class MemoryStateStore:
    """Test-only state store. Production deployments must use shared encrypted storage."""

    def __init__(self) -> None:
        self._items: dict[str, tuple[float, dict[str, Any]]] = {}

    async def put(self, key: str, value: dict[str, Any], ttl_seconds: int) -> None:
        self._items[key] = (time.time() + ttl_seconds, value)

    async def get(self, key: str) -> dict[str, Any] | None:
        item = self._items.get(key)
        if not item or item[0] <= time.time():
            self._items.pop(key, None)
            return None
        return item[1]

    async def pop(self, key: str) -> dict[str, Any] | None:
        value = await self.get(key)
        self._items.pop(key, None)
        return value


class EncryptedRedisStateStore:
    """Encrypt SMART launch state and tokens before storage in Redis."""

    def __init__(self, redis: Redis, encryption_key: str, prefix: str = "mednexus:smart") -> None:
        self._redis = redis
        self._fernet = Fernet(encryption_key.encode())
        self._prefix = prefix

    def _key(self, key: str) -> str:
        return f"{self._prefix}:{key}"

    def _encrypt(self, value: dict[str, Any]) -> bytes:
        return self._fernet.encrypt(json.dumps(value, separators=(",", ":")).encode())

    def _decrypt(self, value: bytes) -> dict[str, Any]:
        try:
            decoded = json.loads(self._fernet.decrypt(value))
        except (InvalidToken, json.JSONDecodeError) as exc:
            raise SmartIntegrationError("stored SMART session is invalid") from exc
        if not isinstance(decoded, dict):
            raise SmartIntegrationError("stored SMART session is malformed")
        return decoded

    async def put(self, key: str, value: dict[str, Any], ttl_seconds: int) -> None:
        await self._redis.set(self._key(key), self._encrypt(value), ex=ttl_seconds)

    async def get(self, key: str) -> dict[str, Any] | None:
        value = await self._redis.get(self._key(key))
        return None if value is None else self._decrypt(value)

    async def pop(self, key: str) -> dict[str, Any] | None:
        value = await self._redis.getdel(self._key(key))
        if value is None:
            return None
        return self._decrypt(value)


@dataclass(frozen=True)
class LaunchState:
    issuer: str
    code_verifier: str
    nonce: str
    created_at: float


class EpicSmartIntegration:
    """Perform SMART discovery, PKCE launch, token exchange, and FHIR reads."""

    def __init__(
        self,
        *,
        fhir_base_url: str,
        client_id: str,
        redirect_uri: str,
        scopes: str,
        store: StateStore,
        session_ttl_seconds: int = 3600,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self.fhir_base_url = fhir_base_url.rstrip("/")
        self.client_id = client_id
        self.redirect_uri = redirect_uri
        self.scopes = scopes
        self.store = store
        self.session_ttl_seconds = session_ttl_seconds
        self._owns_http = http is None
        self.http = http or httpx.AsyncClient(timeout=15.0, follow_redirects=False)

    def _validate_issuer(self, issuer: str) -> str:
        normalized = issuer.rstrip("/")
        parsed = urlsplit(normalized)
        approved = urlsplit(self.fhir_base_url)
        if parsed.scheme != "https" or parsed.username or normalized != self.fhir_base_url:
            raise SmartIntegrationError("unapproved SMART issuer")
        if parsed.netloc != approved.netloc:
            raise SmartIntegrationError("SMART issuer origin mismatch")
        return normalized

    async def discover(self, issuer: str) -> SmartDiscovery:
        approved = self._validate_issuer(issuer)
        response = await self.http.get(
            f"{approved}/.well-known/smart-configuration",
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        discovery = SmartDiscovery.model_validate(response.json())
        issuer_origin = urlsplit(approved).netloc
        for endpoint in (str(discovery.authorization_endpoint), str(discovery.token_endpoint)):
            parsed = urlsplit(endpoint)
            if parsed.scheme != "https" or parsed.netloc != issuer_origin:
                raise SmartIntegrationError("SMART discovery returned an unapproved endpoint")
        return discovery

    async def begin(self, *, issuer: str, launch: str | None = None) -> str:
        approved = self._validate_issuer(issuer)
        discovery = await self.discover(approved)
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        launch_state = LaunchState(approved, verifier, nonce, time.time())
        await self.store.put(f"launch:{state}", asdict(launch_state), 600)
        parameters = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": self.scopes,
            "aud": approved,
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        if launch:
            parameters["launch"] = launch
        return f"{discovery.authorization_endpoint}?{urlencode(parameters)}"

    async def complete(self, *, code: str, state: str) -> str:
        raw_state = await self.store.pop(f"launch:{state}")
        if raw_state is None:
            raise SmartIntegrationError("SMART state is missing, expired, or already used")
        launch_state = LaunchState(**raw_state)
        discovery = await self.discover(launch_state.issuer)
        response = await self.http.post(
            str(discovery.token_endpoint),
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.redirect_uri,
                "client_id": self.client_id,
                "code_verifier": launch_state.code_verifier,
            },
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        token = response.json()
        if not isinstance(token, dict) or not token.get("access_token"):
            raise SmartIntegrationError("Epic token response did not include an access token")
        if str(token.get("token_type", "Bearer")).lower() != "bearer":
            raise SmartIntegrationError("Epic returned an unsupported token type")
        session_id = secrets.token_urlsafe(32)
        session = {
            "issuer": launch_state.issuer,
            "access_token": token["access_token"],
            "patient": token.get("patient"),
            "encounter": token.get("encounter"),
            "scope": token.get("scope", ""),
        }
        expires_in = min(int(token.get("expires_in", self.session_ttl_seconds)), self.session_ttl_seconds)
        await self.store.put(f"session:{session_id}", session, max(60, expires_in))
        return session_id

    async def read_resource(
        self, session_id: str, resource_type: str, resource_id: str
    ) -> FHIRResource:
        session = await self.store.get(f"session:{session_id}")
        if session is None:
            raise SmartIntegrationError("Epic session is missing or expired")
        client = FHIRClient(str(session["issuer"]), str(session["access_token"]))
        try:
            return await client.read(resource_type, resource_id)
        finally:
            await client.close()

    async def close(self) -> None:
        if self._owns_http:
            await self.http.aclose()
