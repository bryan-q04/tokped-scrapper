"""Web UI + API to trigger the scraper and view reports.

Runs on the VPS (uvicorn) behind nginx/SSL. It shells out to the existing runner as a
background job, then serves the generated HTML report + CSV downloads from data/.
Protect mutating calls with TOKPED_WEB_TOKEN (sent as the `x-web-token` header).
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

APP_DIR = Path(__file__).resolve().parent
POC_ROOT = APP_DIR.parent
SRC = POC_ROOT / "src"
DATA = POC_ROOT / "data"

app = FastAPI(title="Tokped Scraper")

_lock = threading.Lock()
_job = {"status": "idle", "started_at": None, "finished_at": None,
        "returncode": None, "args": None, "log_tail": ""}


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


_MAX_LOG = 12000  # chars of tail kept in memory / sent to the browser
_TIMEOUT = 3600   # hard wall-clock cap (s); watchdog kills a hung runner


def _run(args):
    with _lock:
        _job.update(status="running", started_at=_now(), finished_at=None,
                    returncode=None, args=args, log_tail="")
    buf = ""
    try:
        # -u + PYTHONUNBUFFERED so child output reaches the pipe immediately (no block
        # buffering), and merge stderr into stdout so the logging lines stream in order.
        env = {**os.environ, "PYTHONUNBUFFERED": "1"}
        p = subprocess.Popen(
            [sys.executable, "-u", str(SRC / "runner.py"), *args],
            cwd=str(POC_ROOT), env=env, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, bufsize=1,
        )

        deadline = time.time() + _TIMEOUT

        def _watchdog():
            while p.poll() is None:
                if time.time() > deadline:
                    p.kill()
                    return
                time.sleep(5)
        threading.Thread(target=_watchdog, daemon=True).start()

        for line in p.stdout:            # blocks per line; updates the live tail
            buf = (buf + line)[-_MAX_LOG:]
            with _lock:
                _job["log_tail"] = buf
        p.wait()
        with _lock:
            _job.update(status="done" if p.returncode == 0 else "failed",
                        finished_at=_now(), returncode=p.returncode, log_tail=buf)
    except Exception as e:  # noqa: BLE001
        with _lock:
            _job.update(status="failed", finished_at=_now(), returncode=-1,
                        log_tail=(buf + "\n" + str(e))[-_MAX_LOG:])


def _auth(request: Request):
    token = os.environ.get("TOKPED_WEB_TOKEN", "")
    if token and request.headers.get("x-web-token", "") != token:
        raise HTTPException(status_code=401, detail="unauthorized")


def _as_list(v):
    if not v:
        return []
    seq = v if isinstance(v, list) else str(v).split(",")
    return [x.strip() for x in seq if x.strip()]


@app.get("/", response_class=HTMLResponse)
def index():
    return (APP_DIR / "static" / "index.html").read_text(encoding="utf-8")


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/api/run")
async def api_run(request: Request):
    _auth(request)
    with _lock:
        if _job["status"] == "running":
            return JSONResponse({"error": "a run is already in progress"}, status_code=409)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}

    args = []
    if kw := _as_list(body.get("keywords")):
        args += ["--keywords", *kw]
    if ct := _as_list(body.get("cities")):
        args += ["--cities", *ct]
    if body.get("exclude_official"):
        args.append("--exclude-official")
    if body.get("show_adult"):
        args.append("--show-adult")
    if body.get("reset_today", True):
        args.append("--reset-today")

    threading.Thread(target=_run, args=(args,), daemon=True).start()
    return {"status": "started", "args": args}


@app.get("/api/status")
def api_status():
    with _lock:
        return dict(_job)


@app.get("/api/reports")
def api_reports():
    return {
        "reports": sorted(p.name for p in DATA.glob("export_*.html")),
        "csv": sorted(p.name for p in DATA.glob("export_*.csv")),
        "sellers": sorted(p.name for p in DATA.glob("sellers_*.csv")),
    }


@app.get("/report/latest", response_class=HTMLResponse)
def report_latest():
    files = sorted(DATA.glob("export_*.html"))
    if not files:
        return HTMLResponse("<p style='font-family:sans-serif'>No report yet — run a scrape.</p>",
                            status_code=404)
    return files[-1].read_text(encoding="utf-8")


@app.get("/download/{name}")
def download(name: str):
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(400, "bad name")
    f = DATA / name
    if not f.exists() or f.suffix not in (".csv", ".html"):
        raise HTTPException(404, "not found")
    return FileResponse(str(f), filename=name)
