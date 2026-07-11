import sqlite3

from jobfinder import db
from jobfinder.classify import UNKNOWN, normalize_category

ALLOWED = {"forward_deployed", "ai_llm_engineer", "general_swe", UNKNOWN}


def seed(tmp_path, rows):
    """rows: (id, score, status, discovered_at, category)"""
    conn = db.connect(str(tmp_path / "jobs.db"))
    for jid, score, status, discovered, category in rows:
        conn.execute(
            "INSERT INTO jobs (id, score, status, discovered_at, category) VALUES (?,?,?,?,?)",
            (jid, score, status, discovered, category),
        )
    conn.commit()
    return conn


def test_tailor_queue_orders_by_score_then_newest(tmp_path):
    conn = seed(
        tmp_path,
        [
            ("old9", 9, "matched", "2026-06-01", None),
            ("new9", 9, "matched", "2026-07-09", None),
            ("eight", 8, "matched", "2026-07-09", None),
        ],
    )

    assert [r["id"] for r in db.tailor_queue(conn)] == ["new9", "old9", "eight"]


def test_tailor_queue_applies_min_score_and_limit(tmp_path):
    conn = seed(
        tmp_path,
        [
            ("nine", 9, "matched", "2026-07-09", None),
            ("eight", 8, "matched", "2026-07-08", None),
            ("seven", 7, "matched", "2026-07-07", None),
            ("five", 5, "matched", "2026-07-06", None),
        ],
    )

    assert [r["id"] for r in db.tailor_queue(conn, min_score=8)] == ["nine", "eight"]
    assert [r["id"] for r in db.tailor_queue(conn, limit=1, min_score=8)] == ["nine"]
    # limit=0 means uncapped, not "no rows"
    assert len(db.tailor_queue(conn, limit=0, min_score=5)) == 4


def test_tailor_queue_ignores_non_matched_statuses(tmp_path):
    conn = seed(
        tmp_path,
        [
            ("done", 9, "tailored", "2026-07-09", None),
            ("gone", 9, "dismissed", "2026-07-09", None),
            ("live", 9, "matched", "2026-07-09", None),
        ],
    )

    assert [r["id"] for r in db.tailor_queue(conn, min_score=8)] == ["live"]


def test_jobs_needing_category_skips_classified_and_duplicates(tmp_path):
    conn = seed(
        tmp_path,
        [
            ("todo", 7, "matched", "2026-07-09", None),
            ("done", 7, "matched", "2026-07-09", "general_swe"),
            ("dup", 7, "duplicate", "2026-07-09", None),
        ],
    )

    assert [r["id"] for r in db.jobs_needing_category(conn)] == ["todo"]


def test_jobs_needing_category_puts_best_scores_first(tmp_path):
    conn = seed(
        tmp_path,
        [
            ("low", 2, "scored", "2026-07-09", None),
            ("high", 9, "matched", "2026-07-09", None),
            ("unscored", None, "new", "2026-07-09", None),
        ],
    )

    assert [r["id"] for r in db.jobs_needing_category(conn)] == ["high", "low", "unscored"]


def test_set_category_persists(tmp_path):
    conn = seed(tmp_path, [("j", 7, "matched", "2026-07-09", None)])

    db.set_category(conn, "j", "forward_deployed")

    assert conn.execute("SELECT category FROM jobs WHERE id='j'").fetchone()[0] == "forward_deployed"


def test_normalize_category_accepts_known_values():
    assert normalize_category("forward_deployed", ALLOWED) == "forward_deployed"


def test_normalize_category_tolerates_model_formatting():
    assert normalize_category("  Forward-Deployed  ", ALLOWED) == "forward_deployed"
    assert normalize_category("AI LLM Engineer", ALLOWED) == "ai_llm_engineer"


def test_normalize_category_rejects_invented_categories():
    assert normalize_category("staff_engineer", ALLOWED) == UNKNOWN
    assert normalize_category("", ALLOWED) == UNKNOWN
    assert normalize_category(None, ALLOWED) == UNKNOWN
    assert normalize_category(42, ALLOWED) == UNKNOWN
