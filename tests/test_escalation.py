"""Tests for feature/deadlines-and-escalation."""

import sqlite3
from datetime import datetime, timedelta

import pytest

import claims
import db

NOW = datetime(2026, 11, 2, 9, 0, 0)        # claim filed at 09:00
DEADLINE = NOW + timedelta(hours=4)          # gold deadline 13:00
LATE = DEADLINE + timedelta(minutes=1)       # 13:01


@pytest.fixture
def conn(tmp_path):
    connection = db.connect(str(tmp_path / "test.db"))
    yield connection
    connection.close()


def new_claim(conn, status="open"):
    claim_id = claims.file_claim(conn, "Asha Rao", "OA101", "lost", "gold", "", NOW, "desk")
    if status != "open":
        with conn:
            conn.execute("UPDATE claims SET status = ? WHERE id = ?", (status, claim_id))
    return claim_id


def status_of(conn, claim_id):
    return next(c for c in claims.list_claims(conn) if c["id"] == claim_id)["status"]


# When is a claim late? 


def test_one_minute_before_deadline_is_not_overdue():
    assert not claims.is_overdue(DEADLINE, DEADLINE - timedelta(minutes=1))


def test_exactly_at_deadline_is_not_overdue():
    assert not claims.is_overdue(DEADLINE, DEADLINE)


def test_one_minute_after_deadline_is_overdue():
    assert claims.is_overdue(DEADLINE, LATE)


# Escalation 


def test_late_open_and_assigned_claims_are_escalated(conn):
    open_id = new_claim(conn)
    assigned_id = new_claim(conn, "assigned")
    claims.escalate_overdue(conn, LATE)
    assert status_of(conn, open_id) == "escalated"
    assert status_of(conn, assigned_id) == "escalated"


def test_claim_not_late_yet_is_left_alone(conn):
    claim_id = new_claim(conn)
    assert claims.escalate_overdue(conn, DEADLINE) == []
    assert status_of(conn, claim_id) == "open"


def test_resolved_and_closed_claims_are_left_alone(conn):
    resolved_id = new_claim(conn, "resolved")
    closed_id = new_claim(conn, "closed")
    assert claims.escalate_overdue(conn, LATE) == []
    assert status_of(conn, resolved_id) == "resolved"
    assert status_of(conn, closed_id) == "closed"


def test_escalation_returns_ids_and_adds_history(conn):
    claim_id = new_claim(conn)
    assert claims.escalate_overdue(conn, LATE) == [claim_id]
    last = claims.get_history(conn, claim_id)[-1]
    assert last["old_status"] == "open"
    assert last["new_status"] == "escalated"
    assert last["changed_by"] == "system"
    assert last["changed_at"] == LATE.isoformat()


# All or nothing 


def test_failed_history_write_leaves_claim_unchanged(conn):
    claim_id = new_claim(conn)
    with conn:
        conn.execute(
            "CREATE TRIGGER block_history BEFORE INSERT ON history "
            "BEGIN SELECT RAISE(ABORT, 'history write failed'); END"
        )
    with pytest.raises(sqlite3.DatabaseError):
        claims.escalate_overdue(conn, LATE)
    assert status_of(conn, claim_id) == "open"
