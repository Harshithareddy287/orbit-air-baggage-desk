"""Tests for feature/schema-and-filing."""

import sqlite3
from datetime import datetime, timedelta

import pytest

import claims
import db
from claims import ClaimError

NOW = datetime(2026, 11, 2, 9, 0, 0)


@pytest.fixture
def conn(tmp_path):
    connection = db.connect(str(tmp_path / "test.db"))
    yield connection
    connection.close()


def file_sample(conn, **changes):
    values = {
        "passenger": "Asha Rao",
        "flight": "OA101",
        "claim_type": "lost",
        "tier": "gold",
        "note": "Blue suitcase",
        "now": NOW,
        "by": "desk",
    }
    values.update(changes)
    return claims.file_claim(conn, **values)


def fetch_all(conn, sql, params=()):
    cursor = conn.execute(sql, params)
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def get_claim(conn, claim_id):
    return fetch_all(conn, "SELECT * FROM claims WHERE id = ?", (claim_id,))[0]


def count_claims(conn):
    return conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0]


# --- Filing ---------------------------------------------------------------


def test_valid_claim_is_saved_as_open(conn):
    claim_id = file_sample(conn)
    claim = get_claim(conn, claim_id)
    assert claim["passenger"] == "Asha Rao"
    assert claim["flight"] == "OA101"
    assert claim["type"] == "lost"
    assert claim["tier"] == "gold"
    assert claim["status"] == "open"
    assert claim["assigned_agent"] is None
    assert claim["note"] == "Blue suitcase"
    assert claim["filed_at"] == NOW.isoformat()


# --- Validation -----------------------------------------------------------


def test_blank_passenger_is_rejected(conn):
    with pytest.raises(ClaimError, match="(?i)passenger"):
        file_sample(conn, passenger="   ")
    assert count_claims(conn) == 0


def test_blank_flight_is_rejected(conn):
    with pytest.raises(ClaimError, match="(?i)flight"):
        file_sample(conn, flight="")
    assert count_claims(conn) == 0


def test_unknown_type_is_rejected(conn):
    with pytest.raises(ClaimError, match="(?i)type"):
        file_sample(conn, claim_type="stolen")
    assert count_claims(conn) == 0


def test_unknown_tier_is_rejected(conn):
    with pytest.raises(ClaimError, match="(?i)tier"):
        file_sample(conn, tier="platinum")
    assert count_claims(conn) == 0


def test_database_check_constraint_blocks_bad_type(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO claims (passenger, flight, type, tier, status, filed_at, deadline) "
            "VALUES ('A', 'OA1', 'stolen', 'gold', 'open', '2026-11-02T09:00:00', '2026-11-02T13:00:00')"
        )


# --- Deadlines by tier ----------------------------------------------------


def test_gold_deadline_is_4_hours(conn):
    claim = get_claim(conn, file_sample(conn, tier="gold"))
    assert claim["deadline"] == (NOW + timedelta(hours=4)).isoformat()


def test_silver_deadline_is_24_hours(conn):
    claim = get_claim(conn, file_sample(conn, tier="silver"))
    assert claim["deadline"] == (NOW + timedelta(hours=24)).isoformat()


def test_standard_deadline_is_72_hours(conn):
    claim = get_claim(conn, file_sample(conn, tier="standard"))
    assert claim["deadline"] == (NOW + timedelta(hours=72)).isoformat()


# --- History --------------------------------------------------------------


def test_filing_adds_history_row(conn):
    claim_id = file_sample(conn)
    rows = fetch_all(conn, "SELECT * FROM history WHERE claim_id = ?", (claim_id,))
    assert len(rows) == 1
    assert rows[0]["old_status"] is None
    assert rows[0]["new_status"] == "open"
    assert rows[0]["changed_by"] == "desk"
    assert rows[0]["changed_at"] == NOW.isoformat()


# --- Listing --------------------------------------------------------------


def test_list_filters_by_status_and_tier(conn):
    file_sample(conn, tier="gold")
    file_sample(conn, tier="silver")
    file_sample(conn, tier="standard")

    assert len(claims.list_claims(conn)) == 3

    gold = claims.list_claims(conn, tier="gold")
    assert len(gold) == 1
    assert gold[0]["tier"] == "gold"

    assert len(claims.list_claims(conn, status="open")) == 3
    assert claims.list_claims(conn, status="closed") == []
    assert len(claims.list_claims(conn, status="open", tier="silver")) == 1