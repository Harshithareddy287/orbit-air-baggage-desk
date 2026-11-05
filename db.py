"""Database connection and schema for the Orbit Air baggage desk."""

import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS claims (
    id INTEGER PRIMARY KEY,
    passenger TEXT NOT NULL CHECK (trim(passenger) <> ''),
    flight TEXT NOT NULL CHECK (trim(flight) <> ''),
    type TEXT NOT NULL CHECK (type IN ('delayed', 'lost', 'damaged')),
    tier TEXT NOT NULL CHECK (tier IN ('standard', 'silver', 'gold')),
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'assigned', 'escalated', 'resolved', 'closed')),
    assigned_agent TEXT,
    note TEXT,
    filed_at TEXT NOT NULL,
    deadline TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY,
    claim_id INTEGER NOT NULL REFERENCES claims(id),
    old_status TEXT
        CHECK (old_status IS NULL
               OR old_status IN ('open', 'assigned', 'escalated', 'resolved', 'closed')),
    new_status TEXT NOT NULL
        CHECK (new_status IN ('open', 'assigned', 'escalated', 'resolved', 'closed')),
    changed_by TEXT NOT NULL,
    changed_at TEXT NOT NULL
);
"""


def connect(path):
    """Open the database at `path`, enable foreign keys and create the tables."""
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn
