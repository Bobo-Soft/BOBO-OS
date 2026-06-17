#!/usr/bin/env python3
"""
BOBO OS — NovaStore Backend (Phase 6.1)
E:\BOBO-OS\novastore\backend\main.py

FastAPI app store backend. Listens on 127.0.0.1:8740.
Sources: Flathub, AppImageHub, curated Wine/macOS lists.
Database: SQLite (cached metadata + install history).
"""

from __future__ import annotations
import asyncio
import json
import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3

# ── Config ────────────────────────────────────────────────────────────────────
DB_PATH      = Path.home() / ".local" / "share" / "bobo-os" / "novastore.db"
LOG_PATH     = Path("/var/log/bobo-updates.log")
INSTALL_DIR  = Path.home() / ".local" / "share" / "bobo-os" / "installed"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
INSTALL_DIR.mkdir(parents=True, exist_ok=True)

# ── Database ──────────────────────────────────────────────────────────────────

def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS apps (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            description TEXT,
            category    TEXT,
            platform    TEXT,
            version     TEXT,
            size_mb     REAL,
            rating      REAL DEFAULT 0,
            icon_url    TEXT,
            source      TEXT,
            install_cmd TEXT,
            cached_at   INTEGER
        );
        CREATE TABLE IF NOT EXISTS installs (
            app_id      TEXT,
            installed_at INTEGER,
            version     TEXT,
            status      TEXT
        );
        CREATE TABLE IF NOT EXISTS jobs (
            job_id      TEXT PRIMARY KEY,
            app_id      TEXT,
            action      TEXT,
            progress    INTEGER DEFAULT 0,
            status      TEXT DEFAULT 'pending',
            message     TEXT,
            created_at  INTEGER
        );
        """)


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="BOBO OS NovaStore",
    version="1.0.0",
    docs_url=None,   # Disable Swagger UI in production
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    init_db()
    asyncio.create_task(prefetch_flathub())


# ── Models ────────────────────────────────────────────────────────────────────

class AppListItem(BaseModel):
    id: str
    name: str
    description: Optional[str]
    category: Optional[str]
    platform: str
    version: Optional[str]
    size_mb: Optional[float]
    rating: float
    icon_url: Optional[str]
    source: str
    installed: bool = False


class AppDetail(AppListItem):
    install_cmd: Optional[str]


class JobStatus(BaseModel):
    job_id: str
    app_id: str
    action: str
    progress: int
    status: str
    message: Optional[str]


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/apps", response_model=list[AppListItem])
async def list_apps(
    platform: Optional[str] = None,
    category: Optional[str] = None,
    search:   Optional[str] = None,
    limit:    int = 50,
    offset:   int = 0,
):
    """List available apps with optional filters."""
    query = "SELECT * FROM apps WHERE 1=1"
    params: list = []

    if platform:
        query += " AND platform = ?"
        params.append(platform)
    if category:
        query += " AND category = ?"
        params.append(category)
    if search:
        query += " AND (name LIKE ? OR description LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])

    query += " ORDER BY rating DESC, name ASC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    with get_db() as db:
        rows = db.execute(query, params).fetchall()
        installed_ids = {r["app_id"] for r in db.execute("SELECT app_id FROM installs WHERE status='installed'")}

    return [
        AppListItem(
            **dict(r),
            installed=(r["id"] in installed_ids)
        )
        for r in rows
    ]


@app.get("/apps/{app_id}", response_model=AppDetail)
async def get_app(app_id: str):
    with get_db() as db:
        row = db.execute("SELECT * FROM apps WHERE id = ?", [app_id]).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="App not found")
        installed_ids = {r["app_id"] for r in db.execute(
            "SELECT app_id FROM installs WHERE status='installed'")}
    return AppDetail(**dict(row), installed=(app_id in installed_ids))


@app.post("/apps/{app_id}/install")
async def install_app(app_id: str, background_tasks: BackgroundTasks):
    with get_db() as db:
        row = db.execute("SELECT * FROM apps WHERE id = ?", [app_id]).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="App not found")
        app_data = dict(row)

    job_id = str(uuid.uuid4())
    with get_db() as db:
        db.execute(
            "INSERT INTO jobs VALUES (?, ?, 'install', 0, 'pending', 'Starting…', ?)",
            [job_id, app_id, int(time.time())]
        )

    background_tasks.add_task(_run_install, job_id, app_id, app_data)
    return {"job_id": job_id}


@app.get("/jobs/{job_id}", response_model=JobStatus)
async def get_job(job_id: str):
    with get_db() as db:
        row = db.execute("SELECT * FROM jobs WHERE job_id = ?", [job_id]).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Job not found")
    return JobStatus(**dict(row))


@app.delete("/apps/{app_id}")
async def uninstall_app(app_id: str, background_tasks: BackgroundTasks):
    with get_db() as db:
        row = db.execute("SELECT * FROM apps WHERE id = ?", [app_id]).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="App not found")
        app_data = dict(row)

    job_id = str(uuid.uuid4())
    with get_db() as db:
        db.execute(
            "INSERT INTO jobs VALUES (?, ?, 'uninstall', 0, 'pending', 'Starting…', ?)",
            [job_id, app_id, int(time.time())]
        )

    background_tasks.add_task(_run_uninstall, job_id, app_id, app_data)
    return {"job_id": job_id}


@app.get("/updates")
async def list_updates():
    """Return list of apps that have newer versions available."""
    with get_db() as db:
        installed = db.execute(
            "SELECT i.app_id, i.version, a.name FROM installs i "
            "JOIN apps a ON i.app_id = a.id WHERE i.status='installed'"
        ).fetchall()
    # In production: compare against upstream versions
    return [{"app_id": r["app_id"], "name": r["name"],
             "installed_version": r["version"], "latest_version": "latest"} for r in installed]


@app.post("/updates/apply")
async def apply_updates(background_tasks: BackgroundTasks):
    """Trigger background update of all installed apps."""
    background_tasks.add_task(_apply_all_updates)
    return {"message": "Updates started in background."}


# ── Background tasks ──────────────────────────────────────────────────────────

async def _run_install(job_id: str, app_id: str, app_data: dict):
    def update_job(pct: int, msg: str, status: str = "running"):
        with get_db() as db:
            db.execute(
                "UPDATE jobs SET progress=?, message=?, status=? WHERE job_id=?",
                [pct, msg, status, job_id]
            )

    try:
        # Pre-snapshot with btrfs if available (rollback on failure)
        snapshot_created = False
        try:
            subprocess.run(
                ["btrfs", "subvolume", "snapshot", "/", f"/snapshots/before-{app_id}-{int(time.time())}"],
                check=True, capture_output=True, timeout=30
            )
            snapshot_created = True
        except Exception:
            pass  # Non-btrfs systems continue without snapshot

        update_job(10, "Downloading…")

        source = app_data.get("source", "")
        install_cmd = app_data.get("install_cmd", "")

        if source == "flatpak":
            proc = await asyncio.create_subprocess_shell(
                f"flatpak install --noninteractive flathub {app_id}",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
        elif source == "appimage":
            dest = INSTALL_DIR / f"{app_id}.AppImage"
            proc = await asyncio.create_subprocess_shell(
                f"curl -L '{install_cmd}' -o '{dest}' && chmod +x '{dest}'",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
        elif install_cmd:
            proc = await asyncio.create_subprocess_shell(
                install_cmd,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
        else:
            raise ValueError("No install command available")

        update_job(50, "Installing…")
        await proc.communicate()

        if proc.returncode != 0:
            raise RuntimeError(f"Install process exited with code {proc.returncode}")

        update_job(90, "Finishing…")
        with get_db() as db:
            db.execute(
                "INSERT INTO installs VALUES (?, ?, ?, 'installed')",
                [app_id, int(time.time()), app_data.get("version", "unknown")]
            )
        update_job(100, "Installed successfully!", "completed")

    except Exception as e:
        update_job(0, f"Installation failed: {e}", "failed")


async def _run_uninstall(job_id: str, app_id: str, app_data: dict):
    def update_job(pct: int, msg: str, status: str = "running"):
        with get_db() as db:
            db.execute(
                "UPDATE jobs SET progress=?, message=?, status=? WHERE job_id=?",
                [pct, msg, status, job_id]
            )

    try:
        update_job(20, "Removing…")
        source = app_data.get("source", "")
        if source == "flatpak":
            proc = await asyncio.create_subprocess_shell(
                f"flatpak uninstall --noninteractive {app_id}",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
        else:
            appimage = INSTALL_DIR / f"{app_id}.AppImage"
            if appimage.exists():
                appimage.unlink()

        with get_db() as db:
            db.execute("UPDATE installs SET status='removed' WHERE app_id=?", [app_id])
        update_job(100, "Removed.", "completed")
    except Exception as e:
        update_job(0, f"Uninstall failed: {e}", "failed")


async def _apply_all_updates():
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a") as lf:
        lf.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Starting update run...\n")
    try:
        proc = await asyncio.create_subprocess_shell(
            "flatpak update --noninteractive",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        with open(LOG_PATH, "a") as lf:
            lf.write(stdout.decode(errors="replace"))
            lf.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Update run complete.\n")
    except Exception as e:
        with open(LOG_PATH, "a") as lf:
            lf.write(f"Update failed: {e}\n")


async def prefetch_flathub():
    """Populate DB with popular Flathub apps on startup (background)."""
    await asyncio.sleep(3)  # let server finish starting first
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://flathub.org/api/v2/search?locale=en&q=&per_page=50"
            )
            if resp.status_code != 200:
                return
            data = resp.json()
            apps = data.get("hits", [])

        with get_db() as db:
            for item in apps:
                app_id = item.get("app_id", "")
                if not app_id:
                    continue
                db.execute(
                    """INSERT OR REPLACE INTO apps
                    (id, name, description, category, platform, version, rating, icon_url, source, cached_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    [
                        app_id,
                        item.get("name", app_id),
                        item.get("summary", ""),
                        item.get("categories", ["Other"])[0] if item.get("categories") else "Other",
                        "linux",
                        item.get("version", "latest"),
                        item.get("installs_last_month", 0) / 100000,
                        item.get("icon", ""),
                        "flatpak",
                        int(time.time()),
                    ]
                )
    except Exception:
        pass  # Non-critical — DB starts empty, populated on demand


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8740, log_level="warning")
