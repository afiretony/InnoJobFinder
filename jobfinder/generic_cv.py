import hashlib
import json
import logging
import os
from datetime import date

from .claude_cli import RateLimitError, run_claude
from .config import PROJECT_ROOT, cv_prefix
from .tailor import ALLOWED_TOOLS

log = logging.getLogger("jobfinder.generic_cv")

PROMPT_PATH = os.path.join(PROJECT_ROOT, "prompts", "generic_cv.md")

SEED_JOBS = 5
SEED_DESC_CHARS = 1200

CATEGORY_BLURBS = {
    "forward_deployed": "customer-facing engineering: deploying the company's product into a customer's environment, integrating alongside their engineers",
    "ai_llm_engineer": "building applications on top of LLMs: agents, RAG, tool orchestration, LLM integration into a product",
    "inference_optimization": "making models run faster, smaller, or on constrained hardware: quantization, compilers, kernels, runtimes, on-device and edge deployment",
    "fullstack_product": "shipping product surface area: frontend and backend, APIs, user-facing features",
    "robotics_perception": "software for physical systems and visual understanding: robotics, embodied AI, autonomy, perception pipelines",
    "ml_research": "training and developing models: modeling, experimentation, novel architectures, publications",
    "general_swe": "general software engineering: backend services, distributed systems, internal tooling",
}


def _exclude_rule(cfg: dict, category: str) -> str:
    """Optional rule keeping a flagship project off categories that don't value it."""
    dp = (cfg.get("tailoring") or {}).get("deemphasize_project") or {}
    name = (dp.get("name") or "").strip()
    if name and category in set(dp.get("exclude_categories") or []):
        return (
            f"- **Do not include the {name} project anywhere on this CV** — not in the "
            "summary, experience, projects, or skills. This category does not value it, "
            "and it competes for one-page space with the work that does."
        )
    return ""


def profile_sha(cfg: dict) -> str:
    with open(cfg["paths"]["profile"], "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def generic_dir(cfg: dict, category: str) -> str:
    return os.path.join(cfg["paths"]["output_dir"], "generic", category)


def cv_path(cfg: dict, category: str) -> str:
    return os.path.join(generic_dir(cfg, category), f"{cv_prefix(cfg)}_{category}.pdf")


def read_meta(cfg: dict, category: str) -> dict | None:
    path = os.path.join(generic_dir(cfg, category), "meta.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def cv_status(cfg: dict, category: str) -> str:
    """'missing' | 'stale' | 'current'. Stale means it predates the current profile.md."""
    if not os.path.exists(cv_path(cfg, category)):
        return "missing"
    meta = read_meta(cfg, category)
    if not meta or meta.get("profile_sha") != profile_sha(cfg):
        return "stale"
    return "current"


def seed_jobs(conn, category: str, n: int = SEED_JOBS):
    return conn.execute(
        "SELECT id, title, company, description FROM jobs "
        "WHERE category = ? AND score IS NOT NULL AND status != 'duplicate' "
        "ORDER BY score DESC, discovered_at DESC LIMIT ?",
        (category, n),
    ).fetchall()


def _seed_blob(rows) -> str:
    parts = []
    for i, r in enumerate(rows, 1):
        desc = (r["description"] or "(no description captured)")[:SEED_DESC_CHARS]
        parts.append(f"### {i}. {r['title']} @ {r['company']}\n\n{desc}\n")
    return "\n".join(parts)


def render_prompt(cfg: dict, category: str, seed_rows, out_dir: str, today: str) -> str:
    """Build the agent prompt for one category. Pure, so the rules are testable."""
    prefix = cv_prefix(cfg)
    return (
        open(PROMPT_PATH)
        .read()
        .replace("{CATEGORY}", category)
        .replace("{CATEGORY_BLURB}", CATEGORY_BLURBS.get(category, category))
        .replace("{SEED_JOBS}", _seed_blob(seed_rows))
        .replace("{OUT_DIR}", out_dir)
        .replace("{PDF_NAME}", f"{prefix}_{category}.pdf")
        .replace("{TEX_NAME}", f"{prefix}_{category}.tex")
        .replace("{DATE}", today)
        .replace("{CATEGORY_RULES}", _exclude_rule(cfg, category))
    )


def build_generic_cv(conn, cfg: dict, category: str, force: bool = False) -> str | None:
    """Build one reusable CV for a category. Returns the pdf path on success."""
    status = cv_status(cfg, category)
    if status == "current" and not force:
        log.info("generic CV for %s is current; skipping (use --force to rebuild)", category)
        return cv_path(cfg, category)

    rows = seed_jobs(conn, category)
    if not rows:
        log.error("no classified jobs in category %s; cannot seed a CV", category)
        return None

    # Pin the hash of the profile the agent is about to read. Stamping meta.json
    # with a hash taken *after* the call would mark the CV current against a
    # profile.md it never saw, had the file changed mid-build.
    pinned_sha = profile_sha(cfg)

    out_dir = generic_dir(cfg, category)
    os.makedirs(out_dir, exist_ok=True)
    prompt = render_prompt(cfg, category, rows, out_dir, date.today().isoformat())

    t = cfg["tailoring"]
    log.info("building generic CV for %s (%d seed jobs) -> %s", category, len(rows), out_dir)
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
        raise
    except Exception as e:
        log.error("generic CV build failed for %s: %s", category, e)
        return None

    with open(os.path.join(out_dir, "agent_report.md"), "w") as f:
        f.write(result)

    if "STATUS: done" not in result or not os.path.exists(cv_path(cfg, category)):
        log.error("generic CV incomplete for %s (see %s/agent_report.md)", category, out_dir)
        return None

    meta = {
        "category": category,
        "profile_sha": pinned_sha,
        "seed_job_ids": [r["id"] for r in rows],
        "generated_at": date.today().isoformat(),
        "pdf": cv_path(cfg, category),
    }
    with open(os.path.join(out_dir, "meta.json"), "w") as f:
        json.dump(meta, f, indent=2)
    return cv_path(cfg, category)


def run_generic_cvs(conn, cfg: dict, categories=None, force: bool = False) -> dict:
    """Build generic CVs for the given categories (default: all). Returns {category: path|None}."""
    targets = categories or cfg["categories"]
    built = {}
    for category in targets:
        try:
            built[category] = build_generic_cv(conn, cfg, category, force=force)
        except RateLimitError as e:
            log.error("session limit hit; stopping generic CV builds: %s", e)
            break
    return built
