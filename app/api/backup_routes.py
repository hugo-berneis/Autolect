"""Download a full-library backup archive. Restore is CLI-only (safer):
`python -m app.backup restore <archive.tar.gz>`.
"""
from __future__ import annotations

import os
import tempfile
import time

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from ..auth import get_current_user
from ..backup import create_backup

router = APIRouter(prefix="/api", tags=["backup"])


@router.get("/backup")
def download_backup(user: str = Depends(get_current_user)) -> FileResponse:
    fd, path = tempfile.mkstemp(suffix=".tar.gz")
    os.close(fd)
    create_backup(path)
    name = f"autolect-backup-{time.strftime('%Y%m%d-%H%M%S')}.tar.gz"
    return FileResponse(
        path,
        media_type="application/gzip",
        filename=name,
        background=BackgroundTask(os.remove, path),
    )
