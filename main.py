"""Command line interface for the Orbit Air baggage desk.

This module only parses arguments, calls the rules in claims.py and prints
results. All business rules live in claims.py.
"""

import argparse
import csv
import sqlite3
import sys
from datetime import datetime

import claims
import db


def parse_time(value):
    """Parse an ISO 8601 time for --now, e.g. 2026-11-02T09:00:00."""
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"invalid time {value!r}, use ISO format like 2026-11-02T09:00:00"
        ) from None
    if parsed.tzinfo is not None:
        raise argparse.ArgumentTypeError(
            f"invalid time {value!r}, leave out the time zone, e.g. 2026-11-02T09:00:00"
        )
    return parsed


def parse_by(value):
    """Validate --by: who is making the change must not be blank."""
    if not value.strip():
        raise argparse.ArgumentTypeError("must not be blank")
    return value.strip()


def build_parser():
    parser = argparse.ArgumentParser(prog="main.py", description="Orbit Air baggage desk")
    parser.add_argument("--db", default="claims.db", help="SQLite database file (default: claims.db)")
    parser.add_argument("--now", type=parse_time, help="current time in ISO format (default: real clock)")
    parser.add_argument("--by", type=parse_by, default="desk", help="who is making the change (default: desk)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("file", help="file a new claim")
    p.add_argument("--passenger", required=True)
    p.add_argument("--flight", required=True)
    p.add_argument("--type", required=True, dest="claim_type")
    p.add_argument("--tier", required=True)
    p.add_argument("--note")

    p = sub.add_parser("list", help="list claims")
    p.add_argument("--status")
    p.add_argument("--tier")

    p = sub.add_parser("assign", help="assign a claim to an agent")
    p.add_argument("claim_id", type=int)
    p.add_argument("agent")

    for name, text in (("resolve", "resolve a claim"), ("close", "close a resolved claim"),
                       ("history", "show a claim's history")):
        sub.add_parser(name, help=text).add_argument("claim_id", type=int)

    sub.add_parser("escalate", help="escalate overdue open and assigned claims")

    p = sub.add_parser("seed", help="load claims from a CSV file")
    p.add_argument("csv_path")

    return parser


def cmd_file(conn, args, now):
    claim_id = claims.file_claim(
        conn, args.passenger, args.flight, args.claim_type, args.tier, args.note, now, args.by
    )
    print(f"Filed claim {claim_id}")


def cmd_list(conn, args, now):
    rows = claims.list_claims(conn, status=args.status, tier=args.tier)
    if not rows:
        print("No claims found.")
        return
    print(f"{'ID':>4}  {'PASSENGER':<16} {'FLIGHT':<7} {'TYPE':<8} {'TIER':<9} "
          f"{'STATUS':<10} {'AGENT':<12} DEADLINE")
    for r in rows:
        print(f"{r['id']:>4}  {r['passenger']:<16} {r['flight']:<7} {r['type']:<8} "
              f"{r['tier']:<9} {r['status']:<10} {r['assigned_agent'] or '-':<12} {r['deadline']}")


def cmd_assign(conn, args, now):
    claims.assign_claim(conn, args.claim_id, args.agent, now, args.by)
    print(f"Claim {args.claim_id} assigned to {args.agent.strip()}")


def cmd_resolve(conn, args, now):
    claims.resolve_claim(conn, args.claim_id, now, args.by)
    print(f"Claim {args.claim_id} resolved")


def cmd_close(conn, args, now):
    claims.close_claim(conn, args.claim_id, now, args.by)
    print(f"Claim {args.claim_id} closed")


def cmd_escalate(conn, args, now):
    ids = claims.escalate_overdue(conn, now)
    if ids:
        print("Escalated claims: " + ", ".join(str(i) for i in ids))
    else:
        print("No claims to escalate.")


def cmd_history(conn, args, now):
    for h in claims.get_history(conn, args.claim_id):
        print(f"{h['changed_at']}  {h['old_status'] or '-':<10} -> {h['new_status']:<10} by {h['changed_by']}")


def cmd_seed(conn, args, now):
    # Notes are stored as plain data; nothing in the CSV is interpreted.
    try:
        with open(args.csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except UnicodeDecodeError:
        raise claims.ClaimError(f"{args.csv_path} is not a UTF-8 text file") from None
    except csv.Error as e:
        raise claims.ClaimError(f"{args.csv_path} is not a valid CSV file: {e}") from None
    for line, row in enumerate(rows, start=2):
        try:
            claims.file_claim(
                conn, row.get("passenger"), row.get("flight"), row.get("type"),
                row.get("tier"), row.get("note") or None, now, args.by,
            )
        except claims.ClaimError as e:
            raise claims.ClaimError(f"{args.csv_path} line {line}: {e}") from None
    print(f"Seeded {len(rows)} claims from {args.csv_path}")


COMMANDS = {
    "file": cmd_file,
    "list": cmd_list,
    "assign": cmd_assign,
    "resolve": cmd_resolve,
    "close": cmd_close,
    "escalate": cmd_escalate,
    "history": cmd_history,
    "seed": cmd_seed,
}


def main(argv=None):
    args = build_parser().parse_args(argv)
    # The real clock is only read here, and only when --now isn't given.
    now = args.now if args.now is not None else datetime.now().replace(microsecond=0)
    try:
        conn = db.connect(args.db)
        try:
            COMMANDS[args.command](conn, args, now)
        finally:
            conn.close()
    except claims.ClaimError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"Error: {e.strerror}: {e.filename}", file=sys.stderr)
        return 1
    except sqlite3.Error as e:
        print(f"Database error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
