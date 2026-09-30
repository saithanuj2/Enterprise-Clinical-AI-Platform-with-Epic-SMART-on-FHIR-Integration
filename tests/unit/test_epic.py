from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from mednexus.integrations.epic import (
    EpicSmartIntegration,
    MemoryStateStore,
    SmartIntegrationError,
)

FHIR_BASE = "https://ehr.example/api/FHIR/R4"


def epic_transport(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/.well-known/smart-configuration"):
        return httpx.Response(
            200,
            json={
                "authorization_endpoint": "https://ehr.example/oauth2/authorize",
                "token_endpoint": "https://ehr.example/oauth2/token",
            },
        )
    if request.url.path == "/oauth2/token":
        body = request.content.decode()
        assert "code_verifier=" in body
        return httpx.Response(
            200,
            json={
                "access_token": "secret-access-token",
                "token_type": "Bearer",
                "expires_in": 300,
                "patient": "patient-1",
            },
        )
    raise AssertionError(f"unexpected request: {request.url}")


@pytest.mark.anyio
async def test_epic_smart_pkce_flow_uses_single_use_state():
    store = MemoryStateStore()
    async with httpx.AsyncClient(transport=httpx.MockTransport(epic_transport)) as http:
        integration = EpicSmartIntegration(
            fhir_base_url=FHIR_BASE,
            client_id="non-production-client",
            redirect_uri="https://app.example/callback",
            scopes="openid launch/patient patient/Patient.rs",
            store=store,
            http=http,
        )
        authorization_url = await integration.begin(issuer=FHIR_BASE, launch="launch-token")
        parameters = parse_qs(urlsplit(authorization_url).query)

        assert parameters["code_challenge_method"] == ["S256"]
        assert parameters["launch"] == ["launch-token"]
        assert "code_challenge" in parameters
        state = parameters["state"][0]
        session_id = await integration.complete(code="authorization-code", state=state)
        session = await store.get(f"session:{session_id}")

        assert session is not None
        assert session["patient"] == "patient-1"
        assert session["access_token"] == "secret-access-token"
        with pytest.raises(SmartIntegrationError, match="already used"):
            await integration.complete(code="authorization-code", state=state)


@pytest.mark.anyio
async def test_epic_smart_rejects_unapproved_issuer():
    integration = EpicSmartIntegration(
        fhir_base_url=FHIR_BASE,
        client_id="client",
        redirect_uri="https://app.example/callback",
        scopes="openid",
        store=MemoryStateStore(),
    )
    with pytest.raises(SmartIntegrationError, match="unapproved"):
        await integration.begin(issuer="https://attacker.example/FHIR/R4")
    await integration.close()
