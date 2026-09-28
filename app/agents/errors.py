"""Agent exceptions, importable without pulling in the app's infrastructure."""

from __future__ import annotations

from app.schemas.enums import ValidatorStatus


class TransientProviderError(Exception):
    """Provider-side failure worth retrying (timeout, 5xx, rate limit)."""


class ValidationFailure(Exception):
    """Output was well-formed but broke a product rule. Carries the complaint for repair."""

    def __init__(self, complaint: str, *, status: str = ValidatorStatus.FAILED.value) -> None:
        super().__init__(complaint)
        self.complaint = complaint
        self.status = status


class AgentFailed(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
