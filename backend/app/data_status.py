"""Read-only connection checks with a deliberately small public response."""
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import os
import time

import psycopg
from redis.asyncio import Redis
from redis.backoff import NoBackoff
from redis.retry import Retry

_lock = asyncio.Lock()
_cached = None
_expires = 0.0
TARGETS = {
    'facts_postgres': ('FACTS_DATABASE_URL', 'SELECT 1 FROM mini_agent_mcp.travel_facts LIMIT 0'),
    'facts_redis': ('FACTS_REDIS_URL', None),
    'history_postgres': ('LOG_DATABASE_URL', 'SELECT 1 FROM mini_agent_mcp.runs LIMIT 0'),
    'history_redis': ('LOG_REDIS_URL', None),
}


async def probe(env_name, query):
    url = os.getenv(env_name)
    if not url:
        return 'not_configured'
    try:
        async with asyncio.timeout(4):
            if query:
                async with await psycopg.AsyncConnection.connect(
                    url, connect_timeout=2, options='-c statement_timeout=2000'
                ) as conn:
                    await conn.execute(query)
            else:
                async with Redis.from_url(
                    url, socket_connect_timeout=2, socket_timeout=2,
                    retry=Retry(NoBackoff(), 0)
                ) as client:
                    if not await client.ping():
                        return 'unavailable'
        return 'connected'
    except Exception:
        # Driver messages can contain hosts, users and credentials. Never serialize them.
        return 'unavailable'


async def data_status():
    global _cached, _expires
    async with _lock:
        if _cached is not None and time.monotonic() < _expires:
            return deepcopy(_cached)
        states = await asyncio.gather(*(probe(*target) for target in TARGETS.values()))
        _cached = {'checked_at': datetime.now(timezone.utc).isoformat(),
                   'services': dict(zip(TARGETS, states)), 'cache_seconds': 15}
        _expires = time.monotonic() + 15
        return deepcopy(_cached)
