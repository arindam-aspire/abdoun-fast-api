# 08 — Migrate Uploads and Media URL Workflows

## Goal
Rebuild upload and media URL signing workflows.

## Cursor Prompt

```md
Migrate uploads/media functionality into app_refactored/domains/uploads.

Legacy capabilities:
- POST /api/v1/uploads/presigned-url
- profile picture upload workflow if implemented under auth/profile
- media URL signing used by listing/user outputs

Rules:
1. Preserve auth requirements.
2. Preserve environment/config-driven upload constraints.
3. Do not actually upload to S3 in tests.
4. Mock S3 client/presigner for parity tests.
5. Normalize signed URL dynamic query parameters before comparing.
6. Keep response shape identical.
7. Add startup flag use_refactored_uploads, default false.
8. Update coverage checklist.

Completion checks:
- pytest tests/refactor_parity/test_uploads_parity.py -q
- pytest tests/smoke/ -q
- python scripts/check_contract_drift.py
```
