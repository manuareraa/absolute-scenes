# Absolute Scenes live crew: POST /ask streams NDJSON AskEvents on :8080, health at /healthz.
# Build from the repo root:  docker build -f crew/Dockerfile -t chalktalk-ask .
# Without CHALKTALK_ASK_BACKEND=azure it runs the fakes, so a bare container spends nothing.
# Nothing here holds secrets; the deploy sets the endpoint, keys and managed identity.
FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.11.30 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
# uv needs every workspace member's metadata to read the lockfile; only these are built.
COPY pyproject.toml uv.lock ./
COPY postmatch/pyproject.toml postmatch/
COPY vision/pyproject.toml vision/
COPY contracts/schemas contracts/schemas
COPY contracts/python contracts/python
COPY core core
COPY sim sim
COPY mcp mcp
COPY crew crew
RUN uv sync --frozen --no-dev --no-editable --package chalktalk-crew \
    --extra foundry --extra azure

FROM python:3.12-slim
# The Speech SDK loads OpenSSL and ALSA at import, even when synthesising to memory.
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates libssl3 \
    libasound2 && rm -rf /var/lib/apt/lists/*
RUN useradd --create-home --uid 10001 app
COPY --from=build /app/.venv /app/.venv
# The shipped shows were built on 5-minute halves; the ask must replay the same match.
ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1 PORT=8080 \
    CHALKTALK_SIM_HALF_MINUTES=5 CHALKTALK_ASK_PRELOAD=sim-7 CHALKTALK_MAX_MATCHES=2
USER app
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=60s CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/healthz')"
CMD ["python", "-m", "chalktalk_crew.ask", "serve"]
