"""Back up hired.db (plus a plain master.md copy) into backups/ or argv[1], keeping the last 14.
Uses SQLite's online backup API, since copying a WAL-mode file mid-write can tear it."""

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
LIVE = BACKEND / "hired.db"
KEEP = 14


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
            # Fold the WAL into the file so the backup is one self-contained file.
            copy.execute("PRAGMA journal_mode=DELETE")
        finally:
            copy.close()
        row = source.execute("SELECT text FROM profile_source").fetchone()
    finally:
        source.close()

    if row:
        (into / f"master-{stamp}.md").write_text(row[0])

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

    # Read the backup back to verify it.
    check = sqlite3.connect(f"file:{written}?mode=ro", uri=True)
    apps = check.execute("SELECT count(*) FROM application").fetchone()[0]
    pdfs = check.execute("SELECT count(*) FROM application WHERE pdf IS NOT NULL").fetchone()[0]
    chars = check.execute("SELECT length(text) FROM profile_source").fetchone()
    check.close()
    print(f"verified: {apps} applications ({pdfs} with a PDF), profile {chars[0] if chars else 0} chars")
