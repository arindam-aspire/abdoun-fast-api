# Functionality Coverage Checklist

Track migration and parity status per domain.

## Auth & profile

- [x] Legacy behavior inventoried
- [x] Refactored implementation created
- [x] Parity tests added
- [x] Parity tests passing
- [ ] Switched via startup flag

## Users & RBAC

- [x] Legacy behavior inventoried
- [x] Refactored implementation created
- [x] Parity tests added
- [x] Parity tests passing
- [ ] Switched via startup flag

## Agents

- [x] Legacy behavior inventoried
- [x] Refactored implementation created
- [x] Parity tests added
- [x] Parity tests passing
- [ ] Switched via startup flag

## Admin dashboard

- [x] Legacy behavior inventoried
- [x] Refactored implementation created
- [x] Parity tests added
- [x] Parity tests passing
- [ ] Switched via startup flag

## Properties

- [x] Legacy behavior inventoried
- [x] Refactored implementation created
- [x] Parity tests added
- [x] Parity tests passing
- [ ] Switched via startup flag

## Geo search/import

- [x] Legacy behavior inventoried
- [x] Refactored implementation created
- [x] Parity tests added
- [x] Parity tests passing
- [ ] Switched via startup flag

## Taxonomy

- [x] Legacy behavior inventoried
- [x] Refactored implementation created
- [x] Parity tests added
- [x] Parity tests passing
- [ ] Switched via startup flag

## Submissions

- [x] Legacy behavior inventoried
- [x] Refactored implementation created
- [x] Parity tests added
- [x] Parity tests passing
- [ ] Switched via startup flag

## Agent property list

- [x] Legacy behavior inventoried
- [x] Refactored implementation shared (legacy router; no separate refactored flag in this pack)
- [x] Parity tests added (`test_agent_properties_parity.py` sanity)
- [x] Parity tests passing
- [ ] Switched via startup flag (N/A until a dedicated flag exists)

## Favorites

- [x] Legacy behavior inventoried
- [x] Refactored implementation created (personalization package)
- [x] Parity tests added
- [x] Parity tests passing
- [ ] Switched via startup flag

## Saved searches

- [x] Legacy behavior inventoried
- [x] Refactored implementation created (personalization package)
- [x] Parity tests added
- [x] Parity tests passing
- [ ] Switched via startup flag

## Recent views

- [x] Legacy behavior inventoried
- [x] Refactored implementation created (personalization package)
- [x] Parity tests added
- [x] Parity tests passing
- [ ] Switched via startup flag

## Uploads

- [x] Legacy behavior inventoried
- [x] Refactored implementation created
- [x] Parity tests added
- [x] Parity tests passing
- [ ] Switched via startup flag

## Owners

- [x] Legacy behavior inventoried
- [x] Refactored implementation created
- [x] Parity tests added
- [x] Parity tests passing
- [ ] Switched via startup flag

## Admin property assignment

- [x] Legacy behavior inventoried
- [x] Refactored implementation created (`app_refactored/domains/admin`)
- [x] Parity tests added
- [x] Parity tests passing
- [ ] Switched via startup flag

## Observability

- [x] Legacy behavior inventoried (`NON_API_FUNCTIONALITY_AUDIT.md`)
- [x] Shared with legacy app (not migrated into `app_refactored`)
- [x] Verification documented (audit + existing unit/smoke tests)
- [x] N/A parity suite
- [ ] Switched via startup flag (N/A)

## Schedulers

- [x] Legacy behavior inventoried
- [x] Shared with legacy app
- [x] Verification documented
- [x] N/A parity suite
- [ ] Switched via startup flag (N/A)

## Scripts/data workflows

- [x] Legacy behavior inventoried
- [x] Shared / unchanged scripts under `scripts/`
- [x] Verification documented
- [x] N/A parity suite
- [ ] Switched via startup flag (N/A)
