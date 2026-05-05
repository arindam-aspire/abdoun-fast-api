# 10 — Migrate Agents Domain

## Goal
Rebuild agent admin, public onboarding, assignment, and self-service dashboard flows.

## Cursor Prompt

```md
Migrate agents functionality into app_refactored/domains/agents.

Legacy capabilities:
- invite
- manual onboard
- list agents
- summary
- leaderboard
- invites list
- assignments
- agent dashboard summary
- get agent by id
- accept/decline/status/delete
- resend invite/resend invitation alias
- revoke invite
- public invite validate
- public/compat onboarding
- assign-agent/unassign-agent

Rules:
1. Preserve all alias and compat endpoints.
2. Preserve include_in_schema=False behavior where legacy has it.
3. Preserve auth roles exactly.
4. Use fake_current_user override for authenticated parity tests.
5. Do not remove or deprecate endpoints in this task.
6. Add startup flag use_refactored_agents, default false.
7. Update coverage checklist endpoint-by-endpoint.
8. If any compat behavior is unclear, add blocker and do not switch.

Completion checks:
- pytest tests/refactor_parity/test_agents_parity.py -q
- pytest tests/smoke/ -q
- python scripts/check_contract_drift.py
```
