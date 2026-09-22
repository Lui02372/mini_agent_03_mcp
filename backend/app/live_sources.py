"""Official place references and timestamped Open-Meteo model weather.

Only short factual place metadata is curated; no copied articles or invented prices.
Weather is modelled current conditions, not a station observation or trip forecast.
"""
from datetime import datetime, timezone
import httpx
from .multi_models import TripFacts

CATALOG = {
    '부산': (35.1796, 129.0756, [
        dict(name='해운대해수욕장', admission=0, outdoor=True,
             source_url='https://www.visitbusan.net/index.do?contentsSid=22&lang_cd=ko&uc_seq=373',
             note='기본 방문 무료. 장비 대여·주차 등 별도. 부산관광공사 안내 확인 2026-09-22.'),
        dict(name='동백공원', admission=0, outdoor=True,
             source_url='https://www.visitbusan.net/index.do?lang_cd=ko&menuCd=DOM_000000202002001000&uc_seq=284',
             note='공원 이용 무료. 부산관광공사 안내 확인 2026-09-22.')]),
    '서울': (37.5665, 126.9780, [
        dict(name='국립중앙박물관', admission=0, outdoor=False,
             source_url='https://www.museum.go.kr/site/main/edu/view/38/266082',
             note='상설전시 무료; 특별전시 별도. 공식 안내 확인 2026-09-22.')]),
    '제주': (33.4996, 126.5312, [
        dict(name='협재해수욕장', admission=None, outdoor=True,
             source_url='https://data.visitkorea.or.kr/resource/127490',
             note='한국관광공사 관광정보 확인 2026-09-22. 이용료 미확인; 예산 합계에 포함하지 않음.'),
        dict(name='국립제주박물관', admission=None, outdoor=False,
             source_url='https://jeju.museum.go.kr/html/kr/sub02/sub02_0201.html',
             note='국립제주박물관 상설전시 안내 확인 2026-09-22. 현재 요금은 방문 전 확인.')]),
}


def weather_label(code):
    if code == 0: return '맑음'
    if code in (1, 2, 3): return '구름 있음 / 흐림'
    if code in (45, 48): return '안개'
    if code in (51, 53, 55, 56, 57): return '이슬비'
    if code in (61, 63, 65, 66, 67, 80, 81, 82): return '비 / 소나기'
    if code in (71, 73, 75, 77, 85, 86): return '눈'
    if code in (95, 96, 99): return '뇌우'
    return 'WMO 날씨 코드 ' + str(code)


async def collect_facts(city):
    lat, lon, places = CATALOG[city]
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get('https://api.open-meteo.com/v1/forecast', params={
            'latitude': lat, 'longitude': lon, 'current': 'temperature_2m,weather_code',
            'timezone': 'Asia/Seoul'})
        response.raise_for_status()
        current = response.json()['current']
    fetched = datetime.now(timezone.utc).isoformat()
    # Reject stale/future model timestamps instead of calling stale data current.
    observed = datetime.fromisoformat(current['time'] + '+09:00')
    age = (datetime.now(timezone.utc) - observed).total_seconds()
    if age < -1800 or age > 10800:
        raise ValueError('weather timestamp out of range')
    return TripFacts(city=city, is_mock=False,
        weather=weather_label(current['weather_code']) + ' (Open-Meteo 현재 모델 추정)',
        temperature_c=current['temperature_2m'], places=places,
        hotel_per_night=80000, food_per_day=30000, transport_per_day=15000,
        as_of=current['time'] + '+09:00', fetched_at=fetched,
        sources=[{'title': 'Open-Meteo · 현재 모델 날씨 · CC BY 4.0',
                  'url': str(response.url), 'retrieved_at': fetched},
                 *[{'title': p['name'] + ' 공식 안내', 'url': p['source_url'],
                    'retrieved_at': '2026-09-22'} for p in places]])


def is_fresh(facts):
    if facts.is_mock or not facts.sources or not facts.fetched_at:
        return False
    try:
        now = datetime.now(timezone.utc)
        return (0 <= (now - datetime.fromisoformat(facts.fetched_at)).total_seconds() < 1800
                and -1800 <= (now - datetime.fromisoformat(facts.as_of)).total_seconds() <= 10800)
    except (ValueError, TypeError):
        return False
