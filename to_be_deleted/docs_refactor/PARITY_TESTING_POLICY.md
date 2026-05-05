# Parity Testing Policy

- Legacy requests run against the real `app.main:app`.
- Refactored requests run on an isolated test `FastAPI` instance that mounts only the refactored router under test.
- Auth-required parity uses shared fake user overrides from `tests/refactor_parity/conftest.py`.
- Read endpoints must match status and normalized JSON payloads.
- Write endpoints use rollback-backed parity where safe; otherwise they use status + response shape parity only and are flagged for manual DB-effect verification.
- Dynamic fields (timestamps, IDs, signed URLs, tokens) are normalized before equality checks.

