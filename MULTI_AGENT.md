# Four-role travel orchestration

## Flow

Weather and Place run concurrently. The orchestrator joins their results,
then runs Budget, then Validation. Each role independently selects EC2 Ollama/Qwen
or Gemma from the UI. Both use Ollama /api/chat JSON schema output.
The reference's contracts, role separation and join/trace pattern are adapted;
its independent services and deployment files are not copied wholesale.

The budget is computed by Python (per traveller with shared lodging, all listed attractions once,
no long-distance transport). LLM text cannot change the authoritative total.
Validation flags failed roles, over-budget results and sample/mock evidence.
Mock results never qualify for an unqualified passed verdict.

## Production real-data mode (2026-09-22)

Each role can select Ollama/Qwen (qwen3:1.7b) or Gemma (gemma3:1b), both hosted
by EC2 Ollama. Defaults use Qwen for Weather/Place and Gemma for Budget/Validation.
Production rejects cloud providers, mock data/providers and mock-on-error requests.
Cloud adapters remain for compatibility, but no cloud credentials are forwarded by Compose.
REQUIRE_REAL_DATA=true never returns fixtures when actual data cannot be read.
CPU inference takes roughly 2–3 minutes for a four-role run on this 4 GB EC2;
MAX_CONCURRENT_RUNS=1 limits contention. Weather/Place requests are issued
concurrently, while the single Ollama worker queues inference to bound memory.

FACTS_DATABASE_URL / FACTS_REDIS_URL select the dedicated data server, distinct
from the unchanged legacy shared DATABASE_URL / REDIS_URL. The dedicated
travel_facts table stores official place metadata, source URLs, current
Open-Meteo model weather, retrieved_at and as_of timestamps. Weather is refreshed
on demand after 30 minutes. A model weather timestamp older than 3 hours is
rejected; this is not an observed weather station measurement or a trip forecast.
Place facts are a curated catalog in backend/app/live_sources.py, checked on
2026-09-22. Place URLs and fees need editorial rechecking when updated.

Hotel/food/transport numbers are user-editable planning allowances, not scraped
market quotes. Lodging includes property type, price per room/night, rooms and
travellers. Per-person lodging is ceil(nights * room_price * rooms / travellers).
Breakfast/lunch/dinner/cafe each carry a meal style and unit price, charged once
per travel day per person. Included breakfast/omitted meals cost zero. The form
updates the daily meal subtotal as inputs change. Backend line_items store every
formula and category; Budget/Validation agents receive those exact calculations.
Unknown admission fees are excluded and flagged for review.

Sources: [Open-Meteo](https://open-meteo.com/en/docs) (CC BY 4.0),
[Visit Busan](https://www.visitbusan.net/index.do?contentsSid=22&lang_cd=ko&uc_seq=373),
[Visit Korea](https://data.visitkorea.or.kr/resource/127490), and official museums.
The complete per-place source links are stored in the DB and shown in the UI.

On the app EC2, Ollama is a systemd service bound only to Docker's host interface
172.17.0.1:11434. No public 11434 rule is required. ops/setup_ollama.sh and
ops/ollama.service reproduce installation; installed host also has 1 GB swap.
The data EC2 remains PostgreSQL / Redis / pgAdmin only. App images do not contain
model weights. CI uses explicit fixtures; production deployment checks a real
MCP → facts → four Ollama roles → PostgreSQL/Redis saved run and rolls back on failure.

Refresh/validate facts inside the application deployment:
```bash
sudo docker compose --env-file env/.env.docker -f env/compose.yml exec -T travel-mcp-server python -m ops.refresh_facts
```

## Two independent data servers

- DATABASE_URL / REDIS_URL and POSTGRES_* / REDIS_*: existing shared reference
  data at 54.180.29.87:5433 and :6379.
- LOG_DATABASE_URL / LOG_REDIS_URL: dedicated history storage at
  54.180.117.136:5437 and :6381. Credentials are runtime secrets only.
- The data server is a separate Compose project, not deployed by the app workflow.
  Its source is in TodayAssignment/01_simple-multi-llm-compose33/yaml/multiagent-data.

In legacy/demo mode only, the travel MCP tool reads the shared Redis facts cache, then the optional shared
mini_agent_mcp.travel_facts table. Missing table, empty/invalid records and
connection failures visibly fall back to labelled educational fixtures. No
schema is created on the shared data server. A reference table can be provisioned
by its owner with ops/travel_facts.sql; the app does not execute that migration.
Production uses dedicated FACTS URLs and replaces seed samples with source-backed records.

Dedicated PostgreSQL stores runs, agent_results and trace_events. Redis caches
initial/final snapshots for one hour. Active progress is held by the backend
and polled by Streamlit. Failed persistence is shown in the UI; the run remains
usable in memory. Completed persisted runs can be loaded after redeployment.
Interrupted runs do not resume: recovered running snapshots are marked failed.
This is a bounded single-process orchestrator, not a durable job queue.

## API

- GET /api/multi/config — roles, models, configured flags (no keys)
- POST /api/multi/runs — returns 202 + run_id
- GET /api/multi/runs/{run_id} — current or persisted result
- GET /api/multi/history — latest 20 PostgreSQL runs

Request example:

```json
{"city":"부산","days":2,"budget":300000,"data_mode":"mock",
 "providers":{"weather_agent":"mock","place_agent":"mock",
 "budget_agent":"mock","validation_agent":"mock"},"allow_model_mock":true}
```

Data mock and model mock are separate decisions. Real providers are still called
when data is mocked. Disable allow_model_mock to surface failed model calls
without simulated answers. Production models use OLLAMA_MODEL and GEMMA_MODEL.
Inside Docker, localhost is the container itself. host.docker.internal points to
the EC2 host; Ollama must actually run there or use a reachable Ollama URL.
No Ollama model is installed automatically.

## Checks and deployment

```bash
python -m unittest discover -s tests -v
# Against an existing frontend; requires Playwright and Chromium:
python tests/ui_smoke.py http://127.0.0.1:18501
```

CI builds the shared app image, runs unit tests, starts Compose and checks
legacy MCP routes plus the complete four-role mock run through the MCP tool.
EC2 deployment additionally verifies real data, real Ollama inference and successful history storage. Never commit runtime env files or API keys.
Runtime env changes belong in GitHub production/RUNTIME_ENV. Main push deploys
the frontend, backend and MCP image together. Public HTTPS is not configured.

## Public connection panel

GET /api/multi/data-status performs bounded, read-only checks of the configured
FACTS and LOG PostgreSQL/Redis connections. PostgreSQL verifies its table is readable;
Redis verifies authenticated PING. Results are cached 15 seconds with one shared lock.
The response contains only logical roles, connected/unavailable/not_configured and
check timestamp. No addresses, credentials, connection strings or exception details
are returned. A successful probe does not prove write permission: the current run's
actual persist_run result separately confirms PostgreSQL and Redis saves.
The UI explains Redis cache -> PostgreSQL -> source refresh, and history persistence.
