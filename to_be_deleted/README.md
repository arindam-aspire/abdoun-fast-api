# To be deleted (archive)

This folder holds **non-runtime** artifacts from the refactor/migration effort: instructions, audit notes, OpenAPI/DB baselines, and helper scripts that targeted that work.

- **`instructions/`** — step-by-step migration task pack (not used by the app).
- **`docs_refactor/`** — refactor checklists, canary plans, baseline JSON, parity policy docs.
- **`root_audits/`** — root-level audit / prompt / large reference markdown (including generated `db.md`).
- **`docs_misc/`** — extra architecture/inventory markdown moved out of `docs/`.
- **`scripts_refactor/`** — `check_contract_drift.py`, `generate_refactor_baseline.py`, `build_db_md.py` (optional; restore paths if you still want contract baselines in CI).

**Working application code** lives in `app/` (including `app.domains`), `tests/`, `alembic/`, and operational docs under `docs/` (auth, testing, property integration, Postman collection).

After you confirm nothing here is needed, delete this folder entirely (or keep it outside the repo).
