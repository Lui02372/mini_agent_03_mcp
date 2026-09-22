import unittest
from unittest.mock import patch
import httpx
from backend.app.multi_models import TripRequest
from backend.app.multi_data import mock_evidence
from backend.app.multi_orchestration import cost_breakdown
from backend.app import multi_providers

class DetailedBudgetTests(unittest.IsolatedAsyncioTestCase):
    def test_shared_room_and_meal_types_are_per_person(self):
        request=TripRequest(days=2,travelers=2,rooms=1,hotel_per_night=120000,meal_plan=[
            {'name':'아침','style':'간단식','price':8000},
            {'name':'점심','style':'국밥','price':12000},
            {'name':'저녁','style':'해산물','price':20000}])
        facts=mock_evidence('부산','test').facts
        budget=cost_breakdown(request,facts)
        self.assertEqual(budget['items']['숙박'],60000)
        self.assertEqual(budget['items']['식비·카페'],80000)
        self.assertEqual(budget['total'],178000) # includes fixture admissions 8000
        self.assertEqual(budget['group_lodging_total'],120000)
        self.assertEqual(next(x for x in budget['line_items'] if x['category']=='저녁')['detail'],'해산물')

    def test_no_lodging_and_included_breakfast(self):
        req=TripRequest(lodging_type='숙박 없음',meal_plan=[{'name':'아침','style':'숙박비에 포함','price':0}])
        self.assertEqual(cost_breakdown(req,mock_evidence('부산','test').facts)['items']['숙박'],0)
        with self.assertRaises(ValueError):
            TripRequest(meal_plan=[{'name':'아침','style':'식사','price':1000}]*2)

    def test_room_share_rounds_up_in_won(self):
        req=TripRequest(days=3,hotel_per_night=100001,travelers=3)
        self.assertEqual(cost_breakdown(req,mock_evidence('부산','test').facts)['items']['숙박'],66668)

    async def test_gemma_selects_distinct_model_without_qwen_thinking_flag(self):
        async def handler(request):
            import json
            body=json.loads(request.content)
            self.assertEqual(body['model'],'gemma3:1b')
            self.assertNotIn('think',body)
            return httpx.Response(200,json={'message':{'content':'{"summary":"ok","details":[],"cautions":[]}'}})
        original=httpx.AsyncClient
        with patch.object(multi_providers.httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(handler))), patch.dict('os.environ',{'GEMMA_MODEL':'gemma3:1b'}):
            result=await multi_providers.structured('gemma','test')
        self.assertEqual(result.summary,'ok')
