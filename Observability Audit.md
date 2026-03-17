# Observability Audit — End-to-End Step-by-Step Refactor Plan

This document is the refactor plan for the **Observability Audit** section (lines **232–252**) of `FINAL_FASTAPI_BACKEND_AUDIT.md`. Each step is ordered so dependencies are respected and changes can be validated incrementally. Validation decisions are taken from `FASTAPI_BACKEND_AUDIT_VALIDATION.md` lines **131–146** and repo observability standards from `.cursor/rules/05-testing-observability.mdc`.

---

## Summary of Findings Addressed

| # | Finding | Risk | Fix |
|---|--------|------|-----|
| 1 | Limited logging; no correlation IDs / tracing / metrics / slow query logging | Higher MTTR, weaker production diagnostics, harder incident response | Add request IDs, then gradually adopt metrics (Prometheus), tracing (OpenTelemetry), error tracking (Sentry), and slow query logging |

---

## Step-by-Step Refactor Plan

### Step 1 — Introduce Request Correlation IDs (Request IDs)

**Goal:** Ensure every request can be traced through logs end-to-end using a correlation ID.

**Actions (validated):**

1. Add request ID generation and propagation (typically via middleware).
2. Attach the request ID into the logging context so all logs produced during a request include it (structured logging).
3. Ensure the request ID is returned to clients (commonly via a response header) so support can correlate client errors to server logs.
4. Confirm compliance with `.cursor/rules/05-testing-observability.mdc`:
   - structured logging
   - correlation IDs for requests
   - do not log secrets/sensitive data

**Deliverables:** Every request has a correlation ID that appears in structured logs consistently.

---

### Step 2 — Add Metrics Instrumentation (Prometheus)

**Goal:** Add basic operational visibility (traffic, error rates, latency) for production readiness.

**Actions (validated):**

1. Introduce a Prometheus-compatible metrics approach (per audit recommendation).
2. Capture baseline metrics:
   - request count (by route/method/status)
   - request latency (histogram/summary)
   - error count (4xx/5xx)
3. Ensure critical operations emit metrics where appropriate (as required by `.cursor/rules/05-testing-observability.mdc`).

**Deliverables:** Dashboards/alerts can be built from request rate, latency, and error metrics.

---

### Step 3 — Add Distributed Tracing (OpenTelemetry)

**Goal:** Enable end-to-end tracing across request lifecycle and key dependencies.

**Actions (validated):**

1. Add OpenTelemetry tracing to the application (gradual adoption).
2. Ensure traces include the correlation/request ID context so logs ↔ traces correlate cleanly.
3. Instrument key layers where meaningful (routes/services/repositories and external calls).

**Deliverables:** Traces can be used to identify slow spans and bottlenecks across layers.

---

### Step 4 — Add Error Tracking (Sentry)

**Goal:** Capture unhandled exceptions and actionable diagnostics automatically.

**Actions (validated):**

1. Integrate Sentry (per audit recommended stack).
2. Ensure events include request ID and safe context (no secrets).

**Deliverables:** Exceptions are captured with context; alerting can be configured on regressions.

---

### Step 5 — Add Slow Query Logging

**Goal:** Detect and investigate database performance hotspots in production.

**Actions (validated):**

1. Implement slow query logging with a threshold appropriate for production.
2. Ensure slow query logs include request ID/correlation context and avoid logging sensitive parameters.

**Deliverables:** DB bottlenecks can be identified and tied back to specific requests.

---

## Order of Execution

Execute in this order:

1. **Step 1** — Correlation IDs (immediate MTTR reduction; foundation for everything else).
2. **Step 2** — Metrics (production visibility).
3. **Step 3** — Tracing (deeper performance diagnosis).
4. **Step 4** — Sentry (exception monitoring).
5. **Step 5** — Slow query logging (DB hotspot detection).

---

## Verification Checklist

- [ ] Every request has a correlation/request ID and it appears in structured logs.
- [ ] No secrets/sensitive data are logged.
- [ ] Basic metrics are available (request rate, latency, errors).
- [ ] Traces can be captured and correlated with request IDs.
- [ ] Errors are reported to Sentry with safe context + request ID.
- [ ] Slow query logging reports queries above threshold with correlation context.

---

## References

- `FINAL_FASTAPI_BACKEND_AUDIT.md` (Observability Audit section, lines 232–252)
- `FASTAPI_BACKEND_AUDIT_VALIDATION.md` (Observability Findings, lines 131–146)
- `.cursor/rules/05-testing-observability.mdc` (structured logging, correlation IDs, avoid secrets, metrics/traces expectations)
