# Feature Flag Cutover Policy

- All `use_refactored_*` flags default to `false`.
- Rollout starts in staging, never directly in production.
- Enable one domain at a time and restart the process to apply startup-time router selection.
- Domain switch requires passing parity tests and smoke tests.
- Rollback is immediate: set the domain flag back to `false` and restart.
- Keep production defaults on legacy until explicit domain approval.

