# Performance Audit — End-to-End Step-by-Step Refactor Plan

This document is the refactor plan for the **Performance Audit** section (lines **183–232**) of `FINAL_FASTAPI_BACKEND_AUDIT.md`. Each step is ordered so that dependencies are respected and changes can be validated incrementally. Validation decisions are taken from `FASTAPI_BACKEND_AUDIT_VALIDATION.md` lines **96–130** and repo performance standards from `.cursor/rules/03-database-performance.mdc`.

---

## Summary of Findings Addressed

| # | Finding | Risk | Fix |
|---|--------|------|-----|
| 1 | Property hash lookup full table scan (fetch all IDs + Python compare; \(O(n)\)) | Major bottleneck at scale | Add DB hash column + index; lookup in SQL |
| 2 | Database pool configuration missing | Connection exhaustion / stale connections / latency spikes in prod | Configure `pool_size`, `max_overflow`, `pool_timeout`, `pool_recycle`, `pool_pre_ping` via env vars |
| 3 | Synchronous DB engine | Potential scalability ceiling | **No change now** (design choice); revisit if needed |

---

## Step-by-Step Refactor Plan

### Step 1 — Fix Property Hash Lookup Full Table Scan

**Goal:** Remove \(O(n)\) Python-side scanning for property hash lookup.

**Actions (validated):**

1. Add a **hash column** to the properties table.
2. Add a **database index** on the hash column (indexing is explicitly recommended in `.cursor/rules/03-database-performance.mdc` for frequently filtered columns).
3. Update the lookup to **filter by hash in SQL** (avoid fetching all IDs and looping in Python).
4. Ensure the change is implemented in the proper layer boundaries (`.cursor/rules/00-master-fastapi.mdc`):
   - Route → Service → Repository → DB
   - DB access stays in the repository layer.

**Deliverables:** Hash lookup becomes indexed DB lookup (scales), and DB access remains repository-driven.

---

### Step 2 — Add Explicit Database Pool Configuration

**Goal:** Improve production stability and latency under load.

**Actions (validated):**

1. Configure these SQLAlchemy engine options explicitly:
   - `pool_size`
   - `max_overflow`
   - `pool_timeout`
   - `pool_recycle`
   - `pool_pre_ping`
2. Drive all pool parameters via **environment variables** so environments (dev/staging/prod) can tune safely without code changes.
3. Keep query patterns performance-safe (reinforce `.cursor/rules/03-database-performance.mdc`):
   - avoid unbounded queries
   - add indexes where filtering/joining is common
   - avoid N+1 patterns where applicable

**Deliverables:** Predictable connection behavior in production and fewer stale-connection issues.

---

### Step 3 — Keep Synchronous DB Engine (For Now)

**Goal:** Avoid a high-risk refactor that isn’t required yet.

**Actions (validated):**

- Keep the sync SQLAlchemy engine/sessions.
- Track async migration as a future optimization only if workload/concurrency requirements demand it.

**Deliverables:** No major architectural churn; focus stays on the top bottlenecks first.

---

## Order of Execution

Execute in this order:

1. **Step 1** — Hash lookup optimization (biggest scaling win).
2. **Step 2** — DB pool tuning (production reliability).
3. **Step 3** — Sync vs async (defer).

---

## Verification Checklist

- [ ] Property hash lookup no longer fetches all property IDs or loops in Python.
- [ ] Hash column exists and is indexed; lookup filters by hash in SQL.
- [ ] Pool settings are explicitly set and environment-driven (`pool_size`, `max_overflow`, `pool_timeout`, `pool_recycle`, `pool_pre_ping`).
- [ ] Clean layering preserved: DB access remains in repositories (route → service → repository).

---

## References

- `FINAL_FASTAPI_BACKEND_AUDIT.md` (Performance Audit section, lines 183–232)
- `FASTAPI_BACKEND_AUDIT_VALIDATION.md` (Performance Findings, lines 96–130)
- `.cursor/rules/03-database-performance.mdc` (indexes, query hygiene, migrations expectations)
- `.cursor/rules/00-master-fastapi.mdc` (layer boundaries: API → Service → Repository → DB)
