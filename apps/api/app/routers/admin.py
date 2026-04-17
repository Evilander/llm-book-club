"""Admin endpoints for cost tracking and usage analytics."""
import hmac
from datetime import datetime, timedelta
from collections import defaultdict

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db, Message, DiscussionSession
from ..settings import settings


def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    """Guard admin endpoints behind a shared-secret token.

    Behaviour matrix:
      - ADMIN_TOKEN unset AND app_env == "dev"  -> allow (local dev convenience)
      - ADMIN_TOKEN unset AND app_env != "dev"  -> deny (misconfig must not leak)
      - ADMIN_TOKEN set                         -> require header match
    """
    configured = settings.admin_token
    if not configured:
        # Permissive in local / test environments only. Any other app_env
        # (staging, prod, unknown) must set ADMIN_TOKEN explicitly.
        if settings.app_env.lower() in {"dev", "development", "test", "local"}:
            return
        raise HTTPException(
            503,
            "Admin endpoints are disabled: ADMIN_TOKEN is not configured.",
        )
    if not x_admin_token or not hmac.compare_digest(x_admin_token, configured):
        raise HTTPException(401, "Invalid or missing admin token")


router = APIRouter(tags=["admin"], dependencies=[Depends(require_admin)])

# Rough per-token pricing (Claude Sonnet tier)
INPUT_COST_PER_TOKEN = 3.0 / 1_000_000   # $3 per million input tokens
OUTPUT_COST_PER_TOKEN = 15.0 / 1_000_000  # $15 per million output tokens


@router.get("/admin/costs")
def get_costs(
    book_id: str | None = Query(None, description="Filter by book"),
    days: int = Query(30, ge=1, le=365, description="Lookback window in days"),
    db: Session = Depends(get_db),
):
    """
    Aggregate token usage and estimated cost from message metadata.

    Returns total tokens, cost estimate, and breakdowns per session and per agent role.
    """
    cutoff = datetime.utcnow() - timedelta(days=days)

    query = (
        db.query(Message, DiscussionSession.book_id)
        .join(DiscussionSession, Message.session_id == DiscussionSession.id)
        .filter(Message.created_at >= cutoff)
    )

    if book_id:
        query = query.filter(DiscussionSession.book_id == book_id)

    rows = query.all()

    total_input = 0
    total_output = 0
    per_session: dict[str, dict] = defaultdict(lambda: {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "cost_estimate": 0.0,
        "message_count": 0,
    })
    per_agent: dict[str, dict] = defaultdict(lambda: {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "cost_estimate": 0.0,
        "message_count": 0,
    })

    for message, _book_id in rows:
        meta = message.metadata_json or {}
        usage = meta.get("token_usage", {})
        inp = usage.get("input_tokens", 0) or 0
        out = usage.get("output_tokens", 0) or 0

        if inp == 0 and out == 0:
            continue

        total_input += inp
        total_output += out

        msg_cost = inp * INPUT_COST_PER_TOKEN + out * OUTPUT_COST_PER_TOKEN
        role = message.role.value

        sid = message.session_id
        per_session[sid]["input_tokens"] += inp
        per_session[sid]["output_tokens"] += out
        per_session[sid]["total_tokens"] += inp + out
        per_session[sid]["cost_estimate"] += msg_cost
        per_session[sid]["message_count"] += 1

        per_agent[role]["input_tokens"] += inp
        per_agent[role]["output_tokens"] += out
        per_agent[role]["total_tokens"] += inp + out
        per_agent[role]["cost_estimate"] += msg_cost
        per_agent[role]["message_count"] += 1

    total_tokens = total_input + total_output
    total_cost = total_input * INPUT_COST_PER_TOKEN + total_output * OUTPUT_COST_PER_TOKEN

    # Round cost estimates for readability
    for breakdown in list(per_session.values()) + list(per_agent.values()):
        breakdown["cost_estimate"] = round(breakdown["cost_estimate"], 6)

    return {
        "days": days,
        "book_id": book_id,
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "total_tokens": total_tokens,
        "total_cost_estimate": round(total_cost, 6),
        "per_session": dict(per_session),
        "per_agent": dict(per_agent),
    }
