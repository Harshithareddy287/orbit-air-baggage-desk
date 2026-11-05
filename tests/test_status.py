"""Tests for feature/assign-and-status."""

from datetime import datetime, timedelta

import pytest

import claims
import db
from claims import ClaimError

NOW = datetime(2026, 11, 2, 9, 0, 0)
LATER = NOW + timedelta(hours=1)


@pytest.fixture
def conn(tmp_path):
    connection = db.connect(str(tmp_path / "test.db"))
    yield connection
    connection.close()


def new_claim(conn):
    return claims.file_claim(conn, "Asha Rao", "OA101", "lost", "gold", "", NOW, "desk")


def get_claim(conn, claim_id):
    return next(c for c in claims.list_claims(conn) if c["id"] == claim_id)


def status_of(conn, claim_id):
    return get_claim(conn, claim_id)["status"]


def make_escalated(conn, claim_id):
    with conn:
        conn.execute("UPDATE claims SET status = 'escalated' WHERE id = ?", (claim_id,))


def test_assign_open_claim(conn):
    claim_id = new_claim(conn)
    claims.assign_claim(conn, claim_id, "maria", LATER, "lead")
    claim = get_claim(conn, claim_id)
    assert claim["status"] == "assigned"
    assert claim["assigned_agent"] == "maria"


def test_assign_escalated_claim(conn):
    claim_id = new_claim(conn)
    make_escalated(conn, claim_id)
    claims.assign_claim(conn, claim_id, "maria", LATER, "lead")
    assert status_of(conn, claim_id) == "assigned"


def test_resolve_assigned_claim(conn):
    claim_id = new_claim(conn)
    claims.assign_claim(conn, claim_id, "maria", LATER, "lead")
    claims.resolve_claim(conn, claim_id, LATER, "maria")
    assert status_of(conn, claim_id) == "resolved"


def test_resolve_escalated_claim(conn):
    claim_id = new_claim(conn)
    make_escalated(conn, claim_id)
    claims.resolve_claim(conn, claim_id, LATER, "maria")
    assert status_of(conn, claim_id) == "resolved"


def test_close_resolved_claim(conn):
    claim_id = new_claim(conn)
    claims.assign_claim(conn, claim_id, "maria", LATER, "lead")
    claims.resolve_claim(conn, claim_id, LATER, "maria")
    claims.close_claim(conn, claim_id, LATER, "lead")
    assert status_of(conn, claim_id) == "closed"


def test_close_open_claim_is_rejected(conn):
    claim_id = new_claim(conn)
    with pytest.raises(ClaimError):
        claims.close_claim(conn, claim_id, LATER, "lead")
    assert status_of(conn, claim_id) == "open"


def test_resolve_open_claim_is_rejected(conn):
    claim_id = new_claim(conn)
    with pytest.raises(ClaimError):
        claims.resolve_claim(conn, claim_id, LATER, "maria")
    assert status_of(conn, claim_id) == "open"


def test_closed_claim_cannot_change(conn):
    claim_id = new_claim(conn)
    claims.assign_claim(conn, claim_id, "maria", LATER, "lead")
    claims.resolve_claim(conn, claim_id, LATER, "maria")
    claims.close_claim(conn, claim_id, LATER, "lead")
    with pytest.raises(ClaimError):
        claims.assign_claim(conn, claim_id, "omar", LATER, "lead")
    assert status_of(conn, claim_id) == "closed"


def test_status_change_adds_history_row(conn):
    claim_id = new_claim(conn)
    claims.assign_claim(conn, claim_id, "maria", LATER, "lead")
    history = claims.get_history(conn, claim_id)
    assert len(history) == 2
    assert history[1]["old_status"] == "open"
    assert history[1]["new_status"] == "assigned"
    assert history[1]["changed_by"] == "lead"
    assert history[1]["changed_at"] == LATER.isoformat()
