import argparse
import logging
import os
import sys

from . import db
from .classify import run_classify
from .config import PROJECT_ROOT, load_config
from .generic_cv import run_generic_cvs
from .match import run_match
from .report import notify, write_digest
from .scrape import run_scrape
from .tailor import run_tailor

LOCK_PATH = os.path.join(PROJECT_ROOT, "data", ".lock")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("jobfinder")


def acquire_lock() -> bool:
    os.makedirs(os.path.dirname(LOCK_PATH), exist_ok=True)
    if os.path.exists(LOCK_PATH):
        pid = open(LOCK_PATH).read().strip()
        if pid.isdigit():
            try:
                os.kill(int(pid), 0)
                log.warning("another run is active (pid %s); exiting", pid)
                return False
            except (ProcessLookupError, PermissionError):
                pass  # stale lock
    with open(LOCK_PATH, "w") as f:
        f.write(str(os.getpid()))
    return True


def release_lock():
    try:
        os.remove(LOCK_PATH)
    except FileNotFoundError:
        pass


def cmd_run(args, cfg, conn):
    if not acquire_lock():
        return 1
    try:
        new_count = run_scrape(conn, cfg, hours_old=args.hours)
        log.info("scrape done: %d new jobs", new_count)
        matched = run_match(conn, cfg)
        log.info("match done: %d above threshold", len(matched))
        tally = run_classify(conn, cfg)
        log.info("classify done: %s", dict(tally))
        # Draws from the score-ordered queue, not just this run's matches, so jobs
        # stranded by an earlier rate limit get retried.
        tailored = [] if args.no_tailor else run_tailor(conn, cfg)
        digest = write_digest(conn, cfg, new_count, matched, tailored)
        notify(cfg, matched, tailored)
        log.info("digest: %s", digest)
        print(digest)
        return 0
    finally:
        release_lock()


def cmd_tailor(args, cfg, conn):
    t = cfg["tailoring"]
    if args.ids:
        qmarks = ",".join("?" * len(args.ids))
        rows = conn.execute(
            f"SELECT * FROM jobs WHERE id IN ({qmarks})", args.ids
        ).fetchall()
    else:
        limit = t.get("max_per_run", 0) if args.limit is None else args.limit
        rows = db.tailor_queue(conn, limit, t.get("min_score", 0))
    if not rows:
        print("nothing to tailor", file=sys.stderr)
        return 0
    dirs = run_tailor(conn, cfg, rows=rows)
    for d in dirs:
        print(d)
    return 0 if len(dirs) == len(rows) else 1


def cmd_classify(args, cfg, conn):
    tally = run_classify(conn, cfg, limit=args.limit)
    for category, n in tally.most_common():
        print(f"{category:<24} {n}")
    return 0


def cmd_generic_cvs(args, cfg, conn):
    if args.category and args.category not in cfg["categories"]:
        print(f"unknown category: {args.category}", file=sys.stderr)
        return 1
    categories = [args.category] if args.category else None
    built = run_generic_cvs(conn, cfg, categories, force=args.force)
    rc = 0
    for category, path in built.items():
        if path:
            print(path)
        else:
            print(f"FAILED: {category}", file=sys.stderr)
            rc = 1
    return rc


def cmd_email(args, cfg, conn):
    from .tailor import email_job

    qmarks = ",".join("?" * len(args.ids))
    rows = conn.execute(f"SELECT * FROM jobs WHERE id IN ({qmarks})", args.ids).fetchall()
    ok = 0
    for row in rows:
        path = email_job(conn, cfg, row)
        if path:
            print(path)
            ok += 1
    return 0 if ok == len(args.ids) else 1


def cmd_list(args, cfg, conn):
    q = "SELECT id, score, status, title, company, location FROM jobs"
    params = []
    if args.status:
        q += " WHERE status = ?"
        params.append(args.status)
    q += " ORDER BY COALESCE(score, -1) DESC, discovered_at DESC LIMIT ?"
    params.append(args.limit)
    for r in conn.execute(q, params):
        score = r["score"] if r["score"] is not None else "-"
        print(f"{r['id']}  {score:>2}  {r['status']:<9} {r['title']} @ {r['company']} ({r['location']})")
    return 0


def cmd_show(args, cfg, conn):
    r = conn.execute("SELECT * FROM jobs WHERE id = ?", (args.id,)).fetchone()
    if not r:
        print("not found", file=sys.stderr)
        return 1
    for k in r.keys():
        v = r[k]
        if k == "description" and v:
            v = v[:2000]
        print(f"{k}: {v}")
    return 0


def main():
    ap = argparse.ArgumentParser(prog="jobfinder")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="full pipeline: scrape -> match -> tailor -> digest")
    p_run.add_argument("--hours", type=int, default=None, help="look-back window override")
    p_run.add_argument("--no-tailor", action="store_true")

    p_t = sub.add_parser("tailor", help="tailor from the match queue (or specific ids)")
    p_t.add_argument("ids", nargs="*")
    p_t.add_argument(
        "--limit",
        type=int,
        default=None,
        help="max jobs to tailor; 0 = uncapped. Default: tailoring.max_per_run. "
        "Ignored when explicit ids are given.",
    )

    p_c = sub.add_parser("classify", help="assign a category to unclassified jobs")
    p_c.add_argument("--limit", type=int, default=None, help="max jobs to classify")

    p_g = sub.add_parser("generic-cvs", help="build the reusable per-category CVs")
    p_g.add_argument("--category", help="build just this one")
    p_g.add_argument("--force", action="store_true", help="rebuild even if current")

    p_e = sub.add_parser("email", help="regenerate only the cold email for given job ids")
    p_e.add_argument("ids", nargs="+")

    p_l = sub.add_parser("list", help="list jobs")
    p_l.add_argument("--status")
    p_l.add_argument("--limit", type=int, default=30)

    p_s = sub.add_parser("show", help="show one job")
    p_s.add_argument("id")

    args = ap.parse_args()
    cfg = load_config()
    conn = db.connect(cfg["paths"]["db"], cfg["matching"]["threshold"])
    handler = {
        "run": cmd_run,
        "tailor": cmd_tailor,
        "classify": cmd_classify,
        "generic-cvs": cmd_generic_cvs,
        "email": cmd_email,
        "list": cmd_list,
        "show": cmd_show,
    }[args.cmd]
    sys.exit(handler(args, cfg, conn))


if __name__ == "__main__":
    main()
