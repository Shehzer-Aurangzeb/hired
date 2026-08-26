"""
Back up hired.db, and drop a plain copy of the master profile beside it.

Everything this app knows lives in one SQLite file: the master profile you wrote
by hand, every application, and every PDF you sent. Losing the container loses
all of it, so this runs on a timer rather than on good intentions.

    .venv/bin/python tools/backup.py                  # into backups/
    .venv/bin/python tools/backup.py /some/where      # into somewhere else

Daily, via crontab -e:

    0 3 * * * cd /path/to/hired/backend && .venv/bin/python tools/backup.py

The database copy uses SQLite's online backup API rather than cp, because the
app runs in WAL mode: copying the file while a write is in flight can capture a
torn database that only fails when you try to restore it.

master.md is written out as well. It is recoverable from the .db, but the whole
profile is one text file and a copy you can open in any editor is worth the
few kilobytes.
"""

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
LIVE = BACKEND / "hired.db"
KEEP = 14  # ponytail: a fortnight of dailies. Longer if you ever need to go back further.


def backup(into: Path) -> Path:
    if not LIVE.exists():
        raise SystemExit(f"No database at {LIVE}. Nothing to back up.")

    into.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    target = into / f"hired-{stamp}.db"

    source = sqlite3.connect(f"file:{LIVE}?mode=ro", uri=True)
    try:
        copy = sqlite3.connect(target)
        try:
            source.backup(copy)
            # Fold the write-ahead log into the file itself, so the backup is one
            # file rather than three. A restore that quietly leaves the -wal
            # behind is a restore missing its most recent writes.
            copy.execute("PRAGMA journal_mode=DELETE")
        finally:
            copy.close()
        row = source.execute("SELECT text FROM profile_source").fetchone()
    finally:
        source.close()

    if row:
        (into / f"master-{stamp}.md").write_text(row[0])

    # A backup that fills the disk stops being a backup.
    for old in sorted(into.glob("hired-*.db"))[:-KEEP]:
        old.unlink()
        stale = into / old.name.replace("hired-", "master-").replace(".db", ".md")
        stale.unlink(missing_ok=True)

    return target


if __name__ == "__main__":
    into = Path(sys.argv[1]) if len(sys.argv) > 1 else BACKEND / "backups"
    written = backup(into)
    size = written.stat().st_size
    print(f"{written}  ({size / 1024:.0f} KB)")

    # A backup nobody has opened is a guess. Read it back before saying it worked.
    check = sqlite3.connect(f"file:{written}?mode=ro", uri=True)
    apps = check.execute("SELECT count(*) FROM application").fetchone()[0]
    pdfs = check.execute("SELECT count(*) FROM application WHERE pdf IS NOT NULL").fetchone()[0]
    chars = check.execute("SELECT length(text) FROM profile_source").fetchone()
    check.close()
    print(f"verified: {apps} applications ({pdfs} with a PDF), profile {chars[0] if chars else 0} chars")
