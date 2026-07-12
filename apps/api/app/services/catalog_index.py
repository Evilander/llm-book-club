"""Persistent, generation-safe snapshots of configured local media roots."""

from __future__ import annotations

import hashlib
import logging
import os
import threading
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from ..db.models import LocalMediaCatalog, LocalMediaCatalogItem
from .media_library import get_media_catalog


_snapshot_lock = threading.RLock()
_snapshot_cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
_MAX_SNAPSHOT_CACHE_ENTRIES = 8
_MAX_SCAN_ERROR_LENGTH = 2000
logger = logging.getLogger(__name__)


def _normalized_root(root_dir: str) -> Path:
    return Path(root_dir).resolve()


def catalog_root_key(root_dir: str) -> str:
    normalized = os.path.normcase(str(_normalized_root(root_dir))).encode(
        "utf-8", errors="surrogatepass"
    )
    return hashlib.sha256(normalized).hexdigest()


def extension_signature(extensions: set[str]) -> str:
    return "|".join(sorted(extension.casefold() for extension in extensions))


def snapshot_content_signature(snapshot: dict[str, Any]) -> str:
    """Fingerprint the fields that determine a filesystem catalog record."""
    digest = hashlib.sha256()
    for entry in sorted(snapshot.get("items", []), key=lambda item: item["id"]):
        digest.update(str(entry["id"]).encode("utf-8", errors="surrogatepass"))
        digest.update(b"\0")
        digest.update(str(entry["size_bytes"]).encode("ascii"))
        digest.update(b"\0")
        digest.update(str(entry["modified_at"]).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _parse_indexed_at(value: str) -> datetime:
    return _utc_naive(datetime.fromisoformat(value))


def _public_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _cache_key(catalog: LocalMediaCatalog) -> str:
    return f"{catalog.id}:{catalog.active_generation}"


def _cache_snapshot(catalog: LocalMediaCatalog, snapshot: dict[str, Any]) -> None:
    key = _cache_key(catalog)
    with _snapshot_lock:
        stale = [cached_key for cached_key in _snapshot_cache if cached_key.startswith(f"{catalog.id}:")]
        for cached_key in stale:
            _snapshot_cache.pop(cached_key, None)
        _snapshot_cache[key] = snapshot
        _snapshot_cache.move_to_end(key)
        while len(_snapshot_cache) > _MAX_SNAPSHOT_CACHE_ENTRIES:
            _snapshot_cache.popitem(last=False)


def clear_catalog_index_cache() -> None:
    with _snapshot_lock:
        _snapshot_cache.clear()


def find_catalog(
    db: Session,
    *,
    root_dir: str,
    kind: str,
) -> LocalMediaCatalog | None:
    return (
        db.query(LocalMediaCatalog)
        .filter(
            LocalMediaCatalog.kind == kind,
            LocalMediaCatalog.root_key == catalog_root_key(root_dir),
        )
        .first()
    )


def ensure_catalog(
    db: Session,
    *,
    root_dir: str,
    kind: str,
    extensions: set[str],
) -> LocalMediaCatalog:
    catalog = find_catalog(db, root_dir=root_dir, kind=kind)
    if catalog:
        return catalog
    catalog = LocalMediaCatalog(
        kind=kind,
        root_key=catalog_root_key(root_dir),
        root_path=str(_normalized_root(root_dir)),
        extension_signature=extension_signature(extensions),
    )
    db.add(catalog)
    db.flush()
    return catalog


def catalog_status(catalog: LocalMediaCatalog) -> dict[str, Any]:
    return {
        "id": catalog.id,
        "kind": catalog.kind,
        "root_path": catalog.root_path,
        "status": catalog.status,
        "generation": catalog.active_generation,
        "item_count": catalog.item_count,
        "scan_duration_ms": catalog.scan_duration_ms,
        "job_id": catalog.scan_job_id,
        "error": catalog.scan_error,
        "indexed_at": _public_datetime(catalog.indexed_at),
        "scan_started_at": _public_datetime(catalog.scan_started_at),
        "scan_completed_at": _public_datetime(catalog.scan_completed_at),
    }


def _serialize_item(catalog: LocalMediaCatalog, item: LocalMediaCatalogItem) -> dict[str, Any]:
    path = Path(catalog.root_path) / Path(item.relative_path)
    return {
        "id": item.media_id,
        "path": str(path),
        "filename": item.filename,
        "extension": item.extension,
        "format_family": item.format_family,
        "reader_kind": item.reader_kind,
        "can_discuss": item.can_discuss,
        "size_bytes": item.size_bytes,
        "modified_at": item.modified_at,
        "title_guess": item.title_guess,
        "parent_folder": item.parent_folder,
    }


def load_catalog_snapshot(
    db: Session,
    *,
    root_dir: str,
    kind: str,
    extensions: set[str],
) -> dict[str, Any] | None:
    catalog = find_catalog(db, root_dir=root_dir, kind=kind)
    if (
        catalog is None
        or catalog.active_generation < 1
        or catalog.indexed_at is None
        or catalog.extension_signature != extension_signature(extensions)
    ):
        return None

    key = _cache_key(catalog)
    with _snapshot_lock:
        cached = _snapshot_cache.get(key)
        if cached is not None:
            _snapshot_cache.move_to_end(key)
            return cached

    items = (
        db.query(LocalMediaCatalogItem)
        .filter(
            LocalMediaCatalogItem.catalog_id == catalog.id,
            LocalMediaCatalogItem.is_available.is_(True),
        )
        .order_by(LocalMediaCatalogItem.filename)
        .all()
    )
    snapshot = {
        "version": 2,
        "root": catalog.root_path,
        "extensions": sorted(extensions),
        "indexed_at": _public_datetime(catalog.indexed_at),
        "scan_duration_ms": catalog.scan_duration_ms,
        "generation": catalog.active_generation,
        "source": "database",
        "items": [_serialize_item(catalog, item) for item in items],
    }
    _cache_snapshot(catalog, snapshot)
    return snapshot


def persist_catalog_snapshot(
    db: Session,
    *,
    root_dir: str,
    kind: str,
    extensions: set[str],
    snapshot: dict[str, Any],
) -> LocalMediaCatalog:
    """Atomically promote a fully enumerated snapshot to the next generation."""
    catalog = ensure_catalog(
        db,
        root_dir=root_dir,
        kind=kind,
        extensions=extensions,
    )
    generation = catalog.active_generation + 1
    content_signature = snapshot_content_signature(snapshot)
    indexed_at = _parse_indexed_at(snapshot["indexed_at"])
    if (
        catalog.active_generation > 0
        and catalog.extension_signature == extension_signature(extensions)
        and catalog.content_signature == content_signature
    ):
        catalog.active_generation = generation
        catalog.item_count = len(snapshot.get("items", []))
        catalog.scan_duration_ms = int(snapshot.get("scan_duration_ms") or 0)
        catalog.indexed_at = indexed_at
        catalog.scan_completed_at = datetime.utcnow()
        catalog.scan_error = None
        catalog.status = "idle"
        db.commit()
        db.refresh(catalog)
        promoted = {
            **snapshot,
            "root": catalog.root_path,
            "generation": generation,
            "source": "database",
        }
        _cache_snapshot(catalog, promoted)
        return catalog

    existing = {
        item.media_id: item
        for item in db.query(LocalMediaCatalogItem)
        .filter(LocalMediaCatalogItem.catalog_id == catalog.id)
        .all()
    }
    seen: set[str] = set()
    root = _normalized_root(root_dir)
    now = datetime.utcnow()
    inserts: list[dict[str, Any]] = []
    updates: list[dict[str, Any]] = []

    # Advancing this marker in one statement avoids an UPDATE round trip per
    # unchanged file. Availability is promoted in the same transaction.
    db.query(LocalMediaCatalogItem).filter(
        LocalMediaCatalogItem.catalog_id == catalog.id
    ).update(
        {LocalMediaCatalogItem.seen_generation: generation},
        synchronize_session=False,
    )

    for entry in snapshot.get("items", []):
        media_id = str(entry["id"])
        seen.add(media_id)
        try:
            relative_path = Path(entry["path"]).resolve().relative_to(root).as_posix()
        except (OSError, RuntimeError, ValueError) as exc:
            raise ValueError("Catalog entry escaped its configured root") from exc

        values = {
            "relative_path": relative_path,
            "filename": entry["filename"],
            "extension": entry["extension"],
            "format_family": entry["format_family"],
            "reader_kind": entry.get("reader_kind"),
            "can_discuss": bool(entry.get("can_discuss")),
            "size_bytes": int(entry["size_bytes"]),
            "modified_at": entry["modified_at"],
            "title_guess": entry["title_guess"],
            "parent_folder": entry.get("parent_folder"),
            "seen_generation": generation,
            "is_available": True,
        }
        item = existing.get(media_id)
        if item is None:
            inserts.append(
                {
                    "id": str(uuid.uuid4()),
                    "catalog_id": catalog.id,
                    "media_id": media_id,
                    **values,
                    "created_at": now,
                    "updated_at": now,
                }
            )
            continue
        comparable = {key: value for key, value in values.items() if key != "seen_generation"}
        if any(getattr(item, key) != value for key, value in comparable.items()):
            updates.append({"id": item.id, **values, "updated_at": now})

    for media_id, item in existing.items():
        if media_id not in seen and item.is_available:
            updates.append(
                {
                    "id": item.id,
                    "seen_generation": generation,
                    "is_available": False,
                    "updated_at": now,
                }
            )

    if inserts:
        db.bulk_insert_mappings(LocalMediaCatalogItem, inserts)
    if updates:
        db.bulk_update_mappings(LocalMediaCatalogItem, updates)

    catalog.root_path = str(root)
    catalog.extension_signature = extension_signature(extensions)
    catalog.content_signature = content_signature
    catalog.active_generation = generation
    catalog.item_count = len(seen)
    catalog.scan_duration_ms = int(snapshot.get("scan_duration_ms") or 0)
    catalog.indexed_at = indexed_at
    catalog.scan_completed_at = datetime.utcnow()
    catalog.scan_error = None
    catalog.status = "idle"
    db.commit()
    db.refresh(catalog)

    promoted = {
        **snapshot,
        "root": catalog.root_path,
        "generation": generation,
        "source": "database",
    }
    _cache_snapshot(catalog, promoted)
    return catalog


def scan_and_index_catalog(
    db: Session,
    *,
    root_dir: str,
    kind: str,
    extensions: set[str],
    cache_file: str | Path | None = None,
    minimum_bytes: int = 1024,
) -> dict[str, Any]:
    catalog = ensure_catalog(
        db,
        root_dir=root_dir,
        kind=kind,
        extensions=extensions,
    )
    catalog.status = "scanning"
    catalog.scan_started_at = datetime.utcnow()
    catalog.scan_error = None
    db.commit()
    try:
        snapshot = get_media_catalog(
            root_dir,
            extensions=extensions,
            minimum_bytes=minimum_bytes,
            cache_file=cache_file,
            force_refresh=True,
        )
        persist_catalog_snapshot(
            db,
            root_dir=root_dir,
            kind=kind,
            extensions=extensions,
            snapshot=snapshot,
        )
        indexed = load_catalog_snapshot(
            db,
            root_dir=root_dir,
            kind=kind,
            extensions=extensions,
        )
        if indexed is None:
            raise RuntimeError("Catalog promotion did not produce a readable snapshot")
        return indexed
    except Exception as exc:
        db.rollback()
        failed = find_catalog(db, root_dir=root_dir, kind=kind)
        if failed is not None:
            failed.status = "failed"
            failed.scan_error = str(exc)[:_MAX_SCAN_ERROR_LENGTH]
            failed.scan_completed_at = datetime.utcnow()
            db.commit()
        raise


def get_or_seed_catalog(
    db: Session,
    *,
    root_dir: str,
    kind: str,
    extensions: set[str],
    index_enabled: bool,
    cache_file: str | Path | None = None,
    ttl_seconds: int = 24 * 60 * 60,
    minimum_bytes: int = 1024,
) -> dict[str, Any]:
    if index_enabled:
        indexed = load_catalog_snapshot(
            db,
            root_dir=root_dir,
            kind=kind,
            extensions=extensions,
        )
        if indexed is not None:
            return indexed

    snapshot = get_media_catalog(
        root_dir,
        extensions=extensions,
        minimum_bytes=minimum_bytes,
        cache_file=cache_file,
        ttl_seconds=ttl_seconds,
    )
    if index_enabled:
        try:
            persist_catalog_snapshot(
                db,
                root_dir=root_dir,
                kind=kind,
                extensions=extensions,
                snapshot=snapshot,
            )
            return load_catalog_snapshot(
                db,
                root_dir=root_dir,
                kind=kind,
                extensions=extensions,
            ) or snapshot
        except Exception:
            db.rollback()
            logger.exception(
                "Persistent %s catalog seed failed; serving the legacy snapshot",
                kind,
            )
    return snapshot


def run_catalog_scan(catalog_id: str) -> dict[str, Any]:
    """RQ entry point for refreshing a catalog outside request latency."""
    from ..db import SessionLocal
    from ..settings import settings
    from .media_library import CATALOG_VERSION

    db = SessionLocal()
    try:
        catalog = (
            db.query(LocalMediaCatalog)
            .filter(LocalMediaCatalog.id == catalog_id)
            .first()
        )
        if catalog is None:
            raise ValueError("Catalog no longer exists")
        extensions = {
            extension
            for extension in catalog.extension_signature.split("|")
            if extension
        }
        cache_file = (
            None
            if settings.app_env == "test"
            else Path(settings.storage_dir)
            / "catalog"
            / f"{catalog.kind}-v{CATALOG_VERSION}.json"
        )
        snapshot = scan_and_index_catalog(
            db,
            root_dir=catalog.root_path,
            kind=catalog.kind,
            extensions=extensions,
            cache_file=cache_file,
        )
        return {
            "catalog_id": catalog_id,
            "kind": catalog.kind,
            "generation": snapshot.get("generation"),
            "item_count": len(snapshot["items"]),
        }
    finally:
        db.close()
