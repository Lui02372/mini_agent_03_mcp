-- Optional, additive schema for operator-supplied reference facts.
-- No real-time weather source is implied. No sample rows are seeded as real data.
CREATE SCHEMA IF NOT EXISTS mini_agent_mcp;
CREATE TABLE IF NOT EXISTS mini_agent_mcp.travel_facts (
    city text PRIMARY KEY,
    payload jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);
-- payload follows backend/app/multi_models.py:TripFacts.
-- Until valid rows are supplied, the MCP tool visibly falls back to mock data.
