"""Unit tests for SQL-level filtering/sorting on agent listings.

These tests compile SQL to confirm the repository applies filters BEFORE count/pagination,
without requiring a real DB connection.
"""

from __future__ import annotations

import uuid

from sqlalchemy.dialects import postgresql

from app.repositories.property_repository import PropertyRepository


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


class _RowsResult:
    def unique(self):
        return self

    def scalars(self):
        return self

    def all(self):
        return []


class _FakeSession:
    def __init__(self):
        self.statements = []
        self._call = 0

    def execute(self, stmt):
        self.statements.append(stmt)
        self._call += 1
        # First execute is count, second is row fetch.
        if self._call == 1:
            return _ScalarResult(0)
        return _RowsResult()


def _sql(stmt) -> str:
    return str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})).lower()


def test_list_properties_for_agent_default_sort_unchanged() -> None:
    db = _FakeSession()
    repo = PropertyRepository(db)  # type: ignore[arg-type]
    repo.list_properties_for_agent(agent_user_id=uuid.uuid4(), page=1, page_size=20)

    assert len(db.statements) == 2
    count_sql = _sql(db.statements[0])
    page_sql = _sql(db.statements[1])

    # Default order must remain: coalesce(updated_at, created_at) desc.
    # Count SQL will still include ORDER BY inside the window function used to pick latest submission;
    # it must NOT include the page-level ORDER BY on the main select.
    assert "order by coalesce" not in count_sql
    assert "order by" in page_sql
    assert "coalesce" in page_sql and "updated_at" in page_sql and "created_at" in page_sql
    assert "desc" in page_sql


def test_list_properties_for_agent_search_applied_before_count() -> None:
    db = _FakeSession()
    repo = PropertyRepository(db)  # type: ignore[arg-type]
    repo.list_properties_for_agent(agent_user_id=uuid.uuid4(), page=2, page_size=10, search=" Villa ")

    count_sql = _sql(db.statements[0])
    page_sql = _sql(db.statements[1])

    # Search term appears in both count + page statements (i.e., before total is computed).
    assert "villa" in count_sql
    assert "villa" in page_sql


def test_list_properties_for_agent_status_invalid_is_empty() -> None:
    db = _FakeSession()
    repo = PropertyRepository(db)  # type: ignore[arg-type]
    repo.list_properties_for_agent(agent_user_id=uuid.uuid4(), page=1, page_size=10, status="not-a-real-status")

    count_sql = _sql(db.statements[0])
    page_sql = _sql(db.statements[1])

    # Invalid status should not return unfiltered dataset; we add a FALSE() guard.
    assert "false" in count_sql or "0 = 1" in count_sql
    assert "false" in page_sql or "0 = 1" in page_sql


def test_list_properties_for_agent_sort_by_updated_at_desc() -> None:
    db = _FakeSession()
    repo = PropertyRepository(db)  # type: ignore[arg-type]
    repo.list_properties_for_agent(
        agent_user_id=uuid.uuid4(),
        page=1,
        page_size=10,
        sort_by="updated_at",
        sort_order="desc",
    )

    page_sql = _sql(db.statements[1])
    assert "order by" in page_sql
    assert "coalesce" in page_sql and "updated_at" in page_sql
    assert "desc" in page_sql

