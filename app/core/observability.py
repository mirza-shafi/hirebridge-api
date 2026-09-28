"""Error reporting. No-op unless SENTRY_DSN is set, so local and CI stay quiet."""

from __future__ import annotations

import logging

from app.core.config import settings
from app.core.logging import scrub

log = logging.getLogger(__name__)


def _before_send(event: dict[str, object], hint: dict[str, object]) -> dict[str, object]:
    """Last line of defence: CV text must never leave in an error payload."""
    if isinstance(message := event.get("message"), str):
        event["message"] = scrub(message)
    event.pop("request", None)  # bodies may carry CV content
    return event


def init_observability() -> None:
    if not settings.sentry_dsn:
        return
    try:
        import sentry_sdk
    except ImportError:
        log.warning("SENTRY_DSN is set but sentry-sdk is not installed; skipping.")
        return

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        traces_sample_rate=0.1 if settings.is_production else 1.0,
        send_default_pii=False,
        before_send=_before_send,
    )
    log.info("Sentry initialised for %s", settings.environment)
