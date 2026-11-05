"""Tests for feature/cli."""

import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(db, *args, now=None):
    """Run `python main.py --db DB [--now NOW] <args>` and return the result."""
    cmd = [sys.executable, str(ROOT / "main.py"), "--db", str(db)]
    if now:
        cmd += ["--now", now]
    cmd += list(args)
    return subprocess.run(cmd, check=False, capture_output=True, text=True, cwd=ROOT)


def file_claim(db, now="2026-11-02T09:00:00"):
    return run(
        db, "file", "--passenger", "Asha Rao", "--flight", "OA101",
        "--type", "lost", "--tier", "gold", now=now,
    )


def test_file_then_list_shows_the_claim(tmp_path):
    db = tmp_path / "cli.db"
    assert file_claim(db).returncode == 0
    result = run(db, "list")
    assert result.returncode == 0
    assert "Asha Rao" in result.stdout


def test_now_option_is_used_for_escalate(tmp_path):
    db = tmp_path / "cli.db"
    file_claim(db, now="2026-11-02T09:00:00")

    on_time = run(db, "escalate", now="2026-11-02T13:00:00")
    assert on_time.returncode == 0
    assert run(db, "list", "--status", "escalated").stdout.count("Asha Rao") == 0

    late = run(db, "escalate", now="2026-11-02T13:01:00")
    assert late.returncode == 0
    assert "1" in late.stdout
    assert "Asha Rao" in run(db, "list", "--status", "escalated").stdout


def test_seed_loads_the_csv(tmp_path):
    db = tmp_path / "cli.db"
    result = run(db, "seed", str(ROOT / "seed_claims.csv"))
    assert result.returncode == 0
    with sqlite3.connect(db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
    assert count >= 10


def test_bad_status_change_shows_clear_error(tmp_path):
    db = tmp_path / "cli.db"
    file_claim(db)
    result = run(db, "close", "1")
    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "can't move" in output
    assert "Traceback" not in output