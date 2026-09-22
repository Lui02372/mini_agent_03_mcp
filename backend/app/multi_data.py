"""Dedicated source-backed production facts; legacy demo reads remain optional."""
import asyncio
import json
import os
import psycopg
from psycopg.types.json import Jsonb
from .live_sources import collect_facts, is_fresh
from redis.asyncio import Redis
from redis.backoff import NoBackoff
from redis.retry import Retry
from .multi_models import Evidence, TripFacts


def mock_evidence(city: str, reason: str, checks=None) -> Evidence:
    names = {'서울': ['경복궁', '서울숲', '국립중앙박물관'],
             '부산': ['해운대', '감천문화마을', '부산시립미술관'],
             '제주': ['성산일출봉', '협재해변', '제주민속자연사박물관']}[city]
    return Evidence(source='mock', reason=reason, checks=checks or {}, facts=TripFacts(
        city=city, is_mock=True, weather='맑음 (교육용 가상 날씨)', temperature_c=24,
        places=[{'name': n, 'admission': price, 'outdoor': outdoor}
                for n, price, outdoor in zip(names, [5000, 0, 3000], [True, True, False])],
        hotel_per_night=80000, food_per_day=30000, transport_per_day=15000,
        as_of='교육용 샘플 — 현재 날씨·실제 요금 아님'))


def redis_client():
    options = dict(decode_responses=True, socket_connect_timeout=2,
                   socket_timeout=2, retry=Retry(NoBackoff(), 0))
    if os.getenv('FACTS_REDIS_URL'):
        return Redis.from_url(os.environ['FACTS_REDIS_URL'], **options)
    if os.getenv('REDIS_URL'):
        return Redis.from_url(os.environ['REDIS_URL'], **options)
    return Redis(host=os.getenv('REDIS_HOST', '127.0.0.1'),
                 port=int(os.getenv('REDIS_PORT', '6379')),
                 db=int(os.getenv('REDIS_DB', '0')),
                 password=os.getenv('REDIS_PASSWORD') or None,
                 ssl=os.getenv('REDIS_TLS', 'false').lower() == 'true', **options)


async def connect_postgres():
    params = dict(connect_timeout=2, options='-c statement_timeout=2000')
    if os.getenv('FACTS_DATABASE_URL'):
        connection = await psycopg.AsyncConnection.connect(os.environ['FACTS_DATABASE_URL'], **params)
    elif os.getenv('DATABASE_URL'):
        connection = await psycopg.AsyncConnection.connect(os.environ['DATABASE_URL'], **params)
    else:
        connection = await psycopg.AsyncConnection.connect(
            host=os.getenv('POSTGRES_HOST', '127.0.0.1'),
            port=int(os.getenv('POSTGRES_PORT', '5433')),
            dbname=os.getenv('POSTGRES_DB', 'agent_db'),
            user=os.getenv('POSTGRES_USER', 'agent_user'),
            password=os.getenv('POSTGRES_PASSWORD', ''),
            sslmode=os.getenv('POSTGRES_SSLMODE', 'prefer'), **params)
    return connection


async def read_postgres(city: str):
    async with await connect_postgres() as connection:
        await connection.execute('SET TRANSACTION READ ONLY')
        cursor = await connection.execute(
            'SELECT payload FROM mini_agent_mcp.travel_facts WHERE city = %s', (city,))
        row = await cursor.fetchone()
        return row[0] if row else None


async def load_evidence(city: str, mode: str = 'auto') -> Evidence:
    if mode == 'mock':
        return mock_evidence(city, '사용자가 모의 데이터 모드를 선택했습니다.')
    if os.getenv('REQUIRE_REAL_DATA', 'false').lower() == 'true':
        return await load_live_evidence(city)
    checks = {}
    key = 'mini-agent-mcp:v2:facts:' + city
    try:
        async with asyncio.timeout(3), redis_client() as client:
            raw = await client.get(key)
        if raw:
            facts = TripFacts.model_validate_json(raw)
            if facts.city != city:
                raise ValueError('city mismatch')
            return Evidence(facts=facts, source='redis', reason='PostgreSQL 참고 데이터의 캐시', checks={'redis': 'cache_hit'})
        checks['redis'] = 'cache_miss'
    except Exception as error:
        checks['redis'] = type(error).__name__
    try:
        async with asyncio.timeout(4):
            raw = await read_postgres(city)
        if raw is None:
            checks['postgres'] = 'empty'
        else:
            facts = TripFacts.model_validate(raw)
            if facts.city != city:
                raise ValueError('city mismatch')
            checks['postgres'] = 'row_found'
            try:
                async with asyncio.timeout(3), redis_client() as client:
                    await client.set(key, facts.model_dump_json(), ex=300)
            except Exception as error:
                checks['redis_cache_write'] = type(error).__name__
            return Evidence(facts=facts, source='postgres', reason='DB에 저장된 교육용 샘플' if facts.is_mock else '등록된 여행 참고 데이터', checks=checks)
    except Exception as error:
        checks['postgres'] = type(error).__name__
    return mock_evidence(city, 'DB 데이터가 없거나 사용할 수 없어 교육용 샘플로 대체했습니다.', checks)


async def load_live_evidence(city):
    """Dedicated store only; production never silently returns fixtures."""
    if not os.getenv('FACTS_DATABASE_URL'):
        raise RuntimeError('Dedicated facts database is not configured')
    key = 'mini-agent-mcp:v3:facts:' + city
    try:
        async with asyncio.timeout(3), redis_client() as client:
            raw = await client.get(key)
        if raw:
            facts = TripFacts.model_validate_json(raw)
            if facts.city == city and is_fresh(facts):
                return Evidence(facts=facts, source='redis', reason='전용 DB의 출처 확인 자료 · Redis 캐시')
    except Exception:
        pass
    async with asyncio.timeout(5):
        raw = await read_postgres(city)
    facts = TripFacts.model_validate(raw) if raw else None
    if not facts or facts.city != city or not is_fresh(facts):
        facts = await collect_facts(city)
        async with asyncio.timeout(5), await connect_postgres() as conn:
            await conn.execute("INSERT INTO mini_agent_mcp.travel_facts(city,payload) VALUES (%s,%s) "
                               "ON CONFLICT(city) DO UPDATE SET payload=EXCLUDED.payload, updated_at=now()",
                               (city, Jsonb(facts.model_dump())))
    try:
        async with asyncio.timeout(3), redis_client() as client:
            await client.set(key, facts.model_dump_json(), ex=300)
    except Exception:
        pass
    return Evidence(facts=facts, source='postgres', reason='전용 PostgreSQL · 공식 관광정보 + Open-Meteo 모델 날씨')
