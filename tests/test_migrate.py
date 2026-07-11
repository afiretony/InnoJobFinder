import os
import sqlite3

from jobfinder import db

# The schema as it existed before the category column was introduced.
OLD_SCHEMA = """
CREATE TABLE jobs (
    id            TEXT PRIMARY KEY,
    site          TEXT,
    title         TEXT,
    company       TEXT,
    location      TEXT,
    is_remote     INTEGER,
    url           TEXT,
    description   TEXT,
    date_posted   TEXT,
    search_term   TEXT,
    role_family   TEXT,
    discovered_at TEXT,
    score         INTEGER,
    fit_summary   TEXT,
    status        TEXT DEFAULT 'new',
    app_dir       TEXT,
    tailored_at   TEXT
);
"""


def make_old_db(path, rows=()):
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(OLD_SCHEMA)
    for jid, score, status in rows:
        conn.execute(
            "INSERT INTO jobs (id, score, status) VALUES (?, ?, ?)", (jid, score, status)
        )
    conn.commit()
    return conn


def status_of(conn, jid):
    return conn.execute("SELECT status FROM jobs WHERE id = ?", (jid,)).fetchone()[0]


def test_migrate_adds_category_column_and_sets_user_version(tmp_path):
    path = tmp_path / "jobs.db"
    conn = make_old_db(path)

    db.migrate(conn, str(path))

    assert "category" in {r[1] for r in conn.execute("PRAGMA table_info(jobs)")}
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 1


def test_migrate_repromotes_scored_jobs_at_or_above_threshold(tmp_path):
    path = tmp_path / "jobs.db"
    conn = make_old_db(
        path,
        rows=[
            ("at_threshold", 5, "scored"),
            ("above", 6, "scored"),
            ("below", 4, "scored"),
        ],
    )

    db.migrate(conn, str(path), apply_threshold=5)

    assert status_of(conn, "at_threshold") == "matched"
    assert status_of(conn, "above") == "matched"
    assert status_of(conn, "below") == "scored"


def test_migrate_leaves_terminal_and_human_statuses_untouched(tmp_path):
    path = tmp_path / "jobs.db"
    conn = make_old_db(
        path,
        rows=[
            ("applied", 9, "applied"),
            ("dismissed", 9, "dismissed"),
            ("tailored", 9, "tailored"),
            ("duplicate", 9, "duplicate"),
            ("errored", 9, "error"),
            ("new", None, "new"),
        ],
    )

    db.migrate(conn, str(path), apply_threshold=5)

    for jid in ("applied", "dismissed", "tailored", "duplicate", "new"):
        assert status_of(conn, jid) == jid
    assert status_of(conn, "errored") == "error"


def test_migrate_is_idempotent(tmp_path):
    path = tmp_path / "jobs.db"
    conn = make_old_db(path, rows=[("j", 6, "scored")])

    db.migrate(conn, str(path), apply_threshold=5)
    # A human dismisses the job after the first migration...
    conn.execute("UPDATE jobs SET status = 'dismissed' WHERE id = 'j'")
    conn.commit()
    db.migrate(conn, str(path), apply_threshold=5)

    # ...and a second migrate must not resurrect it.
    assert status_of(conn, "j") == "dismissed"


def test_migrate_backs_up_before_altering_an_existing_db(tmp_path):
    path = tmp_path / "jobs.db"
    conn = make_old_db(path, rows=[("j", 9, "applied")])

    db.migrate(conn, str(path), apply_threshold=5)

    baks = [p for p in os.listdir(tmp_path) if ".bak-" in p]
    assert len(baks) == 1
    restored = sqlite3.connect(str(tmp_path / baks[0]))
    assert restored.execute("SELECT status FROM jobs WHERE id='j'").fetchone()[0] == "applied"
    assert restored.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_connect_migrates_a_preexisting_database(tmp_path):
    """The real-world path: connect() runs SCHEMA then migrate() on an old DB."""
    path = tmp_path / "jobs.db"
    make_old_db(path, rows=[("j", 6, "scored")]).close()

    conn = db.connect(str(path), apply_threshold=5)

    assert "category" in {r[1] for r in conn.execute("PRAGMA table_info(jobs)")}
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
    assert status_of(conn, "j") == "matched"
    idx = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert "idx_jobs_category" in idx


def test_fresh_database_migrates_without_altering_or_backing_up(tmp_path):
    path = tmp_path / "jobs.db"

    conn = db.connect(str(path))

    assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
    assert "category" in {r[1] for r in conn.execute("PRAGMA table_info(jobs)")}
    assert [p for p in os.listdir(tmp_path) if ".bak-" in p] == []
