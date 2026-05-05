# 11 — Migrate Property Submissions Domain

## Goal
Rebuild agent submission lifecycle and admin moderation flows.

## Cursor Prompt

```md
Migrate property submissions into app_refactored/domains/submissions.

Legacy capabilities:
Agent:
- create draft
- create and submit
- get submission
- patch submission
- submit existing
- delete with reason

Admin:
- list submissions
- list drafts
- get admin submission
- review/approve/reject
- admin create and approve
- admin submit existing draft and approve
- admin soft delete

Rules:
1. Preserve all workflow status transitions.
2. Preserve payload and step_completion JSON behavior.
3. Preserve consent/terms/privacy flags.
4. Preserve admin vs agent auth boundaries.
5. For write parity, use rollback or shape-only with explicit missing DB effect note.
6. Add startup flag use_refactored_submissions, default false.
7. Update coverage checklist.

Completion checks:
- pytest tests/refactor_parity/test_submissions_parity.py -q
- pytest tests/smoke/ -q
- python scripts/check_contract_drift.py
```
