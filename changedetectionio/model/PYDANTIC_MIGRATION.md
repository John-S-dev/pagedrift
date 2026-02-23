# Pydantic Migration

Plan for incrementally moving the app's storage dicts behind Pydantic models. Driven by
security (CWE-915 mass-assignment, see [GHSA-h3x5-5j56-hm2j][advisory]) and schema
enforcement, not just type tidying.

[advisory]: https://github.com/dgtlmoon/changedetection.io/security/advisories/GHSA-h3x5-5j56-hm2j

## The goal

Every form/API endpoint that mutates a stored dict should validate input against a
declared schema before writing. `extra='forbid'` rejects unknown keys — so an attacker
POSTing extra fields like `uuid=…`, `last_checked=…`, `history=[…]` can't smuggle them
into storage. Per-route allowlists work but rot; one declared schema per stored shape
doesn't.

## Prefer a migration over permanent complexity

