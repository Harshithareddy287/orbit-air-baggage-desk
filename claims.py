"""Claim rules for the Orbit Air baggage desk."""

from datetime import timedelta

DEADLINE_HOURS = {"gold": 4, "silver": 24, "standard": 72}
CLAIM_TYPES = ("delayed", "lost", "damaged")


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

    cursor = conn.execute(sql, params)
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]
