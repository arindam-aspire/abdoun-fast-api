# Final Cutover Checklist

Use before declaring the refactor “complete” in an environment.

## Preconditions

- [ ] All `USE_REFACTORED_*` flags documented and default to `false` in code.
- [ ] `pytest tests/refactor_parity/ -q` passes.
- [ ] `pytest tests/smoke/ -q` passes.
- [ ] `python scripts/check_contract_drift.py` passes against the approved OpenAPI baseline (or frontend impact report is explicitly approved).
- [ ] `docs/refactor/MISSING_FUNCTIONALITY_REGISTER.md` has no critical open items.
- [ ] `docs/refactor/SECURITY_DEBT_REGISTER.md` reviewed; accepted risks signed off.

## Staging: all domains on

- [ ] Enable refactored flags **one at a time** first (see `CANARY_SWITCHOVER_PLAN.md`).
- [ ] After each domain, run smoke + parity + manual spot checks.
- [ ] Optional: enable all refactored flags together in staging only for a soak test.
- [ ] Monitor logs, error rate, auth failures, DB slow queries.

## Production cutover

- [ ] Change management / owner approval recorded.
- [ ] Enable flags per domain schedule (or all at once if policy allows).
- [ ] Restart application processes.
- [ ] Run smoke tests against production (read-only health + critical paths as allowed).
- [ ] Keep rollback env vars ready for one release cycle.

## Post-cutover

- [ ] Follow `POST_CUTOVER_MONITORING.md` for the first 24–72 hours.
- [ ] Track items in `LEGACY_CLEANUP_BACKLOG.md` for a later release (do not delete legacy files in the same PR as first cutover).
