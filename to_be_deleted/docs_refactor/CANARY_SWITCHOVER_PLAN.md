# Canary Switchover Plan

## Principles

- **Default:** all `USE_REFACTORED_*` environment flags are `false`; production stays on legacy import paths until explicit approval.
- **Staging first:** enable one domain flag at a time, restart the process, run automated tests and targeted manual flows.
- **Rollback:** set the domain flag to `false`, restart the process, confirm legacy routers are active.

## Suggested domain order

1. Taxonomy (`USE_REFACTORED_TAXONOMY`)
2. Properties / search / import (`USE_REFACTORED_PROPERTIES`)
3. Personalization (`USE_REFACTORED_PERSONALIZATION`)
4. Uploads (`USE_REFACTORED_UPLOADS`)
5. Owners (`USE_REFACTORED_OWNERS`)
6. Agents (`USE_REFACTORED_AGENTS`)
7. Submissions (`USE_REFACTORED_SUBMISSIONS`)
8. Admin + admin properties (`USE_REFACTORED_ADMIN`)
9. Users (`USE_REFACTORED_USERS`)
10. Auth (`USE_REFACTORED_AUTH`) — last; requires staging login verification per task policy.

## Required checks per domain

- `pytest tests/refactor_parity/ -q`
- `pytest tests/smoke/ -q`
- `python scripts/check_contract_drift.py` (expect `no_contract_drift` with all flags `false`; after enabling one flag, confirm no unintended OpenAPI drift vs approved baseline)
- Domain-specific manual smoke (e.g. taxonomy GETs, property list, login for auth).

## Route inventory per flag (operator procedure)

With only one `USE_REFACTORED_*` set to `true` at a time, restart the app and regenerate inventory:

```bash
python scripts/generate_refactor_baseline.py
# Archive outputs, e.g. docs/refactor/route_inventory_<domain>_on.json
```

Compare to `docs/refactor/ROUTE_INVENTORY.json` from the all-off baseline; paths and methods should match.

## Owner approval checklist

- [ ] Parity tests green for the domain
- [ ] No unresolved **critical** rows in `docs/refactor/MISSING_FUNCTIONALITY_REGISTER.md`
- [ ] Staging sign-off for user-visible flows
- [ ] Rollback command documented for the flag

## Rollback command (example)

```bash
# Set in process env or .env, then restart uvicorn/workers
export USE_REFACTORED_TAXONOMY=false
```

Repeat with the relevant variable for each domain.
