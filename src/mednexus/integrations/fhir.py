"""Defensive FHIR R4 client primitives for approved EHR endpoints."""

from __future__ import annotations

import re
from typing import Any, Literal
from urllib.parse import urljoin, urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field

FHIR_JSON = "application/fhir+json"
FHIR_ID = re.compile(r"^[A-Za-z0-9\-.]{1,64}$")


class FHIRIntegrationError(RuntimeError):
    """Raised when an EHR response violates the expected FHIR contract."""


class FHIRResource(BaseModel):
    model_config = ConfigDict(extra="allow")

    resourceType: str
    id: str | None = None


class PatientResource(FHIRResource):
    resourceType: Literal["Patient"]


class EncounterResource(FHIRResource):
    resourceType: Literal["Encounter"]


class ObservationResource(FHIRResource):
    resourceType: Literal["Observation"]


class BundleLink(BaseModel):
    relation: str
    url: str


class BundleEntry(BaseModel):
    resource: dict[str, Any]


class FHIRBundle(BaseModel):
    resourceType: Literal["Bundle"]
    type: str | None = None
    entry: list[BundleEntry] = Field(default_factory=list)
    link: list[BundleLink] = Field(default_factory=list)


RESOURCE_MODELS: dict[str, type[FHIRResource]] = {
    "Patient": PatientResource,
    "Encounter": EncounterResource,
    "Observation": ObservationResource,
}


class FHIRClient:
    """Small FHIR R4 client with resource allowlisting and bounded pagination."""

    def __init__(
        self,
        base_url: str,
        access_token: str,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        parsed = urlsplit(base_url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username:
            raise ValueError("FHIR base URL must be an HTTPS origin without credentials")
        self.base_url = base_url.rstrip("/") + "/"
        self._origin = (parsed.scheme, parsed.netloc)
        self._headers = {"Authorization": f"Bearer {access_token}", "Accept": FHIR_JSON}
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(15.0),
            follow_redirects=False,
        )

    def _resource_url(self, resource_type: str, resource_id: str | None = None) -> str:
        if resource_type not in RESOURCE_MODELS:
            raise ValueError(f"FHIR resource is not allowlisted: {resource_type}")
        path = resource_type
        if resource_id is not None:
            if not FHIR_ID.fullmatch(resource_id):
                raise ValueError("invalid FHIR resource id")
            path += f"/{resource_id}"
        return urljoin(self.base_url, path)

    def _validate_page_url(self, url: str) -> str:
        parsed = urlsplit(url)
        if (parsed.scheme, parsed.netloc) != self._origin:
            raise FHIRIntegrationError("FHIR pagination attempted to leave the approved origin")
        return url

    async def _get(self, url: str, *, params: dict[str, str] | None = None) -> dict[str, Any]:
        response = await self._client.get(url, params=params, headers=self._headers)
        if response.status_code >= 400:
            request_id = response.headers.get("X-Request-ID", "unavailable")
            raise FHIRIntegrationError(
                f"FHIR request failed with {response.status_code}; request_id={request_id}"
            )
        content_type = response.headers.get("content-type", "")
        if "json" not in content_type:
            raise FHIRIntegrationError("FHIR endpoint returned a non-JSON response")
        body = response.json()
        if not isinstance(body, dict):
            raise FHIRIntegrationError("FHIR endpoint returned an invalid JSON document")
        return body

    async def read(self, resource_type: str, resource_id: str) -> FHIRResource:
        body = await self._get(self._resource_url(resource_type, resource_id))
        model = RESOURCE_MODELS[resource_type]
        return model.model_validate(body)

    async def search(
        self,
        resource_type: str,
        parameters: dict[str, str],
        *,
        max_pages: int = 5,
    ) -> list[FHIRResource]:
        if not 1 <= max_pages <= 20:
            raise ValueError("max_pages must be between 1 and 20")
        url = self._resource_url(resource_type)
        params: dict[str, str] | None = parameters
        resources: list[FHIRResource] = []
        model = RESOURCE_MODELS[resource_type]
        for _ in range(max_pages):
            bundle = FHIRBundle.model_validate(await self._get(url, params=params))
            params = None
            resources.extend(model.model_validate(item.resource) for item in bundle.entry)
            next_link = next((item.url for item in bundle.link if item.relation == "next"), None)
            if not next_link:
                break
            url = self._validate_page_url(next_link)
        return resources

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()
