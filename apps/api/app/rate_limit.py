"""Rate limiter instance shared across routers."""

from slowapi import Limiter
from slowapi.util import get_remote_address

from .settings import settings

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[settings.rate_limit_default],
    storage_uri=settings.redis_url,
    storage_options={"socket_connect_timeout": 0.25, "socket_timeout": 0.25},
    in_memory_fallback_enabled=True,
    swallow_errors=True,
)
