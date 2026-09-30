# HIPAA readiness boundary

## What the repository can provide

The application can supply technical safeguards and evidence: authenticated access, authorization, audit events, integrity controls, transmission-security configuration, PHI-safe logging, secure secrets, tests, deployment controls, and recovery procedures.

The Epic integration currently adds secure authorization foundations, encrypted server-side token storage, resource allowlisting, and a deidentified-by-default operating mode. These are readiness controls; they are not a certification.

## What code cannot provide by itself

HIPAA applicability and compliance depend on the operating organization and deployment. Before ePHI is used, the responsible organization must complete and maintain at least:

- a documented risk analysis and risk-management plan;
- administrative, physical, and technical safeguard decisions;
- workforce access policies and training;
- business associate agreements with applicable service providers;
- incident response and breach-notification procedures;
- contingency, backup, restoration, and emergency-mode procedures;
- device, media, retention, and disposal controls;
- periodic access and audit review;
- documented evaluations and evidence retention.

## Current gate

`live_phi_allowed` remains `false`. MedNexus must continue using synthetic or properly deidentified test data until an accountable security/compliance owner accepts the deployment controls and changes this gate through a reviewed production release. Documentation must continue to say **HIPAA-ready technical foundation**, not **HIPAA compliant**, until that determination is formally supported.
