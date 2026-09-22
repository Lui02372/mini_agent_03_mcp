"""Refresh/validate dedicated factual records; run inside the MCP container."""
import asyncio
from backend.app.multi_data import load_live_evidence

async def main():
    for city in ('서울', '부산', '제주'):
        evidence = await load_live_evidence(city)
        assert not evidence.facts.is_mock
        print(city, evidence.source, evidence.facts.as_of, len(evidence.facts.sources), 'sources')

if __name__ == '__main__':
    asyncio.run(main())
