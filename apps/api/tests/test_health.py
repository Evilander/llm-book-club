"""Dependency failures must be actionable without exposing connection details."""
import json
from unittest.mock import MagicMock, patch

import pytest

from app.routers.health import health


@pytest.mark.parametrize("db_down,redis_down", [(False, False), (True, False), (False, True)])
def test_health_status_and_private_error_details(db_down, redis_down):
    db = MagicMock()
    if db_down:
        db.execute.side_effect = RuntimeError("connection password=private-value")
    redis = MagicMock()
    redis.__enter__.return_value = redis
    if redis_down:
        redis.ping.side_effect = RuntimeError("redis://private-credential@private-host")
    with patch("redis.Redis.from_url", return_value=redis):
        response = health(db)
    data = json.loads(response.body)
    assert response.status_code == (503 if db_down or redis_down else 200)
    assert data["ok"] is (not db_down and not redis_down)
    assert data["checks"]["database"] == ("unavailable" if db_down else "ok")
    assert data["checks"]["redis"] == ("unavailable" if redis_down else "ok")
    assert "private" not in response.body.decode()
    redis.__exit__.assert_called_once()
