import httpx
import pytest

from mednexus.integrations.fhir import FHIRClient, FHIRIntegrationError


@pytest.mark.anyio
async def test_fhir_client_validates_resource_type_and_origin():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer test-token"
        return httpx.Response(
            200,
            headers={"content-type": "application/fhir+json"},
            json={"resourceType": "Patient", "id": "example", "active": True},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        client = FHIRClient("https://ehr.example/FHIR/R4", "test-token", client=http)
        resource = await client.read("Patient", "example")

    assert resource.resourceType == "Patient"
    with pytest.raises(ValueError, match="not allowlisted"):
        await client.read("Binary", "example")
    with pytest.raises(ValueError, match="invalid FHIR resource id"):
        await client.read("Patient", "../secret")


@pytest.mark.anyio
async def test_fhir_client_rejects_cross_origin_pagination():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"content-type": "application/fhir+json"},
            json={
                "resourceType": "Bundle",
                "type": "searchset",
                "link": [{"relation": "next", "url": "https://attacker.example/next"}],
            },
        )
    )
    async with httpx.AsyncClient(transport=transport) as http:
        client = FHIRClient("https://ehr.example/FHIR/R4", "test-token", client=http)
        with pytest.raises(FHIRIntegrationError, match="approved origin"):
            await client.search("Observation", {"patient": "example"})
