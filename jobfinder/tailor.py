import logging
import os
import re
from datetime import date

from . import db
from .claude_cli import RateLimitError, run_claude
from .config import PROJECT_ROOT, cv_prefix

log = logging.getLogger("jobfinder.tailor")

PROMPT_PATH = os.path.join(PROJECT_ROOT, "prompts", "tailor.md")
EMAIL_PROMPT_PATH = os.path.join(PROJECT_ROOT, "prompts", "email.md")
EMAIL_STYLE_PATH = os.path.join(PROJECT_ROOT, "prompts", "email_style.md")

# Scoped tool allowlist for the headless tailoring agent: file edits plus the
# specific shell commands the tailor-cv skill needs (mkdir/cp/pdflatex, and
# pdftoppm to render a page for a visual one-page check).
ALLOWED_TOOLS = ",".join(
    [
        "Read",
        "Glob",
        "Grep",
        "Write",
        "Edit",
        "Bash(mkdir:*)",
        "Bash(cp:*)",
        "Bash(ls:*)",
        "Bash(cat:*)",
        "Bash(date:*)",
        "Bash(pdflatex:*)",
        "Bash(pdftoppm:*)",
        "Bash(grep:*)",
    ]
)


def _slug(text: str, max_words: int = 5) -> str:
    words = re.sub(r"[^A-Za-z0-9 ]+", " ", text or "").split()
    return "-".join(words[:max_words]) or "job"


def tailor_job(conn, cfg: dict, row) -> str | None:
    """Tailor CV + cold email for one matched job. Returns app_dir on success."""
    t = cfg["tailoring"]
    today = date.today().isoformat()
    app_dir = os.path.join(
        cfg["paths"]["output_dir"],
        "applications",
        f"{today}_{_slug(row['company'], 3)}_{_slug(row['title'])}_{row['id']}",
    )
    os.makedirs(app_dir, exist_ok=True)

    # Persist the JD alongside the outputs for reference
    with open(os.path.join(app_dir, "job.md"), "w") as f:
        f.write(
            f"# {row['title']} @ {row['company']}\n\n"
            f"- URL: {row['url']}\n- Location: {row['location']}\n"
            f"- Site: {row['site']} | Posted: {row['date_posted']} | Discovered: {row['discovered_at']}\n"
            f"- Score: {row['score']}/10 — {row['fit_summary']}\n\n## Description\n\n"
            f"{row['description'] or '(no description captured)'}\n"
        )

    template = open(PROMPT_PATH).read().replace("{EMAIL_STYLE}", open(EMAIL_STYLE_PATH).read())
    prompt = (
        template.replace("{TITLE}", row["title"] or "")
        .replace("{COMPANY}", row["company"] or "")
        .replace("{LOCATION}", row["location"] or "")
        .replace("{URL}", row["url"] or "")
        .replace("{SCORE}", str(row["score"]))
        .replace("{FIT}", row["fit_summary"] or "")
        .replace("{DESCRIPTION}", row["description"] or "(not captured — fetch is unavailable; tailor using the title and your judgment, conservatively)")
        .replace("{DATE}", today)
        .replace("{APP_DIR}", app_dir)
        .replace("{CV_PREFIX}", cv_prefix(cfg))
    )

    log.info("tailoring %s @ %s -> %s", row["title"], row["company"], app_dir)
    try:
        result = run_claude(
            prompt,
            model=t.get("model", ""),
            cwd=cfg["paths"]["resume_repo"],
            allowed_tools=ALLOWED_TOOLS,
            timeout=t["timeout_seconds"],
            thinking_tokens=t.get("thinking_tokens", 0),
        )
    except RateLimitError:
        # Leave the job as 'matched' so a later run retries it once the window resets.
        raise
    except Exception as e:
        log.error("tailoring failed for %s: %s", row["id"], e)
        db.set_status(conn, row["id"], "error", app_dir)
        return None

    with open(os.path.join(app_dir, "agent_report.md"), "w") as f:
        f.write(result)

    ok = "STATUS: done" in result and any(
        f.lower().endswith(".pdf") for f in os.listdir(app_dir)
    )
    if ok:
        db.set_status(conn, row["id"], "tailored", app_dir)
        return app_dir
    log.error("tailoring incomplete for %s (see %s/agent_report.md)", row["id"], app_dir)
    db.set_status(conn, row["id"], "error", app_dir)
    return None


def email_job(conn, cfg: dict, row) -> str | None:
    """Regenerate only the cold email for an already-tailored job."""
    t = cfg["tailoring"]
    app_dir = row["app_dir"]
    if not app_dir or not os.path.isdir(app_dir):
        log.error("no application folder for %s; tailor it first", row["id"])
        return None

    template = open(EMAIL_PROMPT_PATH).read().replace(
        "{EMAIL_STYLE}", open(EMAIL_STYLE_PATH).read()
    )
    prompt = (
        template.replace("{TITLE}", row["title"] or "")
        .replace("{COMPANY}", row["company"] or "")
        .replace("{LOCATION}", row["location"] or "")
        .replace("{URL}", row["url"] or "")
        .replace("{DESCRIPTION}", row["description"] or "(not captured)")
        .replace("{APP_DIR}", app_dir)
    )
    log.info("regenerating email for %s @ %s", row["title"], row["company"])
    try:
        result = run_claude(
            prompt,
            model=t.get("model", ""),
            cwd=cfg["paths"]["resume_repo"],
            allowed_tools="Read,Glob,Grep,Write,Edit",
            timeout=t["timeout_seconds"],
            thinking_tokens=t.get("thinking_tokens", 0),
        )
    except Exception as e:
        log.error("email regeneration failed for %s: %s", row["id"], e)
        return None
    if "STATUS: done" in result and os.path.exists(os.path.join(app_dir, "cold_email.md")):
        return os.path.join(app_dir, "cold_email.md")
    log.error("email regeneration incomplete for %s: %s", row["id"], result[:300])
    return None


def run_tailor(conn, cfg: dict, rows=None, limit: int | None = None) -> list[str]:
    """Tailor from the match queue (rows=None) or an explicit row list.

    The queue is score-ordered and capped, so a run stays inside the timer period.
    Explicit rows bypass the cap: that path is a deliberate manual invocation.
    """
    t = cfg["tailoring"]
    if not t.get("enabled", True):
        return []
    if rows is None:
        if limit is None:
            limit = t.get("max_per_run", 0)
        rows = db.tailor_queue(conn, limit, t.get("min_score", 0))
    done = []
    for row in rows:
        try:
            app_dir = tailor_job(conn, cfg, row)
        except RateLimitError as e:
            log.error("session limit hit; stopping tailoring (%d done, rest stay matched): %s",
                      len(done), e)
            break
        if app_dir:
            done.append(app_dir)
    return done
