# Four-role travel orchestration

## Flow

Weather and Place run concurrently. The orchestrator joins their results,
then runs Budget, then Validation. Each role independently selects OpenAI,
Gemini, Ollama or deterministic mock from the UI. The provider adapters follow
07_multi-agent-service-ops/shared/travel_llm.py: OpenAI Responses structured
output, Gemini generate_content structured JSON, Ollama /api/chat JSON schema.
The reference's contracts, role separation and join/trace pattern are adapted;
its independent services and deployment files are not copied wholesale.

The budget is computed by Python (one traveller, all listed attractions once,
no long-distance transport). LLM text cannot change the authoritative total.
Validation flags failed roles, over-budget results and sample/mock evidence.
Mock results never qualify for an unqualified passed verdict.

## Two independent data servers

- DATABASE_URL / REDIS_URL and POSTGRES_* / REDIS_*: existing shared reference
  data at 54.180.29.87:5433 and :6379.
- LOG_DATABASE_URL / LOG_REDIS_URL: dedicated history storage at
  54.180.117.136:5437 and :6381. Credentials are runtime secrets only.
- The data server is a separate Compose project, not deployed by the app workflow.
  Its source is in TodayAssignment/01_simple-multi-llm-compose33/yaml/multiagent-data.

The travel MCP tool reads the shared Redis facts cache, then the optional shared
mini_agent_mcp.travel_facts table. Missing table, empty/invalid records and
connection failures visibly fall back to labelled educational fixtures. No
schema is created on the shared data server. A reference table can be provisioned
by its owner with ops/travel_facts.sql; the app does not execute that migration.
The dedicated server's optional sample table is not the app's shared data source.

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
without simulated answers. Keys/models use OPENAI_*, GEMINI_* and OLLAMA_* envs.
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
EC2 deploy repeats these checks. Never commit runtime env files or API keys.
Runtime env changes belong in GitHub production/RUNTIME_ENV. Main push deploys
the frontend, backend and MCP image together. Public HTTPS is not configured.
