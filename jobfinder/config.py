import os
import re

import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def cv_prefix(cfg: dict) -> str:
    """Filename prefix for generated CVs, derived from the candidate's name.

    "Jordan Doe" -> "Jordan_Doe_CV"; empty/missing name falls back to "CV".
    """
    name = ((cfg.get("candidate") or {}).get("name") or "").strip()
    slug = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")
    return f"{slug}_CV" if slug else "CV"


def load_config(path: str | None = None) -> dict:
    cfg_path = path or os.path.join(PROJECT_ROOT, "config.yaml")
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)
    # Resolve relative paths against the project root. Absolute paths (e.g. a
    # resume kept in a separate repo) are left untouched.
    p = cfg["paths"]
    for key in ("output_dir", "db", "resume_repo", "profile", "base_cv"):
        if p.get(key) and not os.path.isabs(p[key]):
            p[key] = os.path.join(PROJECT_ROOT, p[key])
    return cfg
