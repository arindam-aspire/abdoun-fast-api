# Vibe Coding Policy

This policy defines how we ship features and run refactors with speed **and** architectural discipline.

## 1) Outcome Over Output

- Build for maintainability, not just short-term delivery.
- Prioritize code that a new team member can understand quickly.
- Prefer clear naming and predictable structure over clever shortcuts.

## 2) SOLID as Daily Constraints

- **Single Responsibility:** each module/function should have one main reason to change.
- **Open/Closed:** extend via composition and new units, avoid editing stable code paths unnecessarily.
- **Liskov Substitution:** abstractions should be safely replaceable in tests/runtime.
- **Interface Segregation:** prefer focused interfaces/services over broad god-objects.
- **Dependency Inversion:** higher-level logic depends on contracts, not infrastructure details.

## 3) Layering Rules (Backend)

- Routers/controllers: HTTP mapping, auth checks, request/response binding only.
- Services: business workflow, validation, orchestration.
- Repositories: persistence and query concerns only.
- Infra adapters (S3, Cognito, email, metrics): isolated behind service boundaries.

## 4) Refactor Protocol

1. Lock behavior first (tests or characterization checks).
2. Restructure in small commits without changing behavior.
3. Re-run tests and verify critical API contracts.
4. Document notable architectural decisions in `docs/`.

## 5) Change Size and Scope

- Keep PRs small and reviewable; split by concern.
- Avoid mixing:
  - feature + refactor,
  - schema + unrelated cleanup,
  - endpoint contract changes + internals.
- If a mixed PR is unavoidable, call out risk zones clearly.

## 6) API Contract Discipline

- Use typed request/response schemas for public endpoints.
- Keep error shapes consistent and actionable.
- Preserve backward compatibility by default.
- For breaking changes: version, migration notes, and rollout plan are required.

## 7) Testing and Verification

- New behavior requires tests at the right level (unit/integration/contract).
- Refactors require parity checks for unchanged behavior.
- Critical paths (auth, permissions, submissions, payments-like flows) need regression coverage.

## 8) Observability and Failure Semantics

- No silent exception swallowing.
- Log with context needed for triage (operation, actor, identifiers, cause).
- Favor explicit domain errors over generic `Exception`.
- Degrade gracefully for non-critical side effects.

## 9) Definition of Done (Engineering)

A change is done when:

- Code follows layering and SOLID expectations.
- Tests pass and meaningful coverage exists for touched behavior.
- API/schema/DB changes are documented.
- Security and permission implications were considered.
- The PR description explains **why** this change exists.

## 10) Team Agreements for “Vibe” Development

- Default to consistency with existing conventions.
- Prefer deleting dead code over adding feature flags forever.
- Leave the codebase better than you found it.
- If architecture trade-offs are made, record them explicitly.

---

## Quick PR Checklist

- [ ] Router is thin; business logic is in service layer.
- [ ] Data access is in repository, not in route/service glue code.
- [ ] Public contracts are typed and backward-compatible.
- [ ] Errors are explicit and logged with context.
- [ ] Tests added/updated for changed behavior.
- [ ] Scope is focused and reviewable.
