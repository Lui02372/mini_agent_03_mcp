"""Best-effort persistence in the dedicated data server; memory remains usable."""
import asyncio
from copy import deepcopy
import json
import os
from psycopg.types.json import Jsonb
import psycopg
from redis.asyncio import Redis
from redis.retry import Retry
from redis.backoff import NoBackoff


async def connect_postgres():
    return await psycopg.AsyncConnection.connect(os.environ['LOG_DATABASE_URL'], connect_timeout=2,
                                                  options='-c statement_timeout=2000')


def redis_client():
    return Redis.from_url(os.environ['LOG_REDIS_URL'], decode_responses=True,
                          socket_connect_timeout=2, socket_timeout=2, retry=Retry(NoBackoff(), 0))


async def persist_run(run):
    result = {'postgres': 'not_configured', 'redis': 'not_configured'}
    if os.getenv('LOG_DATABASE_URL'):
        try:
            async with asyncio.timeout(5), await connect_postgres() as conn:
                await conn.execute('''INSERT INTO mini_agent_mcp.runs(run_id,status,city,version,payload)
                    VALUES (%s,%s,%s,%s,%s) ON CONFLICT(run_id) DO UPDATE SET
                    status=EXCLUDED.status, version=EXCLUDED.version, payload=EXCLUDED.payload, updated_at=now()
                    WHERE mini_agent_mcp.runs.version <= EXCLUDED.version''',
                    (run['run_id'], run['status'], run['request']['city'], len(run['trace']), Jsonb(run)))
                for agent, state in run['agents'].items():
                    await conn.execute('''INSERT INTO mini_agent_mcp.agent_results
                        (run_id,agent_id,status,provider_requested,provider_used,latency_ms,payload)
                        VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(run_id,agent_id) DO UPDATE SET
                        status=EXCLUDED.status,provider_used=EXCLUDED.provider_used,
                        latency_ms=EXCLUDED.latency_ms,payload=EXCLUDED.payload''',
                        (run['run_id'], agent, state['status'], state['provider_requested'],
                         state['provider_used'], state['latency_ms'], Jsonb(state)))
                for event in run['trace']:
                    await conn.execute('''INSERT INTO mini_agent_mcp.trace_events
                        (run_id,sequence,actor,action,status,occurred_at) VALUES (%s,%s,%s,%s,%s,%s)
                        ON CONFLICT(run_id,sequence) DO NOTHING''',
                        (run['run_id'], event['sequence'], event['actor'], event['action'], event['status'], event['at']))
            result['postgres'] = 'saved'
        except Exception as error:
            result['postgres'] = type(error).__name__
    # Cache contains persistence result, not just an optimistic success label.
    run = deepcopy(run)
    run['storage'] = {**result, 'redis': 'saved'}
    if os.getenv('LOG_REDIS_URL'):
        try:
            async with asyncio.timeout(3), redis_client() as client:
                await client.set('mini-agent-mcp:v2:run:' + run['run_id'], json.dumps(run, ensure_ascii=False), ex=3600)
            result['redis'] = 'saved'
        except Exception as error:
            result['redis'] = type(error).__name__
    return result


async def restore_run(run_id):
    if len(run_id) != 32 or any(c not in '0123456789abcdef' for c in run_id):
        return None
    if os.getenv('LOG_REDIS_URL'):
        try:
            async with asyncio.timeout(3), redis_client() as client:
                raw = await client.get('mini-agent-mcp:v2:run:' + run_id)
            if raw:
                return json.loads(raw)
        except Exception:
            pass
    if os.getenv('LOG_DATABASE_URL'):
        try:
            async with asyncio.timeout(4), await connect_postgres() as conn:
                cursor = await conn.execute('SELECT payload FROM mini_agent_mcp.runs WHERE run_id=%s', (run_id,))
                row = await cursor.fetchone()
                return row[0] if row else None
        except Exception:
            pass
    return None


async def recent_runs():
    if not (os.getenv('LOG_DATABASE_URL')):
        return {'runs': [], 'storage': 'not_configured'}
    try:
        async with asyncio.timeout(4), await connect_postgres() as conn:
            cursor = await conn.execute('SELECT run_id,city,status,updated_at FROM mini_agent_mcp.runs ORDER BY updated_at DESC LIMIT 20')
            rows = await cursor.fetchall()
        return {'runs': [{'run_id': r[0], 'city': r[1], 'status': r[2], 'updated_at': r[3].isoformat()} for r in rows], 'storage': 'postgres'}
    except Exception as error:
        return {'runs': [], 'storage': type(error).__name__}
