"""ARQ worker.

Queues are separated from day one (docs/01-architecture.md §11): a backlog of 400 CV parses
must not starve a live interview session. Run one worker process per queue.

    arq app.workers.settings.WorkerSettings              # default: parse
    QUEUE_NAME=generate arq app.workers.settings.WorkerSettings
"""

from __future__ import annotations

import os

from arq.connections import RedisSettings

from app.core.config import settings
from app.core.logging import configure_logging
from app.workers.tasks import embed_profile, parse_job, parse_resume, rank_job, tailor_cv

QUEUE_PARSE = "hb:parse"
QUEUE_GENERATE = "hb:generate"
QUEUE_INTERVIEW = "hb:interview"


async def startup(ctx: dict[str, object]) -> None:
    configure_logging(settings.log_level)


async def shutdown(ctx: dict[str, object]) -> None:
    """In-flight jobs finish before exit; ARQ waits on SIGTERM by default."""


class WorkerSettings:
    functions = [parse_resume, parse_job, tailor_cv, rank_job, embed_profile]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    queue_name = os.getenv("QUEUE_NAME", QUEUE_PARSE)
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 10
    job_timeout = 600
    keep_result = 3600
    max_tries = 3
