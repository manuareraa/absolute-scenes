# Absolute Scenes Analyst MCP server (streamable HTTP on :8000, health at /healthz).
# Build from the repo root:  docker build -f mcp/Dockerfile -t chalktalk-mcp .
# Stream D deploys it to Azure Container Apps; nothing here holds secrets.
FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.11.30 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
# uv needs every workspace member's metadata to read the lockfile; only these are built.
COPY pyproject.toml uv.lock ./
COPY crew/pyproject.toml crew/
COPY postmatch/pyproject.toml postmatch/
COPY vision/pyproject.toml vision/
COPY contracts/schemas contracts/schemas
COPY contracts/python contracts/python
COPY core core
COPY sim sim
COPY mcp mcp
RUN uv sync --frozen --no-dev --no-editable --package chalktalk-mcp

FROM python:3.12-slim
RUN useradd --create-home --uid 10001 app
COPY --from=build /app/.venv /app/.venv
ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1 HOST=0.0.0.0 PORT=8000 \
    CHALKTALK_MAX_MATCHES=2
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/healthz')"
CMD ["python", "-m", "chalktalk_mcp", "--transport", "streamable-http"]
