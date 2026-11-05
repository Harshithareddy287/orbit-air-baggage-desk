"""Claim rules for the Orbit Air baggage desk."""

from datetime import datetime, timedelta

DEADLINE_HOURS = {"gold": 4, "silver": 24, "standard": 72}
CLAIM_TYPES = ("delayed", "lost", "damaged")

# Every status a claim may move to from its current status. "closed" is final.
ALLOWED_CHANGES = {
    "open": {"assigned", "escalated"},
    "assigned": {"resolved", "escalated"},
    "escalated": {"assigned", "resolved"},
    "resolved": {"closed"},
    "closed": set(),
}


class ClaimError(Exception):
    """Raised when a claim request breaks a business rule."""


def deadline_for(tier, filed_at):
    """Return the response deadline for a claim of `tier` filed at `filed_at`."""
    if tier not in DEADLINE_HOURS:
        raise ClaimError(f"Unknown tier: {tier!r}")
    return filed_at + timedelta(hours=DEADLINE_HOURS[tier])


def file_claim(conn, passenger, flight, claim_type, tier, note, now, by):
    """Validate and save a new open claim plus its first history row.

    Returns the new claim id.
    """
    passenger = (passenger or "").strip()
    flight = (flight or "").strip()
    if not passenger:
        raise ClaimError("Passenger name can't be blank")
    if not flight:
        raise ClaimError("Flight number can't be blank")
    if claim_type not in CLAIM_TYPES:
        raise ClaimError(f"Unknown claim type: {claim_type!r}")
    deadline = deadline_for(tier, now)

    filed_at = now.isoformat()
    with conn:
        cursor = conn.execute(
            "INSERT INTO claims (passenger, flight, type, tier, status, note, filed_at, deadline) "
            "VALUES (?, ?, ?, ?, 'open', ?, ?, ?)",
            (passenger, flight, claim_type, tier, note, filed_at, deadline.isoformat()),
        )
        claim_id = cursor.lastrowid
        conn.execute(
            "INSERT INTO history (claim_id, old_status, new_status, changed_by, changed_at) "
            "VALUES (?, NULL, 'open', ?, ?)",
            (claim_id, by, filed_at),
        )
    return claim_id


def list_claims(conn, status=None, tier=None):
    """Return claims as a list of dicts, optionally filtered by status and tier."""
    sql = "SELECT * FROM claims"
    conditions = []
    params = []
    if status is not None:
        conditions.append("status = ?")
        params.append(status)
    if tier is not None:
        conditions.append("tier = ?")
        params.append(tier)
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY id"

    return _rows_as_dicts(conn.execute(sql, params))


def _rows_as_dicts(cursor):
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _change_status(conn, claim_id, new_status, now, by, agent=None):
    """Move a claim to `new_status` and save its history row in one transaction.

    When `agent` is given it is saved as the claim's assigned agent.
    """
    row = conn.execute("SELECT status FROM claims WHERE id = ?", (claim_id,)).fetchone()
    if row is None:
        raise ClaimError(f"Claim {claim_id} does not exist")
    old_status = row[0]
    if new_status not in ALLOWED_CHANGES[old_status]:
        raise ClaimError(f"Claim {claim_id} can't move from {old_status} to {new_status}")

    changed_at = now.isoformat()
    with conn:
        cursor = conn.execute(
            "UPDATE claims SET status = ?, assigned_agent = COALESCE(?, assigned_agent) "
            "WHERE id = ? AND status = ?",
            (new_status, agent, claim_id, old_status),
        )
        if cursor.rowcount != 1:
            raise ClaimError(f"Claim {claim_id} changed while updating, try again")
        conn.execute(
            "INSERT INTO history (claim_id, old_status, new_status, changed_by, changed_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (claim_id, old_status, new_status, by, changed_at),
        )


def assign_claim(conn, claim_id, agent, now, by):
    """Assign an open or escalated claim to `agent`."""
    agent = (agent or "").strip()
    if not agent:
        raise ClaimError("Agent name can't be blank")
    _change_status(conn, claim_id, "assigned", now, by, agent=agent)


def resolve_claim(conn, claim_id, now, by):
    """Mark an assigned or escalated claim as resolved."""
    _change_status(conn, claim_id, "resolved", now, by)


def close_claim(conn, claim_id, now, by):
    """Close a resolved claim. Closed is final."""
    _change_status(conn, claim_id, "closed", now, by)


def is_overdue(deadline, now):
    """Return True only when `now` is strictly later than `deadline`.

    Exactly at the deadline still counts as on time.
    """
    return now > deadline


def escalate_overdue(conn, now):
    """Escalate every open or assigned claim whose deadline has passed at `now`.

    Each claim's status change and history row are saved together, recorded as
    changed by "system". Returns the escalated claim ids in id order.
    """
    candidates = conn.execute(
        "SELECT id, deadline FROM claims WHERE status IN ('open', 'assigned') ORDER BY id"
    ).fetchall()

    escalated = []
    for claim_id, deadline in candidates:
        if is_overdue(datetime.fromisoformat(deadline), now):
            _change_status(conn, claim_id, "escalated", now, "system")
            escalated.append(claim_id)
    return escalated


def get_history(conn, claim_id):
    """Return a claim's history rows as a list of dicts, oldest first."""
    if conn.execute("SELECT 1 FROM claims WHERE id = ?", (claim_id,)).fetchone() is None:
        raise ClaimError(f"Claim {claim_id} does not exist")
    return _rows_as_dicts(
        conn.execute("SELECT * FROM history WHERE claim_id = ? ORDER BY id", (claim_id,))
    )
