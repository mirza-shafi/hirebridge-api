FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

# WeasyPrint renders the tailored CVs and needs pango/harfbuzz at runtime (ADR-0008).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libffi8 fonts-dejavu-core curl \
    && rm -rf /var/lib/apt/lists/*

# uv from PyPI rather than a ghcr.io image: the build already depends on PyPI, and one
# registry is one thing that can be blocked or rate-limited instead of two.
RUN pip install --no-cache-dir uv

# The virtualenv lives OUTSIDE the project directory on purpose: the compose stack
# bind-mounts the source over /srv for hot reload, which would shadow a .venv created here
# and leave the container with no interpreter packages at all.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /srv

COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev --no-install-project 2>/dev/null || uv sync --no-dev --no-install-project

COPY . .
ENV PATH="/opt/venv/bin:$PATH" PYTHONPATH=/srv
RUN chmod +x scripts/entrypoint.sh

# api:    docker run <img>
# worker: docker run -e RUN_MIGRATIONS=false <img> arq app.workers.settings.WorkerSettings
ENTRYPOINT ["./scripts/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
