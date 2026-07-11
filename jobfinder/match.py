import json
import logging
import os

from . import db
from .claude_cli import RateLimitError, extract_json, run_claude
from .config import PROJECT_ROOT

log = logging.getLogger("jobfinder.match")

PROMPT_PATH = os.path.join(PROJECT_ROOT, "prompts", "match.md")


def _job_payload(row, max_chars: int) -> dict:
    desc = (row["description"] or "")[:max_chars]
    return {
        "id": row["id"],
        "title": row["title"],
        "company": row["company"],
        "location": row["location"],
        "remote": bool(row["is_remote"]),
        "description": desc,
    }


def run_match(conn, cfg: dict) -> list:
    """Score all 'new' jobs. Returns rows of matched (above-threshold) jobs."""
    m = cfg["matching"]
    new_jobs = db.jobs_with_status(conn, "new")
    if not new_jobs:
        log.info("no new jobs to score")
        return []

    with open(cfg["paths"]["profile"]) as f:
        profile = f.read()
    # Constraints (seniority, target roles, location, dealbreakers) are the user's
    # own, so they live in config.yaml rather than being baked into the prompt.
    template = open(PROMPT_PATH).read().replace(
        "{CONSTRAINTS}", (m.get("constraints") or "(none specified)").strip()
    )

    batch, batches = [], []
    for row in new_jobs:
        batch.append(row)
        if len(batch) >= m["batch_size"]:
            batches.append(batch)
            batch = []
    if batch:
        batches.append(batch)

    matched_ids = []
    for i, rows in enumerate(batches):
        jobs_json = json.dumps(
            [_job_payload(r, m["description_max_chars"]) for r in rows], indent=1
        )
        prompt = template.replace("{PROFILE}", profile).replace("{JOBS_JSON}", jobs_json)
        try:
            result = run_claude(
                prompt, model=m["model"], allowed_tools="", timeout=m["timeout_seconds"]
            )
            scores = extract_json(result)
        except RateLimitError as e:
            log.error("session limit hit; stopping scoring (unscored jobs stay 'new'): %s", e)
            break
        except Exception as e:
            log.error("scoring batch %d failed: %s", i, e)
            continue

        by_id = {r["id"]: r for r in rows}
        for item in scores:
            jid = item.get("id")
            if jid not in by_id:
                continue
            score = int(item.get("score", 0))
            db.set_score(conn, jid, score, item.get("fit", ""), m["threshold"])
            if score >= m["threshold"]:
                matched_ids.append(jid)
            log.info(
                "scored %s | %s @ %s -> %d",
                jid,
                by_id[jid]["title"],
                by_id[jid]["company"],
                score,
            )

    if matched_ids:
        qmarks = ",".join("?" * len(matched_ids))
        return conn.execute(
            f"SELECT * FROM jobs WHERE id IN ({qmarks}) ORDER BY score DESC", matched_ids
        ).fetchall()
    return []
