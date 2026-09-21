"""Read-only checks; no connection strings or exception messages in logs."""
import argparse
import os
import urllib.request
import json


def check_app():
    for path in ("/health", "/api/mcp/status", "/api/mcp/tools", "/api/mcp/baggage-policy"):
        with urllib.request.urlopen("http://backend:8000" + path, timeout=30) as response:
            data = json.load(response)
        if path == "/api/mcp/status":
            assert data["status"] == "connected" and data["tool_count"] >= 3
        print("PASS", path)


def check_data():
    import psycopg
    import redis
    from redis.retry import Retry
    from redis.backoff import NoBackoff
    failed = False
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
