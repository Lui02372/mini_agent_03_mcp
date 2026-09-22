FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.deploy.txt ./
RUN pip install -r requirements.deploy.txt && useradd --create-home --uid 10001 app
COPY --chown=app:app backend/ ./backend/
COPY --chown=app:app frontend/ ./frontend/
COPY --chown=app:app mcp_server/ ./mcp_server/
COPY --chown=app:app ops/check_services.py ./ops/check_services.py
COPY --chown=app:app .streamlit/ ./.streamlit/
COPY --chown=app:app tests/ ./tests/
USER app
CMD ["python", "-m", "mcp_server.travel_server"]
