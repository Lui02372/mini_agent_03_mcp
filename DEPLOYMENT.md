# EC2 deployment

Repository: https://github.com/Lui02372/mini_agent_03_mcp
Application: http://54.180.142.56/ (HTTP; TLS is not configured)

Open this project folder in VS Code. Commit and push to main to run the workflow
in `.github/workflows/deploy.yml`. The CI job builds and checks the image on a
GitHub-hosted runner. Deployment runs on the personal EC2 runner labeled
`mini-agent-ec2`, loads the tested image and runs `ops/deploy.sh`.

Runtime configuration is the `RUNTIME_ENV` secret in the GitHub `production`
environment. Never commit `.env`, `env/.env.docker`, API keys or PEM files.
Use `env/.env.docker.example` for the non-secret template.

The app EC2 exposes only port 80. Backend 8000 and travel MCP 8010 are internal.
The policy stdio MCP runs as a backend child process. Shared PostgreSQL and Redis
are external; this repository never deploys or changes those shared services.

Server releases: `/opt/mini-agent-mcp/releases/<release>`.
Current successful release: `/opt/mini-agent-mcp/current`.
Each release retains its runtime env; deployment failure attempts rollback.
This single-host deployment can have brief downtime.

External DB checks are read-only SELECT 1 and Redis PING. The current demo has no
storage feature. `REQUIRE_DATA_SERVICES=false` permits deployment with a warning
if the external database is unavailable; set true when storage becomes required.

## Local use

```bash
docker compose --env-file env/.env.docker -f env/compose.yml up -d --build --wait
```

For public access allow inbound TCP 80 on the app EC2 security group. SSH 22
should allow the administrator's IP only. The self-hosted runner connects
outbound to GitHub, so GitHub inbound SSH rules and PEM secrets are unnecessary.
The public repository's workflow runs on main push/manual dispatch only.
