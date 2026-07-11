"""Local dashboard: python -m jobfinder.web  ->  http://127.0.0.1:8765"""

import glob
import logging
import os
import subprocess
import sys
import threading

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from . import activity, db
from .config import PROJECT_ROOT, load_config

log = logging.getLogger("jobfinder.web")

app = FastAPI(title="InnoJobFinder")
cfg = load_config()

STATIC_HTML = os.path.join(PROJECT_ROOT, "jobfinder", "dashboard.html")
USER_STATUSES = {"applied", "dismissed", "matched"}
_busy = {"run": False}


def _conn():
    return db.connect(cfg["paths"]["db"], cfg["matching"]["threshold"])


def _row_to_dict(r):
    d = dict(r)
    d["description"] = None  # list payloads stay light; detail endpoint has it
    return d


@app.get("/", response_class=HTMLResponse)
def index():
    return open(STATIC_HTML).read()


@app.get("/api/stats")
def stats():
    conn = _conn()
    rows = conn.execute("SELECT status, COUNT(*) n FROM jobs GROUP BY status").fetchall()
    by_status = {r["status"]: r["n"] for r in rows}
    total = sum(by_status.values())
    last = conn.execute("SELECT MAX(discovered_at) m FROM jobs").fetchone()["m"]
    return {"total": total, "by_status": by_status, "last_discovered": last, "running": _busy["run"]}


@app.get("/api/progress")
def progress():
    """Live view of any jobfinder work, however it was launched (CLI, timer, web)."""
    procs = activity.running_jobs()
    return {
        "active": procs,
        "busy": bool(procs) or _busy["run"],
        "web_busy": _busy["run"],
        "lock_pid": activity.lock_holder(),
        "model_calls": activity.model_calls_in_flight(),
        **activity.snapshot(_conn(), cfg),
    }


@app.get("/api/categories")
def categories():
    """Category buckets with counts, in the config's display order. '__none__' is unclassified."""
    conn = _conn()
    rows = conn.execute(
        "SELECT category, COUNT(*) n FROM jobs WHERE status != 'duplicate' GROUP BY category"
    ).fetchall()
    counts = {r["category"]: r["n"] for r in rows}
    ordered = [{"category": c, "n": counts.pop(c, 0)} for c in cfg["categories"]]
    null_n = counts.pop(None, 0)
    for cat in sorted(counts):  # anything the model produced outside the config set (e.g. 'unknown')
        ordered.append({"category": cat, "n": counts[cat]})
    if null_n:
        ordered.append({"category": "__none__", "n": null_n})
    return ordered


@app.get("/api/jobs")
def jobs(status: str = "", min_score: int = 0, q: str = "", category: str = "", limit: int = 200):
    conn = _conn()
    sql = "SELECT * FROM jobs WHERE COALESCE(score, 0) >= ?"
    params: list = [min_score]
    if status:
        sql += " AND status = ?"
        params.append(status)
    else:
        sql += " AND status != 'duplicate'"
    if category == "__none__":
        sql += " AND category IS NULL"
    elif category:
        sql += " AND category = ?"
        params.append(category)
    if q:
        sql += " AND (title LIKE ? OR company LIKE ?)"
        params += [f"%{q}%", f"%{q}%"]
    sql += " ORDER BY COALESCE(score,-1) DESC, discovered_at DESC LIMIT ?"
    params.append(limit)
    return [_row_to_dict(r) for r in conn.execute(sql, params)]


@app.get("/api/jobs/{jid}")
def job_detail(jid: str):
    conn = _conn()
    r = conn.execute("SELECT * FROM jobs WHERE id = ?", (jid,)).fetchone()
    if not r:
        raise HTTPException(404)
    d = dict(r)
    d["files"] = {}
    if d.get("app_dir") and os.path.isdir(d["app_dir"]):
        for name in ("cold_email.md", "notes.md"):
            p = os.path.join(d["app_dir"], name)
            if os.path.exists(p):
                d["files"][name] = open(p).read()
        pdfs = glob.glob(os.path.join(d["app_dir"], "*.pdf"))
        if pdfs:
            d["files"]["pdf"] = pdfs[0]
    return d


@app.get("/api/pdf/{jid}")
def job_pdf(jid: str):
    d = job_detail(jid)
    pdf = d["files"].get("pdf")
    if not pdf:
        raise HTTPException(404, "no PDF for this job")
    return FileResponse(pdf, media_type="application/pdf")


