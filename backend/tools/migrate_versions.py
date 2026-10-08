"""Rebuild profile_source without CHECK (id = 1) and with AUTOINCREMENT ids.
Idempotent; pass --check to report only. Back up first with tools/backup.py."""

import sqlite3
import sys
from pathlib import Path

DB = Path(__file__).resolve().parents[1] / "hired.db"

NEW_TABLE = """
CREATE TABLE profile_source_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text VARCHAR NOT NULL,
    updated_at DATETIME NOT NULL
)
"""


def shape(con: sqlite3.Connection) -> tuple[bool, bool, int]:
    """Return (has single-row CHECK, is AUTOINCREMENT, row count)."""
    sql = con.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='profile_source'"
    ).fetchone()
    if sql is None:
        raise SystemExit("No profile_source table. Start the app once first.")
    ddl = sql[0]
    rows = con.execute("SELECT count(*) FROM profile_source").fetchone()[0]
    return "id = 1" in ddl, "AUTOINCREMENT" in ddl.upper(), rows


def main() -> None:
    if not DB.exists():
        raise SystemExit(f"No database at {DB}")

    con = sqlite3.connect(DB)
    con.execute("PRAGMA foreign_keys=OFF")
    checked, autoinc, rows = shape(con)

    print(f"profile_source: {rows} row(s), single-row CHECK {checked}, AUTOINCREMENT {autoinc}")
    if "--check" in sys.argv:
        print("already migrated" if autoinc and not checked else "needs migrating")
        return
    if autoinc and not checked:
        print("already migrated, nothing to do")
        return

    # One transaction, so a crash leaves the original table intact.
    with con:
        con.execute(NEW_TABLE)
        con.execute(
            "INSERT INTO profile_source_new (id, text, updated_at) "
            "SELECT id, text, updated_at FROM profile_source ORDER BY id"
        )
        con.execute("DROP TABLE profile_source")
        con.execute("ALTER TABLE profile_source_new RENAME TO profile_source")

    after_checked, after_autoinc, after_rows = shape(con)
    if after_rows != rows or after_checked or not after_autoinc:
        raise SystemExit("migration did not land as expected; restore from backups/")

    # Seed sqlite_sequence from the copied rows, otherwise freed ids could be reused.
    top = con.execute("SELECT max(id) FROM profile_source").fetchone()[0] or 0
    with con:
        con.execute(
            "INSERT INTO sqlite_sequence (name, seq) SELECT 'profile_source', ? "
            "WHERE NOT EXISTS (SELECT 1 FROM sqlite_sequence WHERE name='profile_source')",
            (top,),
        )
        con.execute(
            "UPDATE sqlite_sequence SET seq = ? WHERE name = 'profile_source' AND seq < ?",
            (top, top),
        )
    seq = con.execute(
        "SELECT seq FROM sqlite_sequence WHERE name='profile_source'"
    ).fetchone()
    print(f"migrated: {after_rows} version(s), next id after {seq[0] if seq else 0}")


if __name__ == "__main__":
    main()
