import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from backend.app import data_status as status
from backend.app.multi_models import TripRequest
from backend.app.multi_orchestration import Orchestrator, config


class ConnectionStatusTests(unittest.IsolatedAsyncioTestCase):
    async def test_driver_error_does_not_expose_connection_details(self):
        secret = 'postgresql://private_user:private_password@10.20.30.40/private_db'
        with patch.dict('os.environ', {'FACTS_DATABASE_URL': secret}), patch.object(
            status.psycopg.AsyncConnection, 'connect', AsyncMock(side_effect=RuntimeError(secret))
        ):
            result = await status.probe('FACTS_DATABASE_URL', 'SELECT 1')
        self.assertEqual(result, 'unavailable')
        self.assertNotIn(secret, result)

    async def test_concurrent_refresh_is_cached_and_response_is_allowlisted(self):
        with patch.object(status, '_cached', None), patch.object(status, '_expires', 0), patch.object(
            status, '_lock', asyncio.Lock()
        ), patch.object(status, 'probe', AsyncMock(return_value='connected')) as probe:
            first, second = await asyncio.gather(status.data_status(), status.data_status())
            self.assertEqual(probe.await_count, 4)
            self.assertEqual(set(first), {'checked_at', 'services', 'cache_seconds'})
            self.assertEqual(first, second)
            first['services']['facts_postgres'] = 'changed'
            self.assertEqual((await status.data_status())['services']['facts_postgres'], 'connected')
            self.assertNotIn('URL', json.dumps(second))

    async def test_production_rejects_cloud_and_demo_models(self):
        with patch.dict('os.environ', {'ENABLE_DEMO': 'false'}):
            self.assertEqual((await config())['providers'], ['ollama', 'gemma'])
            for provider in ('openai', 'gemini', 'mock'):
                with self.assertRaises(HTTPException) as result:
                    Orchestrator().start(TripRequest(providers={'weather_agent': provider}))
                self.assertEqual(result.exception.status_code, 422)
