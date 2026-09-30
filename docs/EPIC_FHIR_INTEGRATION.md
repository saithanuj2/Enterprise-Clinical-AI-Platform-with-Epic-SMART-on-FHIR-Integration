# Epic SMART on FHIR R4 integration

## Status

MedNexus contains a sandbox-ready Epic SMART App Launch foundation. It is disabled by default and must not receive live PHI until the deployment has completed the security, legal, and operational controls in `HIPAA_READINESS.md`.

Implemented controls:

- SMART discovery from the configured FHIR R4 issuer.
- OAuth 2.0 authorization-code flow with PKCE, state, and nonce.
- Exact issuer and discovered-endpoint origin allowlisting.
- Single-use launch state with a ten-minute expiry.
- Fernet-encrypted launch state and access tokens in Redis.
- Opaque HttpOnly, SameSite session cookies; access tokens never enter browser JavaScript.
- Allowlisted `Patient`, `Encounter`, and `Observation` resource reads.
- FHIR JSON resource validation, bounded pagination, and next-link origin validation.
- Safe errors that do not include tokens, response bodies, or patient content.

## Epic registration required

Create a non-production application in Epic on FHIR. Register this callback exactly:

```text
http://localhost:8000/api/v1/integrations/epic/callback
```

Use the non-production client ID for the Epic sandbox. Do not commit the client ID, encryption key, access token, refresh token, or customer endpoint.

## Local configuration

Generate a state-encryption key:

```powershell
.\.venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Add the resulting value and Epic client ID to the untracked `.env` file:

```dotenv
EPIC_SMART_ENABLED=true
EPIC_CLIENT_ID=your-non-production-client-id
EPIC_STATE_ENCRYPTION_KEY=your-generated-fernet-key
EPIC_FHIR_BASE_URL=https://fhir.epic.com/interconnect-fhir-oauth/api/FHIR/R4
EPIC_REDIRECT_URI=http://localhost:8000/api/v1/integrations/epic/callback
WEB_BASE_URL=http://localhost:5173
```

Restart the API, open `/ehr`, and select **Connect to Epic**. Redis must be running because launch state and access tokens are never stored in the browser or process memory.

## Production requirements

- Register the production HTTPS redirect URI separately with Epic.
- Set a customer-specific Epic FHIR base URL and allow only that exact issuer.
- Store the encryption key in a managed secret/KMS system and rotate it under a documented procedure.
- Run Redis with TLS, authentication, persistence controls, private networking, and an approved retention policy.
- Validate requested SMART scopes with the healthcare organization and use the minimum necessary permissions.
- Add verified OpenID Connect ID-token validation if MedNexus uses Epic identity for application login.
- Complete Epic customer testing and organizational approval before live use.
