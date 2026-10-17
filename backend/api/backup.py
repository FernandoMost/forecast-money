"""
api/backup.py — encrypted full-data backup export/restore.

The whole app state lives in data/ (auth.db, shared.db, users/*.db). These
endpoints package it as a single AES-256 encrypted zip so the user can move
their environment between machines without anything leaving their control.

Endpoints:
  POST /backup/export   — {password} → AES-256 zip download
  POST /backup/restore  — multipart file + password → validate, auto-backup
                          current data/ to data.backup-{ts}/, then replace

Restore semantics: FULL REPLACE (no merge). SQLite connections are opened
per-request, so swapping the files is safe without a restart; in-memory rule
caches are reloaded at the end.
"""

from __future__ import annotations

import io
import json
import logging
import re
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pyzipper
from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile

from api.deps import get_current_user, get_settings
from api.models import BackupExportRequest, BackupRestoreResponse

logger = logging.getLogger(__name__)
router = APIRouter()

MANIFEST_NAME = "manifest.json"
BACKUP_VERSION = 1
_ROOT_DBS = ("auth.db", "shared.db")
_USER_DB_RE = re.compile(r"^[\w-]+\.db$")


# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------

def _iter_db_files(settings) -> list[Path]:
    """Return the DB files that make up a backup (existing ones only)."""
    files = [p for name in _ROOT_DBS if (p := settings.data_dir / name).exists()]
    users_dir = settings.users_data_dir
    if users_dir.is_dir():
        files.extend(sorted(users_dir.glob("*.db")))
    return files


def _snapshot_dbs(db_files: list[Path], settings, dest_dir: Path) -> list[str]:
    """
    Copy each DB into dest_dir (preserving relative paths) via VACUUM INTO,
    so the backup never reads a file mid-write. Returns relative paths.
    """
    rel_paths: list[str] = []
    for src in db_files:
        rel = src.relative_to(settings.data_dir)
        dest = dest_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(src) as conn:
            conn.execute(f"VACUUM INTO '{dest}'")
        rel_paths.append(rel.as_posix())
    return rel_paths


def _create_backup(settings, password: str) -> bytes:
    """Build the encrypted backup zip in memory. Returns the zip bytes."""
    with tempfile.TemporaryDirectory() as tmp:
        db_files = _iter_db_files(settings)
        rel_paths = _snapshot_dbs(db_files, settings, Path(tmp))
        manifest = {
            "app": "forecast-money",
            "version": BACKUP_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "files": rel_paths,
        }
        buf = io.BytesIO()
        with pyzipper.AESZipFile(
            buf, "w",
            compression=pyzipper.ZIP_DEFLATED,
            encryption=pyzipper.WZ_AES,
        ) as zf:
            zf.setpassword(password.encode("utf-8"))
            zf.writestr(MANIFEST_NAME, json.dumps(manifest, indent=2))
            for rel in rel_paths:
                zf.write(Path(tmp) / rel, arcname=rel)
        return buf.getvalue()


# ---------------------------------------------------------------------------
# Restore helpers
# ---------------------------------------------------------------------------

def _validate_member(name: str) -> bool:
    """Allow only the manifest + expected DB paths; rejects zip-slip and junk."""
    if name == MANIFEST_NAME:
        return True
    if name in _ROOT_DBS:
        return True
    if name.startswith("users/") and _USER_DB_RE.match(name.removeprefix("users/")):
        return True
    return False


def _integrity_check(db_path: Path) -> bool:
    try:
        with sqlite3.connect(db_path) as conn:
            return conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    except sqlite3.Error:
        return False


def _reload_rule_caches() -> None:
    """Refresh in-memory rule caches so no restart is needed after restore."""
    try:
        from categorizer.description_cleaner import reload_rules as reload_clean
        from categorizer.rule_categorizer import reload_rules as reload_cat
        reload_clean()
        reload_cat()
    except Exception:
        logger.warning("Rule cache reload after restore failed", exc_info=True)


def _restore_backup(settings, zip_bytes: bytes, password: str) -> BackupRestoreResponse:
    try:
        zf = pyzipper.AESZipFile(io.BytesIO(zip_bytes))
        zf.setpassword(password.encode("utf-8"))
        # Reading the manifest verifies the password (raises on mismatch)
        manifest = json.loads(zf.read(MANIFEST_NAME))
    except RuntimeError:
        raise HTTPException(status_code=400, detail="Wrong password or corrupt backup file.")
    except (json.JSONDecodeError, KeyError):
        raise HTTPException(status_code=422, detail="Not a valid Forecast Money backup.")

    if manifest.get("version") != BACKUP_VERSION:
        raise HTTPException(status_code=422, detail=f"Unsupported backup version: {manifest.get('version')}")

    names = zf.namelist()
    if any(not _validate_member(n) for n in names):
        raise HTTPException(status_code=422, detail="Backup contains unexpected files — refusing to restore.")

    db_names = [n for n in names if n != MANIFEST_NAME]
    if not db_names:
        raise HTTPException(status_code=422, detail="Backup contains no databases.")

    data_dir = settings.data_dir
    with tempfile.TemporaryDirectory() as tmp:
        zf.extractall(tmp)
        for rel in db_names:
            if not _integrity_check(Path(tmp) / rel):
                raise HTTPException(status_code=422, detail=f"Corrupt database inside backup: {rel}")

        previous_backup: str | None = None
        if data_dir.exists():
            previous_backup = f"{data_dir.name}.backup-{datetime.now():%Y%m%d-%H%M%S}"
            shutil.move(str(data_dir), str(data_dir.parent / previous_backup))

        for rel in db_names:
            dest = data_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(Path(tmp) / rel), str(dest))

    _reload_rule_caches()
    logger.info("Backup restored: %s (previous data → %s)", db_names, previous_backup)
    return BackupRestoreResponse(restored=sorted(db_names), previous_backup=previous_backup)


# ---------------------------------------------------------------------------
# POST /backup/export
# ---------------------------------------------------------------------------

@router.post("/backup/export", summary="Download encrypted full-data backup")
def export_backup(
    body: BackupExportRequest,
    settings=Depends(get_settings),
    _user=Depends(get_current_user),
):
    zip_bytes = _create_backup(settings, body.password)
    filename = f"forecast-money-backup-{datetime.now():%Y-%m-%d}.zip"
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# POST /backup/restore
# ---------------------------------------------------------------------------

@router.post("/backup/restore", response_model=BackupRestoreResponse, summary="Restore an encrypted backup (full replace)")
async def restore_backup(
    file: UploadFile = File(...),
    password: str = Form(...),
    settings=Depends(get_settings),
    _user=Depends(get_current_user),
):
    return _restore_backup(settings, await file.read(), password)
