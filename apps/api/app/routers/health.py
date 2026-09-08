from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from ..db.engine import get_db

router = APIRouter()


@router.get("/health")
def health(db: Session = Depends(get_db)):
    checks = {}

    # Database connectivity
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e}"

    # Redis connectivity
    try:
        from redis import Redis
        from ..settings import settings
        r = Redis.from_url(settings.redis_url, socket_connect_timeout=2)
        r.ping()
        checks["redis"] = "ok"
        r.close()
    except Exception as e:
        checks["redis"] = f"error: {e}"

    all_ok = all(v == "ok" for v in checks.values())

    return {
        "status": "healthy" if all_ok else "degraded",
        "ok": all_ok,
        "checks": checks,
    }
