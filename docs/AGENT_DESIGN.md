# Controlled Agent Design

`POST /api/v1/agent/query` is a bounded router, not a free-running agent. It can retrieve clinical context and obtain a patient summary when an explicit subject ID is supplied. Inputs are schema-validated, execution is capped at one deterministic iteration, tools executed are returned, and every response includes an audit ID and evidence citations.

There is no arbitrary SQL tool, shell access, autonomous diagnosis, or silent unsupported answer. Future approved analytics must use named parameterized query templates.
