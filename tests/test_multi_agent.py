import asyncio
import os
import unittest
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException
import httpx
from backend.app.multi_models import AGENTS, AgentAnswer, TripRequest
from backend.app.multi_data import load_evidence, mock_evidence
from backend.app.multi_orchestration import Orchestrator, cost_breakdown
from backend.app import multi_providers
from backend.app.multi_storage import persist_run, restore_run


class RedisStub:
    def __init__(self, value=None, error=None):
        self.value, self.error, self.written = value, error, []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, key):
        if self.error:
            raise self.error
        return self.value

    async def set(self, *args, **kwargs):
        self.written.append((args, kwargs))


class OrchestrationTests(unittest.IsolatedAsyncioTestCase):
    async def run_trip(self, request, provider=None):
        engine = Orchestrator()
        evidence = mock_evidence(request.city, 'test fixture')
        with patch('backend.app.multi_orchestration.fetch_evidence', AsyncMock(return_value=evidence)):
            if provider:
                with patch('backend.app.multi_orchestration.structured', provider):
                    record = engine.start(request)
                    await engine.tasks[record['run_id']]
            else:
                record = engine.start(request)
                await engine.tasks[record['run_id']]
        return engine.get(record['run_id'])

    async def test_four_roles_join_and_validation(self):
        run = await self.run_trip(TripRequest(providers={a: 'mock' for a in AGENTS}, data_mode='mock'))
        self.assertEqual(run['status'], 'completed')
        self.assertEqual(set(run['agents']), set(AGENTS))
        self.assertTrue(all(s['status'] == 'mock' for s in run['agents'].values()))
        self.assertEqual(run['budget']['total'], 178000)
        self.assertTrue(run['validation']['mock_data'])
        self.assertEqual(run['validation']['verdict'], 'needs_review')
        ends = {t['actor']: t['sequence'] for t in run['trace'] if t['action'] == 'result'}
        starts = {t['actor']: t['sequence'] for t in run['trace'] if t['action'] == 'execute'}
        self.assertGreater(starts['budget_agent'], max(ends['weather_agent'], ends['place_agent']))
        self.assertGreater(starts['validation_agent'], ends['budget_agent'])

    async def test_real_workers_run_in_parallel_and_budget_gets_context(self):
        barrier = asyncio.Event()
        starters = set()

        async def provider(name, prompt):
            if '역할: weather_agent' in prompt or '역할: place_agent' in prompt:
                role = 'weather' if '역할: weather_agent' in prompt else 'place'
                starters.add(role)
                if len(starters) == 2:
                    barrier.set()
                await asyncio.wait_for(barrier.wait(), 1)
            if '역할: budget_agent' in prompt:
                self.assertIn('weather_agent', prompt)
                self.assertIn('place_agent', prompt)
            return AgentAnswer(summary='검증된 구조화 응답', details=[], cautions=[])

        run = await self.run_trip(TripRequest(providers={a: 'openai' for a in AGENTS}), provider)
        self.assertEqual(starters, {'weather', 'place'})
        self.assertTrue(all(s['provider_used'] == 'openai' for s in run['agents'].values()))

    async def test_provider_failure_falls_back_visibly(self):
        run = await self.run_trip(TripRequest(providers={a: 'openai' for a in AGENTS}, allow_model_mock=True), AsyncMock(side_effect=TimeoutError('secret must not leak')))
        self.assertEqual(run['status'], 'completed')
        self.assertTrue(all(s['error'] and s['provider_used'] == 'mock' for s in run['agents'].values()))
        self.assertNotIn('secret must not leak', str(run))

    async def test_strict_failure_and_budget_excess_cannot_pass_validation(self):
        run = await self.run_trip(TripRequest(providers={a: 'openai' for a in AGENTS}, allow_model_mock=False, budget=10000), AsyncMock(side_effect=ValueError()))
        self.assertEqual(run['status'], 'partial_failure')
        self.assertEqual(len(run['validation']['failed_agents']), 4)
        self.assertFalse(run['validation']['budget_within_limit'])
        self.assertTrue(all(s['provider_used'] is None for s in run['agents'].values()))

    async def test_admission_bounds_and_capacity(self):
        with self.assertRaises(ValueError):
            TripRequest(days=0)
        with self.assertRaises(ValueError):
            TripRequest(providers={'unknown_agent': 'mock'})
        engine = Orchestrator()
        gate = asyncio.Event()
        with patch.object(engine, 'execute', lambda *args: gate.wait()):
            for _ in range(4):
                engine.start(TripRequest())
            with self.assertRaises(HTTPException) as raised:
                engine.start(TripRequest())
            self.assertEqual(raised.exception.status_code, 429)
            gate.set()
            await asyncio.gather(*engine.tasks.values())

    async def test_mock_data_never_calls_databases(self):
        with patch('backend.app.multi_data.redis_client') as redis, patch('backend.app.multi_data.read_postgres') as pg:
            result = await load_evidence('부산', 'mock')
        self.assertEqual(result.source, 'mock')
        redis.assert_not_called()
        pg.assert_not_called()

    async def test_missing_or_failed_databases_return_mock(self):
        for pg_result, pg_error in [(None, None), (None, OSError('secret'))]:
            redis = RedisStub(error=ConnectionError('secret'))
            with patch('backend.app.multi_data.redis_client', return_value=redis), patch('backend.app.multi_data.read_postgres', AsyncMock(return_value=pg_result, side_effect=pg_error)):
                result = await load_evidence('제주')
            self.assertEqual(result.source, 'mock')
            self.assertEqual(result.facts.city, '제주')
            self.assertNotIn('secret', str(result))
            self.assertFalse(redis.written)

    async def test_database_row_and_cache_contract(self):
        facts = mock_evidence('서울', 'fixture').facts
        redis = RedisStub(value='not-valid-json')
        with patch('backend.app.multi_data.redis_client', return_value=redis), patch('backend.app.multi_data.read_postgres', AsyncMock(return_value=facts.model_dump())):
            result = await load_evidence('서울')
        self.assertEqual(result.source, 'postgres')
        self.assertEqual(len(redis.written), 1)
        redis = RedisStub(value=facts.model_dump_json())
        with patch('backend.app.multi_data.redis_client', return_value=redis), patch('backend.app.multi_data.read_postgres') as pg:
            result = await load_evidence('서울')
        self.assertEqual(result.source, 'redis')
        pg.assert_not_called()

    async def test_wrong_city_cache_not_used(self):
        redis = RedisStub(value=mock_evidence('서울', 'fixture').facts.model_dump_json())
        with patch('backend.app.multi_data.redis_client', return_value=redis), patch('backend.app.multi_data.read_postgres', AsyncMock(return_value=None)):
            result = await load_evidence('부산')
        self.assertEqual(result.source, 'mock')
        self.assertEqual(result.facts.city, '부산')

    async def test_ollama_payload_and_structured_output(self):
        real_client = httpx.AsyncClient

        def respond(request):
            import json
            body = json.loads(request.content)
            self.assertFalse(body['stream'])
            self.assertIn('summary', body['format']['properties'])
            return httpx.Response(200, json={'message': {'content': '{"summary":"ok","details":[],"cautions":[]}'}})

        with patch.object(multi_providers.httpx, 'AsyncClient', side_effect=lambda **kw: real_client(transport=httpx.MockTransport(respond), **kw)):
            answer = await multi_providers.structured('ollama', 'test')
        self.assertEqual(answer.summary, 'ok')

    async def test_history_never_writes_to_shared_urls(self):
        with patch.dict(os.environ, {'DATABASE_URL': 'postgresql://shared', 'REDIS_URL': 'redis://shared'}, clear=True):
            with patch('backend.app.multi_storage.connect_postgres') as pg, patch('backend.app.multi_storage.redis_client') as redis:
                result = await persist_run({})
        self.assertEqual(result, {'postgres': 'not_configured', 'redis': 'not_configured'})
        pg.assert_not_called()
        redis.assert_not_called()

    async def test_log_db_failure_still_caches_run_without_leaking_error(self):
        run = await self.run_trip(TripRequest(providers={a: 'mock' for a in AGENTS}))
        redis = RedisStub()
        with patch.dict(os.environ, {'LOG_DATABASE_URL': 'postgresql://log', 'LOG_REDIS_URL': 'redis://log'}, clear=True):
            with patch('backend.app.multi_storage.connect_postgres', AsyncMock(side_effect=OSError('private password'))), patch('backend.app.multi_storage.redis_client', return_value=redis):
                result = await persist_run(run)
        self.assertEqual(result, {'postgres': 'OSError', 'redis': 'saved'})
        self.assertEqual(len(redis.written), 1)
        self.assertNotIn('private password', str(redis.written))

    async def test_invalid_history_id_cannot_query_storage(self):
        with patch('backend.app.multi_storage.connect_postgres') as pg:
            self.assertIsNone(await restore_run("' OR 1=1"))
        pg.assert_not_called()


if __name__ == '__main__':
    unittest.main()
