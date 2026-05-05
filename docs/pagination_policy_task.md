# Pagination Policy + Full Implementation Task (Cursor AI)

You are a senior FastAPI + SQLAlchemy architect working on a live application.

## Goal

Create a formal pagination policy first, then implement it consistently across all paginated endpoints.

## Critical rules

- Do not change route paths or HTTP methods.
- Do not remove old query params immediately.
- Keep backward-compatible aliases where they already exist.
- Do not pass `sortBy` directly into SQL.
- Use allow-listed sort fields only.
- If an endpoint response change affects frontend, document it clearly.
- Run tests after each endpoint group.

---

## Standard to implement

### Request standard

External API:

page=1  
pageSize=20  
sortBy=createdAt  
sortOrder=desc  

Internal Python:

page  
page_size  
sort_by  
sort_order  
offset  
limit  

---

### Response standard

{
  "items": [],
  "total": 125,
  "page": 1,
  "pageSize": 20,
  "totalPages": 7,
  "hasNext": true,
  "hasPrevious": false
}

If endpoint uses StandardResponse, wrap under data.

---

## Steps

### Step 1 — Write policy document

Create:
docs/refactor/PAGINATION_POLICY.md

Include:
- Purpose
- Request format
- Internal format
- Response format
- Sorting rules
- Backward compatibility rules
- Deprecation rules
- Examples

---

### Step 2 — Inventory endpoints

Create:
docs/refactor/PAGINATION_ENDPOINT_INVENTORY.md

Columns:
| Endpoint | File | Params | Response | Sorting | Risk | Decision |

---

### Step 3 — Create shared module

app/domains/shared/pagination.py

Include:
- PageParams
- SortParams
- PaginationCalc
- PaginatedResponse
- calculate_pagination()
- build_paginated_response()

---

### Step 4 — Sorting helper

Add allowlist-based sort resolver.

---

### Step 5 — Unit tests

tests/unit/shared/test_pagination.py

Cover:
- page calculations
- edge cases
- response aliasing
- sort validation

---

### Step 6 — Implement in groups

Group A (low risk):
- users
- agents
- admin
- submissions

Group B (medium):
- favorites
- saved searches
- recent views

Group C (high):
- properties
- geo-search

---

### Step 7 — Compatibility

- Keep limit/offset aliases
- Prefer page/pageSize
- Document deprecation

---

### Step 8 — Frontend impact

Create:
docs/refactor/PAGINATION_FRONTEND_IMPACT.md

---

### Step 9 — Validation

Run:

python -c "from app.main import app"  
pytest tests/unit/shared/test_pagination.py -q  
pytest tests/smoke/ -q  
pytest tests/refactor_parity/ -q  

---

### Step 10 — Final report

Update PAGINATION_POLICY.md with:
- migrated endpoints
- pending endpoints
- frontend impact
- TODOs

---

## Done criteria

- Policy created
- Inventory created
- Shared helper implemented
- Tests passing
- Endpoints standardized or documented
- Frontend impact documented
- No unsafe SQL sorting
