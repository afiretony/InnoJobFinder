import json
import logging
import os
from collections import Counter

from . import db
from .claude_cli import RateLimitError, extract_json, run_claude
from .config import PROJECT_ROOT

log = logging.getLogger("jobfinder.classify")

PROMPT_PATH = os.path.join(PROJECT_ROOT, "prompts", "classify.md")

UNKNOWN = "unknown"


def normalize_category(value, allowed) -> str:
    """Map a model response onto the closed set. Anything unrecognized is 'unknown'."""
    if not isinstance(value, str):
        return UNKNOWN
    slug = value.strip().lower().replace("-", "_").replace(" ", "_")
    return slug if slug in allowed else UNKNOWN


def _job_payload(row, max_chars: int) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "company": row["company"],
        "description": (row["description"] or "")[:max_chars],
    }


def run_classify(conn, cfg: dict, limit: int | None = None) -> Counter:
    """Assign a category to every unclassified job. Returns a per-category tally."""
    m = cfg["matching"]
    allowed = set(cfg["categories"]) | {UNKNOWN}

    rows = db.jobs_needing_category(conn, limit)
    if not rows:
        log.info("no jobs need classifying")
        return Counter()

    template = open(PROMPT_PATH).read()

    batches, batch = [], []
    for row in rows:
        batch.append(row)
        if len(batch) >= m["batch_size"]:
            batches.append(batch)
            batch = []
    if batch:
        batches.append(batch)

    tally: Counter = Counter()
    for i, chunk in enumerate(batches):
        jobs_json = json.dumps(
            [_job_payload(r, m["description_max_chars"]) for r in chunk], indent=1
        )
        prompt = template.replace("{JOBS_JSON}", jobs_json)
        try:
            result = run_claude(
                prompt, model=m["model"], allowed_tools="", timeout=m["timeout_seconds"]
            )
            items = extract_json(result)
        except RateLimitError as e:
            log.error(
                "session limit hit; stopping classification (%d done, rest stay null): %s",
                sum(tally.values()),
                e,
            )
            break
        except Exception as e:
            log.error("classify batch %d failed: %s", i, e)
            continue

        by_id = {r["id"]: r for r in chunk}
        for item in items:
            jid = item.get("id")
            if jid not in by_id:
                continue
            raw = item.get("category")
            category = normalize_category(raw, allowed)
            if category == UNKNOWN and raw not in (None, UNKNOWN):
                log.warning("job %s: unrecognized category %r -> unknown", jid, raw)
            db.set_category(conn, jid, category)
            tally[category] += 1

    log.info("classified %d jobs: %s", sum(tally.values()), dict(tally))
    return tally