@app.get("/api/preview/{jid}")
def job_preview(jid: str):
    """First page of the tailored CV rendered to PNG (cached beside the PDF)."""
    d = job_detail(jid)
    pdf = d["files"].get("pdf")
    if not pdf:
        raise HTTPException(404, "no PDF for this job")
    cache = pdf + ".preview.png"
    if not os.path.exists(cache) or os.path.getmtime(cache) < os.path.getmtime(pdf):
        # pdftoppm (poppler) is cross-platform. -singlefile writes exactly <prefix>.png.
        prefix = cache[: -len(".png")]
        r = subprocess.run(
            ["pdftoppm", "-png", "-singlefile", "-f", "1", "-l", "1", "-r", "150", pdf, prefix],
            capture_output=True, timeout=30,
        )
        if r.returncode != 0 or not os.path.exists(cache):
            raise HTTPException(500, "preview rendering failed (is poppler/pdftoppm installed?)")
    return FileResponse(cache, media_type="image/png")


@app.post("/api/jobs/{jid}/status/{status}")
def set_status(jid: str, status: str):
    if status not in USER_STATUSES:
        raise HTTPException(400, f"status must be one of {sorted(USER_STATUSES)}")
    conn = _conn()
    if not conn.execute("SELECT 1 FROM jobs WHERE id = ?", (jid,)).fetchone():
        raise HTTPException(404)
    db.set_status(conn, jid, status)
    return {"ok": True}


@app.post("/api/jobs/{jid}/open")
def open_folder(jid: str):
    """Open the application folder in the OS file manager (local use only)."""
    conn = _conn()
    r = conn.execute("SELECT app_dir FROM jobs WHERE id = ?", (jid,)).fetchone()
    if not r or not r["app_dir"] or not os.path.isdir(r["app_dir"]):
        raise HTTPException(404, "no application folder yet")
    opener = "open" if sys.platform == "darwin" else "explorer" if os.name == "nt" else "xdg-open"
    try:
        subprocess.Popen([opener, r["app_dir"]])
    except (FileNotFoundError, OSError) as e:
        raise HTTPException(500, f"could not open folder ({opener}): {e}")
    return {"ok": True}


def _bg(target, *args):
    def wrap():
        try:
            target(*args)
        except Exception:
            log.exception("background task failed")
        finally:
            _busy["run"] = False

    _busy["run"] = True
    threading.Thread(target=wrap, daemon=True).start()


@app.post("/api/jobs/{jid}/tailor")
def tailor_now(jid: str):
    if _busy["run"]:
        return JSONResponse({"ok": False, "error": "a run is already in progress"}, 409)
    conn = _conn()
    r = conn.execute("SELECT * FROM jobs WHERE id = ?", (jid,)).fetchone()
    if not r:
        raise HTTPException(404)

    def work():
        from .tailor import tailor_job
        tailor_job(_conn(), cfg, r)

    _bg(work)
    return {"ok": True, "message": "tailoring started (takes a few minutes)"}


@app.post("/api/jobs/{jid}/email")
def regen_email(jid: str):
    if _busy["run"]:
        return JSONResponse({"ok": False, "error": "a run is already in progress"}, 409)
    conn = _conn()
    r = conn.execute("SELECT * FROM jobs WHERE id = ?", (jid,)).fetchone()
    if not r:
        raise HTTPException(404)
    if not r["app_dir"]:
        raise HTTPException(400, "tailor this job first")

    def work():
        from .tailor import email_job
        email_job(_conn(), cfg, r)

    _bg(work)
    return {"ok": True, "message": "email regeneration started (about a minute)"}


@app.post("/api/run")
def run_pipeline(hours: int = 0, no_tailor: bool = False):
    if _busy["run"]:
        return JSONResponse({"ok": False, "error": "a run is already in progress"}, 409)

    def work():
        cmd = [os.path.join(PROJECT_ROOT, ".venv", "bin", "python"), "-m", "jobfinder", "run"]
        if hours:
            cmd += ["--hours", str(hours)]
        if no_tailor:
            cmd += ["--no-tailor"]
        subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, timeout=5400)

    _bg(work)
    return {"ok": True, "message": "pipeline run started"}


def main():
    import os
    import uvicorn
    # Loopback by default: the dashboard has NO authentication. Only bind wider
    # than 127.0.0.1 on a network you trust (set JOBFINDER_HOST=0.0.0.0), and put
    # an authenticating reverse proxy in front of any public exposure.
    host = os.environ.get("JOBFINDER_HOST", "127.0.0.1")
    uvicorn.run(app, host=host, port=8765, log_level="warning")


if __name__ == "__main__":
    host = os.environ.get("JOBFINDER_HOST", "127.0.0.1")
    print(f"InnoJobFinder dashboard: http://{host}:8765")
    main()
