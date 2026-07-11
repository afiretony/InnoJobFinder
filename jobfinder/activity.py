"""What is jobfinder doing right now?

The dashboard's in-process `_busy` flag only knows about work the web app itself
started. A CLI invocation (`make classify`) or the systemd timer is invisible to
it. These helpers read /proc and the database instead, so any jobfinder work
shows up regardless of who launched it.

Linux-only, which matches where this pipeline runs.
"""

import os

from .config import PROJECT_ROOT
from .generic_cv import cv_status

LOCK_PATH = os.path.join(PROJECT_ROOT, "data", ".lock")


def _uptime() -> float:
    with open("/proc/uptime") as f:
        return float(f.read().split()[0])


def _cmdline(pid: str) -> list[str]:
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            raw = f.read()
    except OSError:
        return []
    return [p.decode("utf-8", "replace") for p in raw.split(b"\0") if p]


def _elapsed_seconds(pid: str) -> float | None:
    """Seconds since the process started, from /proc/<pid>/stat field 22."""
    try:
        with open(f"/proc/{pid}/stat") as f:
            after_comm = f.read().rsplit(") ", 1)[1]
    except (OSError, IndexError):
        return None
    fields = after_comm.split()
    try:
        # fields[0] is state (stat field 3), so stat field 22 is fields[19].
        start_ticks = int(fields[19])
    except (IndexError, ValueError):
        return None
    return max(0.0, _uptime() - start_ticks / os.sysconf("SC_CLK_TCK"))


def _pids() -> list[str]:
    if not os.path.isdir("/proc"):
        return []
    return [e for e in os.listdir("/proc") if e.isdigit()]


def running_jobs() -> list[dict]:
    """Every `python -m jobfinder <subcommand>` process, excluding the web server."""
    found = []
    for pid in _pids():
        argv = _cmdline(pid)
        if not argv or "jobfinder.web" in argv or "-m" not in argv:
            continue
        i = argv.index("-m")
        if i + 1 >= len(argv) or argv[i + 1] != "jobfinder":
            continue
        rest = [a for a in argv[i + 2 :] if not a.startswith("-")]
        found.append(
            {
                "pid": int(pid),
                "command": rest[0] if rest else "run",
                "elapsed_seconds": _elapsed_seconds(pid),
            }
        )
    return sorted(found, key=lambda d: d["pid"])


def model_calls_in_flight() -> int:
    """Headless `claude -p` subprocesses — a scoring, classify or tailoring call."""
    n = 0
    for pid in _pids():
        argv = _cmdline(pid)
        if argv and os.path.basename(argv[0]) == "claude" and "-p" in argv:
            n += 1
    return n


def lock_holder() -> int | None:
    """PID holding the pipeline lock, if it is still alive."""
    try:
        with open(LOCK_PATH) as f:
            pid = int(f.read().strip())
    except (OSError, ValueError):
        return None
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return None
    return pid


def snapshot(conn, cfg: dict) -> dict:
    """Database-derived progress: how far classification has got, and tier sizes."""
    min_score = cfg["tailoring"].get("min_score", 8)

    total = conn.execute("SELECT COUNT(*) FROM jobs WHERE status != 'duplicate'").fetchone()[0]
    classified = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE category IS NOT NULL AND status != 'duplicate'"
    ).fetchone()[0]
    by_category = {
        r[0]: r[1]
        for r in conn.execute(
            "SELECT category, COUNT(*) FROM jobs "
            "WHERE category IS NOT NULL AND status != 'duplicate' "
            "GROUP BY category ORDER BY 2 DESC"
        )
    }
    bespoke = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE status = 'matched' AND score >= ?", (min_score,)
    ).fetchone()[0]
    generic = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE status = 'matched' AND score < ?", (min_score,)
    ).fetchone()[0]
    unscored = conn.execute("SELECT COUNT(*) FROM jobs WHERE status = 'new'").fetchone()[0]

    return {
        "classify": {
            "classified": classified,
            "total": total,
            "remaining": total - classified,
            "by_category": by_category,
        },
        "tiers": {"bespoke": bespoke, "generic": generic, "min_score": min_score},
        "unscored": unscored,
        "generic_cvs": {c: cv_status(cfg, c) for c in cfg["categories"]},
    }
