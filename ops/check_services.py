"""Health checks including a persisted real run in production; no secret logging."""
import argparse
import os
import urllib.request
import json
import time


def check_app():
    for path in ("/health", "/api/mcp/status", "/api/mcp/tools", "/api/mcp/baggage-policy"):
        with urllib.request.urlopen("http://backend:8000" + path, timeout=30) as response:
            data = json.load(response)
        if path == "/api/mcp/status":
            assert data["status"] == "connected" and data["tool_count"] >= 3
        print("PASS", path)
    real = os.getenv('REQUIRE_REAL_DATA', 'false').lower() == 'true'
    payload = {"data_mode": "auto" if real else "mock", "allow_model_mock": False,
               "providers": {a: "ollama" if real else "mock" for a in
               ("weather_agent", "place_agent", "budget_agent", "validation_agent")}}
    request = urllib.request.Request("http://backend:8000/api/multi/runs",
              data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=10) as response:
        run = json.load(response)
    deadline = time.monotonic() + (650 if real else 30)
    while run["status"] == "running" and time.monotonic() < deadline:
        time.sleep(0.3)
        with urllib.request.urlopen("http://backend:8000/api/multi/runs/" + run["run_id"], timeout=10) as response:
            run = json.load(response)
    assert run["status"] == "completed", run["status"]
    assert len(run["agents"]) == 4
    assert all(a["provider_used"] == ("ollama" if real else "mock") and not a['error'] for a in run["agents"].values())
    assert run["validation"]["mock_data"] is (not real)
    if real:
        assert run['storage'] == {'postgres': 'saved', 'redis': 'saved'}, run['storage']
    assert "mcp" not in run["evidence"]["checks"], "MCP evidence tool was unavailable"
    print("PASS four-agent orchestration through MCP:", "real Ollama + source data + persisted history" if real else "explicit CI fixtures")



def check_data():
    import psycopg
    import redis
    from redis.retry import Retry
    from redis.backoff import NoBackoff
    failed = False
    if os.getenv('REQUIRE_REAL_DATA', 'false').lower() == 'true':
        try:
            with psycopg.connect(os.environ['FACTS_DATABASE_URL'], connect_timeout=3) as conn:
                assert conn.execute('SELECT 1').fetchone() == (1,)
            with redis.Redis.from_url(os.environ['FACTS_REDIS_URL'], socket_connect_timeout=3,
                                      socket_timeout=3, retry=Retry(NoBackoff(), 0)) as client:
                assert client.ping()
            print('PASS dedicated facts PostgreSQL / Redis')
            return
        except Exception as error:
            print('FAIL dedicated data:', type(error).__name__)
            raise SystemExit(1)
    try:
        with psycopg.connect(host=os.environ["POSTGRES_HOST"], port=int(os.getenv("POSTGRES_PORT", "5432")), dbname=os.environ["POSTGRES_DB"], user=os.environ["POSTGRES_USER"], password=os.environ["POSTGRES_PASSWORD"], sslmode=os.getenv("POSTGRES_SSLMODE", "prefer"), connect_timeout=5) as connection:
            assert connection.execute("SELECT 1").fetchone() == (1,)
        print("PASS PostgreSQL authentication / SELECT 1")
    except Exception as error:
        print("FAIL PostgreSQL:", type(error).__name__)
        failed = True
    try:
        with redis.Redis(host=os.environ["REDIS_HOST"], port=int(os.getenv("REDIS_PORT", "6379")), password=os.getenv("REDIS_PASSWORD") or None, db=int(os.getenv("REDIS_DB", "0")), ssl=os.getenv("REDIS_TLS", "false").lower() == "true", socket_connect_timeout=5, socket_timeout=5, retry=Retry(NoBackoff(), 0)) as client:
            assert client.ping()
        print("PASS Redis authentication / PING")
    except Exception as error:
        print("FAIL Redis:", type(error).__name__)
        failed = True
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", action="store_true")
    args = parser.parse_args()
    check_data() if args.data else check_app()
