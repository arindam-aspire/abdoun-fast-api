# 03 — Build Parity Test Harness

## Goal
Create a reusable parity test framework that can compare legacy and refactored implementations safely.

## Cursor Prompt

```md
Create tests/refactor_parity/ with a concrete parity harness.

Files:
1. tests/refactor_parity/conftest.py
2. tests/refactor_parity/parity_client.py
3. tests/refactor_parity/assertions.py
4. tests/refactor_parity/auth_overrides.py
5. tests/refactor_parity/test_harness_self_check.py

Requirements:
- Use the real app.main:app for legacy route calls.
- For refactored domain calls, use APIRouter mounted into a temporary test FastAPI app, not production app.main.
- Implement fake_current_user dependency override usable by both legacy and refactored routes.
- Create helpers:
  - assert_status_parity()
  - assert_json_shape_parity()
  - assert_response_headers_parity(optional=True)
  - normalize_dynamic_fields() for timestamps, ids, signed URLs, tokens
- Write endpoint classification:
  - READ_ONLY: compare status + normalized JSON
  - AUTH_REQUIRED_READ: compare using fake user override
  - WRITE_WITH_ROLLBACK: run inside rollback transaction if available
  - WRITE_SHAPE_ONLY: compare status + response shape only and add note to MISSING_FUNCTIONALITY_REGISTER if DB effect cannot be safely tested
- Create docs/refactor/PARITY_TESTING_POLICY.md explaining the strategy.

Do not migrate any domain yet.

Completion checks:
- pytest tests/refactor_parity/test_harness_self_check.py -q
- python -c "from app.main import app"
```
