from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from fastapi.responses import JSONResponse

from ..db.engine import get_db

router = APIRouter()


@router.get("/health")
def health(db: Session = Depends(get_db)):
    checks = {}

    # Database connectivity
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "unavailable"

    # Redis connectivity
    try:
        from redis import Redis
        from ..settings import settings
        with Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2) as r:
            r.ping()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "unavailable"

    all_ok = all(v == "ok" for v in checks.values())

    return JSONResponse(status_code=200 if all_ok else 503, content={
        "status": "healthy" if all_ok else "degraded",
        "ok": all_ok,
        "checks": checks,
    })
