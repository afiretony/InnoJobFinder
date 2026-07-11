import logging
import os
import subprocess
import sys
from collections import defaultdict
from datetime import datetime

from .generic_cv import cv_path, cv_status

log = logging.getLogger("jobfinder.report")

# The generic tier can run to hundreds of jobs; show the best of each category.
MAX_PER_CATEGORY = 20

CV_WARNING = {
    "current": "",
    "stale": "  ⚠️ **stale** — predates the current `profile.md`; rerun `make generic-cvs`",
    "missing": "  ⚠️ **missing** — run `make generic-cvs`",
}


def _job_line(r) -> str:
    return (
        f"- **{r['score']}/10** [{r['title']} @ {r['company']}]({r['url']}) "
        f"({r['location'] or 'n/a'}) — {r['fit_summary']}"
    )


def _backlog_lines(conn, cfg: dict) -> list[str]:
    min_score = cfg["tailoring"].get("min_score", 8)
    bespoke = conn.execute(
        "SELECT * FROM jobs WHERE status = 'matched' AND score >= ? "
        "ORDER BY score DESC, discovered_at DESC",
        (min_score,),
    ).fetchall()
    generic = conn.execute(
        "SELECT * FROM jobs WHERE status = 'matched' AND score < ? "
        "ORDER BY score DESC, discovered_at DESC",
        (min_score,),
    ).fetchall()

    lines = ["## Backlog", ""]
    lines.append(f"### Bespoke tier — score ≥ {min_score} — **{len(bespoke)}** awaiting a tailored CV")
    lines.append("")
    if bespoke:
        for r in bespoke[:MAX_PER_CATEGORY]:
            lines.append(_job_line(r))
        if len(bespoke) > MAX_PER_CATEGORY:
            lines.append(f"- …and **{len(bespoke) - MAX_PER_CATEGORY}** more")
    else:
        lines.append("_Empty — every strong match has a tailored CV._")
    lines.append("")

    lines.append(
        f"### Generic tier — score < {min_score} — **{len(generic)}** to apply with a category CV"
    )
    lines.append("")
    if not generic:
        lines.append("_Empty._")
        lines.append("")
        return lines

    by_cat = defaultdict(list)
    for r in generic:
        by_cat[r["category"] or "unclassified"].append(r)

    ordered = [c for c in cfg["categories"] if c in by_cat]
    ordered += sorted(c for c in by_cat if c not in cfg["categories"])

    for cat in ordered:
        rows = by_cat[cat]
        lines.append(f"#### `{cat}` — {len(rows)} jobs")
        if cat in cfg["categories"]:
            state = cv_status(cfg, cat)
            lines.append(f"CV: `{cv_path(cfg, cat)}`{CV_WARNING[state]}")
        elif cat == "unclassified":
            lines.append("_Not yet classified — run `make classify`._")
        else:
            lines.append("_No generic CV: category outside the configured set._")
        lines.append("")
        for r in rows[:MAX_PER_CATEGORY]:
            lines.append(_job_line(r))
        if len(rows) > MAX_PER_CATEGORY:
            lines.append(f"- …and **{len(rows) - MAX_PER_CATEGORY}** more")
        lines.append("")
    return lines


def write_digest(conn, cfg: dict, new_count: int, matched_rows, tailored_dirs) -> str:
    out = cfg["paths"]["output_dir"]
    digest_dir = os.path.join(out, "digests")
    os.makedirs(digest_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")

    scored = conn.execute(
        "SELECT * FROM jobs WHERE status IN ('scored','matched','tailored','error') "
        "AND replace(replace(discovered_at,'T',' '),'Z','') >= datetime('now', '-1 day') "
        "ORDER BY score DESC LIMIT 40"
    ).fetchall()

    lines = [
        f"# InnoJobFinder digest — {stamp}",
        "",
        f"- New jobs this run: **{new_count}**",
        f"- Strong matches this run: **{len(matched_rows)}**",
        f"- Tailored CV + email packages: **{len(tailored_dirs)}**",
        "",
    ]
    if tailored_dirs:
        lines.append("## Ready to apply (CV + cold email generated)")
        lines.append("")
        for d in tailored_dirs:
            lines.append(f"- `{d}`")
        lines.append("")
    if matched_rows:
        lines.append("## Strong matches this run")
        lines.append("")
        for r in matched_rows:
            lines.append(_job_line(r))
        lines.append("")

    lines += _backlog_lines(conn, cfg)

    lines.append("## Last 24h scoreboard")
    lines.append("")
    lines.append("| Score | Title | Company | Location | Status | Link |")
    lines.append("|---|---|---|---|---|---|")
    for r in scored:
        title = (r["title"] or "")[:60].replace("|", "/")
        lines.append(
            f"| {r['score']} | {title} | {r['company']} | {r['location'] or ''} "
            f"| {r['status']} | [link]({r['url']}) |"
        )
    content = "\n".join(lines) + "\n"

    path = os.path.join(digest_dir, f"{stamp}.md")
    with open(path, "w") as f:
        f.write(content)
    # Rolling pointer to the latest digest
    with open(os.path.join(out, "INBOX.md"), "w") as f:
        f.write(content)
    return path


def notify(cfg: dict, matched_rows, tailored_dirs):
    """Best-effort desktop notification when a run finds strong matches.

    Uses the OS's native mechanism: osascript on macOS, notify-send on Linux.
    No-op if disabled or unavailable.
    """
    if not cfg.get("notifications", {}).get("enabled"):
        return
    if not matched_rows and not tailored_dirs:
        return
    top = matched_rows[0] if matched_rows else None
    msg = f"{len(matched_rows)} strong match(es), {len(tailored_dirs)} CV(s) generated"
    subtitle = f"Top: {top['title']} @ {top['company']}" if top else ""
    if sys.platform == "darwin":
        cmd = ["osascript", "-e",
               f'display notification "{msg}" with title "InnoJobFinder" subtitle "{subtitle}"']
    else:
        cmd = ["notify-send", "InnoJobFinder", f"{msg}\n{subtitle}".strip()]
    try:
        subprocess.run(cmd, capture_output=True, timeout=10)
    except (FileNotFoundError, OSError, subprocess.SubprocessError) as e:
        log.warning("notification failed (%s not available?): %s", cmd[0], e)
