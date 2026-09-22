import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch
from backend.app.live_sources import is_fresh
from backend.app.multi_data import mock_evidence, load_evidence
from backend.app.multi_models import TripRequest
from backend.app.multi_orchestration import cost_breakdown, fetch_evidence

class LiveDataTests(unittest.IsolatedAsyncioTestCase):
    def test_mock_and_stale_records_are_not_live(self):
        facts = mock_evidence('부산', 'test').facts
        self.assertFalse(is_fresh(facts))
        facts.is_mock = False
        facts.sources = [{'title': 'test', 'url': 'https://example.com'}]
        facts.fetched_at = datetime.now(timezone.utc).isoformat()
        facts.as_of = datetime.now(timezone.utc).isoformat()
        self.assertTrue(is_fresh(facts))
        facts.as_of = (datetime.now(timezone.utc) - timedelta(hours=4)).isoformat()
        self.assertFalse(is_fresh(facts))

    async def test_production_data_failure_does_not_become_mock(self):
        with patch.dict('os.environ', {'REQUIRE_REAL_DATA': 'true'}), patch('backend.app.multi_data.load_live_evidence', AsyncMock(side_effect=ConnectionError)):
            with self.assertRaises(ConnectionError):
                await load_evidence('부산')
        with patch.dict('os.environ', {'REQUIRE_REAL_DATA': 'true'}), patch('backend.app.multi_orchestration.open_session', AsyncMock(side_effect=ConnectionError)):
            with self.assertRaises(RuntimeError):
                await fetch_evidence(TripRequest())

    def test_plan_costs_and_unknown_admission_are_explicit(self):
        facts = mock_evidence('부산', 'test').facts
        facts.places[0].admission = None
        req = TripRequest(hotel_per_night=100000, food_per_day=20000, transport_per_day=10000)
        budget = cost_breakdown(req, facts)
        self.assertEqual(budget['total'], 163000)
        self.assertIn(facts.places[0].name, budget['unpriced_places'])
        self.assertFalse(req.allow_model_mock)
