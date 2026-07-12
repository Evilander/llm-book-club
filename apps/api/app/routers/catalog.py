"""Status and asynchronous refresh controls for persistent local-media catalogs."""

import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import LocalMediaCatalog, get_db
from ..rate_limit import limiter
from ..services.catalog_index import catalog_status, ensure_catalog, run_catalog_scan
from ..services.media_library import (
    SUPPORTED_AUDIOBOOK_EXTENSIONS,
    SUPPORTED_READER_EXTENSIONS,
)
from ..settings import settings
from ..worker import enqueue_catalog_scan


router = APIRouter(prefix="/library/catalog", tags=["library"])


class CatalogStatusResponse(BaseModel):
    id: str
    kind: str
    configured: bool = True
    root_path: str
    status: str
    generation: int
    item_count: int
    scan_duration_ms: int
    job_id: str | None = None
    error: str | None = None
    indexed_at: str | None = None
    scan_started_at: str | None = None
    scan_completed_at: str | None = None


class CatalogStatusListResponse(BaseModel):
    index_enabled: bool
    catalogs: list[CatalogStatusResponse]


class CatalogScanRequest(BaseModel):
    kind: str = "all"


class CatalogScanResponse(BaseModel):
    catalogs: list[CatalogStatusResponse]


def _catalog_definitions() -> list[tuple[str, str, set[str]]]:
    definitions: list[tuple[str, str, set[str]]] = []
    if settings.books_dir:
        definitions.append(("books", settings.books_dir, SUPPORTED_READER_EXTENSIONS))
    audio_root = settings.audiobooks_dir or settings.books_dir
    if audio_root:
        definitions.append(
            ("audiobooks", audio_root, SUPPORTED_AUDIOBOOK_EXTENSIONS)
        )
    return definitions


def _configured_catalogs(db: Session) -> list[LocalMediaCatalog]:
    catalogs: list[LocalMediaCatalog] = []
    for kind, root_dir, extensions in _catalog_definitions():
        root = Path(root_dir).resolve()
        if not root.exists() or not root.is_dir():
            continue
        catalogs.append(
            ensure_catalog(
                db,
                root_dir=str(root),
                kind=kind,
                extensions=extensions,
            )
        )
    db.commit()
    return catalogs


def _response(catalog: LocalMediaCatalog) -> CatalogStatusResponse:
    return CatalogStatusResponse.model_validate(catalog_status(catalog))


@router.get("/status", response_model=CatalogStatusListResponse)
@limiter.limit("120/minute")
def get_catalog_status(request: Request, db: Session = Depends(get_db)):
    return CatalogStatusListResponse(
        index_enabled=settings.media_catalog_index_enabled,
        catalogs=[_response(catalog) for catalog in _configured_catalogs(db)],
    )


@router.post("/scans", response_model=CatalogScanResponse, status_code=202)
@limiter.limit("6/minute")
def start_catalog_scan(
    request: Request,
    background_tasks: BackgroundTasks,
    payload: CatalogScanRequest = Body(default_factory=CatalogScanRequest),
    db: Session = Depends(get_db),
):
    if not settings.media_catalog_index_enabled:
        raise HTTPException(409, "Persistent media catalog indexing is disabled")
    if payload.kind not in {"all", "books", "audiobooks"}:
        raise HTTPException(400, "kind must be all, books, or audiobooks")

    selected = [
        catalog
        for catalog in _configured_catalogs(db)
        if payload.kind == "all" or catalog.kind == payload.kind
    ]
    if not selected:
        raise HTTPException(400, "No matching media directory is configured")

    queued: list[LocalMediaCatalog] = []
    for catalog in selected:
        claimed = (
            db.query(LocalMediaCatalog)
            .filter(
                LocalMediaCatalog.id == catalog.id,
                LocalMediaCatalog.status.notin_(["queueing", "queued", "scanning"]),
            )
            .update({LocalMediaCatalog.status: "queueing"}, synchronize_session=False)
        )
        db.commit()
        db.refresh(catalog)
        if not claimed:
            queued.append(catalog)
            continue
        job_id = f"media-catalog-{catalog.id}-{uuid.uuid4().hex}"
        catalog.status = "queued"
        catalog.scan_job_id = job_id
        catalog.scan_error = None
        db.commit()
        try:
            enqueue_catalog_scan(catalog.id, job_id)
        except Exception as exc:
            if settings.app_env in {"dev", "development", "test", "local"}:
                background_tasks.add_task(run_catalog_scan, catalog.id)
                db.refresh(catalog)
                queued.append(catalog)
                continue
            catalog.status = "failed"
            catalog.scan_job_id = None
            catalog.scan_error = "Catalog worker queue is unavailable"
            db.commit()
            raise HTTPException(
                503,
                "Catalog worker queue is unavailable; ensure Redis and the worker are running",
            ) from exc
        db.refresh(catalog)
        queued.append(catalog)

    return CatalogScanResponse(catalogs=[_response(catalog) for catalog in queued])


@router.get("/scans/{job_id}", response_model=CatalogStatusResponse)
@limiter.limit("120/minute")
def get_catalog_scan(job_id: str, request: Request, db: Session = Depends(get_db)):
    catalog = (
        db.query(LocalMediaCatalog)
        .filter(LocalMediaCatalog.scan_job_id == job_id)
        .first()
    )
    if catalog is None:
        raise HTTPException(404, "Catalog scan not found")
    return _response(catalog)
