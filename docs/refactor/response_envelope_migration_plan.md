# Full Project Response Envelope Migration Plan (Cursor AI)

You are a senior FastAPI + frontend integration architect.

This is a live FastAPI project with an existing frontend. We want to standardize response envelopes across the full backend, then produce a frontend impact log for FE migration.

---

## Critical rules

- Do NOT change route paths or HTTP methods.
- Do NOT change authentication behavior.
- Do NOT change DB schema.
- Do NOT remove old business fields.
- Do NOT start implementation before completing inventory and policy.
- Every endpoint change must be logged for frontend migration.
- Work endpoint group by endpoint group.
- After each group, run tests.
- If unsure whether frontend depends on an endpoint, mark it as `Needs FE verification`.

---

## Target response envelope

### Success response

{
  "success": true,
  "message": null,
  "data": {},
  "error": null,
  "meta": {}
}

### Paginated success response

{
  "success": true,
  "message": null,
  "data": {
    "items": []
  },
  "error": null,
  "meta": {
    "pagination": {
      "total": 0,
      "page": 1,
      "pageSize": 20,
      "totalPages": 0,
      "hasNext": false,
      "hasPrevious": false
    }
  }
}

### Error response

{
  "success": false,
  "message": "Human-readable message",
  "data": null,
  "error": {
    "code": "ERROR_CODE",
    "details": {}
  },
  "meta": {}
}

---

## Phase 1 — Identify and document first

Do not change source code in this phase.

Create:

docs/refactor/RESPONSE_ENVELOPE_POLICY.md  
docs/refactor/RESPONSE_ENVELOPE_ENDPOINT_INVENTORY.md  
docs/refactor/RESPONSE_ENVELOPE_FE_IMPACT_LOG.md  

---

## Phase 2 — Create shared response module

Create or update:

app/domains/shared/responses.py

---

## Phase 3 — Unit tests

Create:

tests/unit/shared/test_response_envelope.py

---

## Phase 4 — Migrate endpoint groups

Group 1 — Low risk  
Group 2 — Medium risk  
Group 3 — Authenticated  
Group 4 — High risk  
Group 5 — Auth  

---

## Phase 5 — Error envelope plan

Create:

docs/refactor/RESPONSE_ENVELOPE_ERROR_PLAN.md

---

## Phase 6 — Validation

Run:

python -c "from app.main import app"  
pytest tests/unit/shared/test_response_envelope.py -q  
pytest tests/smoke/ -q  
pytest tests/refactor_parity/ -q  

---

## Phase 7 — Final report

Create:

docs/refactor/RESPONSE_ENVELOPE_MIGRATION_SUMMARY.md

---

## Done criteria

- Policy created  
- Inventory created  
- FE impact log created  
- Shared response module implemented  
- Unit tests passing  
- Endpoints migrated or documented  
- No route changes  
- No auth changes  
- No DB changes  
