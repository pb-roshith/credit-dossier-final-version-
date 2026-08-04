"""Background API for manufacturing local MCP credit data."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import require_admin


router = APIRouter(
    prefix="/api/manufacture",
    tags=["manufacture"],
    dependencies=[Depends(require_admin)],
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
MCP_DIR = REPOSITORY_ROOT / "mcp"
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="manufacture")
_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.Lock()


class ManufactureRequest(BaseModel):
    company_name: str = Field(min_length=2, max_length=256)
    industry: str = Field(min_length=2, max_length=256)
    geography: str = Field(min_length=2, max_length=256)


class ManufactureJob(BaseModel):
    job_id: str
    status: str
    percent: int
    stage: str
    result: dict[str, Any] | None = None
    error: str | None = None


def _set_job(job_id: str, **updates: Any) -> None:
    with _jobs_lock:
        _jobs[job_id].update(updates)


def _run_manufacturing(job_id: str, request: ManufactureRequest) -> None:
    _set_job(
        job_id,
        status="running",
        percent=10,
        stage="Generating PDFs, uploading to Mistral, and seeding PostgreSQL",
    )
    command = [
        sys.executable,
        "manufacture.py",
        "--company-name",
        request.company_name,
        "--industry",
        request.industry,
        "--geography",
        request.geography,
        "--json",
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=MCP_DIR,
            capture_output=True,
            text=True,
            timeout=30 * 60,
            check=False,
        )
        if completed.returncode != 0:
            error = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(error or "Manufacturing process failed.")
        output_lines = [
            line.strip() for line in completed.stdout.splitlines() if line.strip()
        ]
        if not output_lines:
            raise RuntimeError("Manufacturing process returned no result.")
        result = json.loads(output_lines[-1])
        from app.services.mcp_service import MCPClientService
        MCPClientService.invalidate_cache(request.company_name)
        _set_job(
            job_id,
            status="completed",
            percent=100,
            stage="Manufacturing completed",
            result=result,
        )
    except Exception as exc:
        _set_job(
            job_id,
            status="failed",
            percent=100,
            stage="Manufacturing failed",
            error=str(exc),
        )


@router.post("", response_model=ManufactureJob, status_code=202)
def start_manufacturing(request: ManufactureRequest) -> ManufactureJob:
    """Start one background manufacturing job."""
    if not (MCP_DIR / "manufacture.py").exists():
        raise HTTPException(status_code=500, detail="Local MCP service is missing.")
    job_id = "mfg_" + uuid.uuid4().hex[:12]
    job = {
        "job_id": job_id,
        "status": "queued",
        "percent": 0,
        "stage": "Queued for manufacturing",
        "result": None,
        "error": None,
    }
    with _jobs_lock:
        _jobs[job_id] = job
    _executor.submit(_run_manufacturing, job_id, request)
    return ManufactureJob(**job)


@router.get("/{job_id}", response_model=ManufactureJob)
def get_manufacturing_job(job_id: str) -> ManufactureJob:
    """Return current progress and the final manufacturing result."""
    with _jobs_lock:
        job = _jobs.get(job_id)
        snapshot = dict(job) if job else None
    if not snapshot:
        raise HTTPException(status_code=404, detail="Manufacturing job not found.")
    return ManufactureJob(**snapshot)
