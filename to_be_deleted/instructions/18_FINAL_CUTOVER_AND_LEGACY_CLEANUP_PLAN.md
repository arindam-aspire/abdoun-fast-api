# 18 — Final Cutover and Legacy Cleanup Plan

## Goal
Complete the refactor safely and prepare old-code cleanup without rushing deletion.

## Cursor Prompt

```md
Prepare final cutover and cleanup.

Rules:
- Do not delete legacy implementation immediately.
- After all domains are switched and stable, mark legacy code as deprecated.
- Keep rollback path for at least one release cycle.

Tasks:
1. Generate docs/refactor/FINAL_CUTOVER_CHECKLIST.md.
2. Confirm all feature flags can be enabled in staging and smoke tests pass.
3. Confirm all feature flags disabled still restore legacy behavior.
4. Confirm OpenAPI contract is either unchanged or frontend-impact report is approved.
5. Create docs/refactor/LEGACY_CLEANUP_BACKLOG.md listing files that can be removed later.
6. Create docs/refactor/POST_CUTOVER_MONITORING.md:
   - logs to watch
   - error rates
   - auth failures
   - DB slow queries
   - user-facing flows
7. Do not remove legacy code in this task.

Completion checks:
- FINAL_CUTOVER_CHECKLIST.md complete
- LEGACY_CLEANUP_BACKLOG.md complete
- POST_CUTOVER_MONITORING.md complete
- all tests green
```
