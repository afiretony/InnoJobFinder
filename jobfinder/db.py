import hashlib
import logging
import os
import sqlite3
from datetime import datetime, timezone

log = logging.getLogger("jobfinder.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
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
    category      TEXT,                -- one of config categories, or 'unknown'
    status        TEXT DEFAULT 'new',  -- new | scored | matched | tailored | duplicate | error
    app_dir       TEXT,
    tailored_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_company_title ON jobs(company, title);
-- idx_jobs_category is created by migrate(): on a pre-existing database the
-- column does not exist yet when this script runs.
"""

SCHEMA_VERSION = 1
DEFAULT_APPLY_THRESHOLD = 5


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def _backup(conn: sqlite3.Connection, db_path: str) -> str:
    """Consistent snapshot via SQLite's backup API, before any destructive DDL/DML."""
    bak = f"{db_path}.bak-{datetime.now().strftime('%Y%m%d')}"
    if os.path.exists(bak):
        return bak
    dest = sqlite3.connect(bak)
    with dest:
        conn.backup(dest)
    dest.close()
    log.warning("backed up database to %s", bak)
    return bak


def migrate(
    conn: sqlite3.Connection, db_path: str, apply_threshold: int = DEFAULT_APPLY_THRESHOLD
) -> int:
    """Bring an existing database up to SCHEMA_VERSION. Idempotent."""
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version >= SCHEMA_VERSION:
        return version

    if "category" not in _columns(conn, "jobs"):
        _backup(conn, db_path)
        conn.execute("ALTER TABLE jobs ADD COLUMN category TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_category ON jobs(category)")
    # The apply threshold dropped (bespoke CVs are no longer the only outcome), so
    # jobs previously parked at 'scored' are now worth applying to.
    conn.execute(
        "UPDATE jobs SET status = 'matched' WHERE status = 'scored' AND score >= ?",
        (apply_threshold,),
    )
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()
    return SCHEMA_VERSION


def job_id(url: str) -> str:
    return hashlib.sha1(url.strip().encode()).hexdigest()[:12]


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def connect(
    db_path: str, apply_threshold: int = DEFAULT_APPLY_THRESHOLD
) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    migrate(conn, db_path, apply_threshold)
    return conn


def insert_job(conn: sqlite3.Connection, job: dict) -> bool:
    """Insert a job if unseen. Returns True if newly inserted.

    A job already seen at the same URL is skipped. A job with the same
    (company, title) as an existing row is stored but marked 'duplicate'
    so it never gets scored/tailored twice across sites.
    """
    jid = job_id(job["url"])
    cur = conn.execute("SELECT 1 FROM jobs WHERE id = ?", (jid,))
    if cur.fetchone():
        return False

    status = "new"
    if job.get("company") and job.get("title"):
        cur = conn.execute(
            "SELECT 1 FROM jobs WHERE lower(company) = lower(?) AND lower(title) = lower(?)",
            (job["company"], job["title"]),
        )
        if cur.fetchone():
            status = "duplicate"

    conn.execute(
        """INSERT INTO jobs (id, site, title, company, location, is_remote, url,
                             description, date_posted, search_term, role_family,
                             discovered_at, status)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            jid,
            job.get("site"),
            job.get("title"),
            job.get("company"),
            job.get("location"),
            1 if job.get("is_remote") else 0,
            job["url"],
            job.get("description"),
            job.get("date_posted"),
            job.get("search_term"),
            job.get("role_family"),
            now_iso(),
            status,
        ),
    )
    conn.commit()
    return status == "new"


def jobs_with_status(conn: sqlite3.Connection, status: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM jobs WHERE status = ? ORDER BY discovered_at", (status,)
    ).fetchall()


def tailor_queue(
    conn: sqlite3.Connection, limit: int | None = None, min_score: int = 0
) -> list[sqlite3.Row]:
    """Matched jobs awaiting a bespoke CV, best first. limit of 0/None means all."""
    sql = (
        "SELECT * FROM jobs WHERE status = 'matched' AND score >= ? "
        "ORDER BY score DESC, discovered_at DESC"
    )
    params: list = [min_score]
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    return conn.execute(sql, params).fetchall()


def jobs_needing_category(
    conn: sqlite3.Connection, limit: int | None = None
) -> list[sqlite3.Row]:
    """Unclassified jobs, best-scoring first so a rate limit truncates the tail."""
    sql = (
        "SELECT * FROM jobs WHERE category IS NULL AND status != 'duplicate' "
        "ORDER BY COALESCE(score, -1) DESC, discovered_at DESC"
    )
    params: list = []
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    return conn.execute(sql, params).fetchall()


def set_category(conn: sqlite3.Connection, jid: str, category: str):
    conn.execute("UPDATE jobs SET category = ? WHERE id = ?", (category, jid))
    conn.commit()


def set_score(conn: sqlite3.Connection, jid: str, score: int, fit_summary: str, threshold: int):
    status = "matched" if score >= threshold else "scored"
    conn.execute(
        "UPDATE jobs SET score = ?, fit_summary = ?, status = ? WHERE id = ?",
        (score, fit_summary, status, jid),
    )
    conn.commit()


def set_status(conn: sqlite3.Connection, jid: str, status: str, app_dir: str | None = None):
    if app_dir:
        conn.execute(
            "UPDATE jobs SET status = ?, app_dir = ?, tailored_at = ? WHERE id = ?",
            (status, app_dir, now_iso(), jid),
        )
    else:
        conn.execute("UPDATE jobs SET status = ? WHERE id = ?", (status, jid))
    conn.commit()
