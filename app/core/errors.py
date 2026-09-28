"""RFC 9457 problem details. Every error response in the API has this shape."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import request_id_var

BASE = "https://hirebridge.dev/errors"


class AppError(Exception):
    """Base for expected, typed failures."""

    status_code = status.HTTP_400_BAD_REQUEST
    error_type = "bad-request"
    title = "Bad request"

    def __init__(self, detail: str, **extra: Any) -> None:
        super().__init__(detail)
        self.detail = detail
        self.extra = extra


class NotFound(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    error_type = "not-found"
    title = "Not found"


class Forbidden(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    error_type = "forbidden"
    title = "Forbidden"


class Conflict(AppError):
    status_code = status.HTTP_409_CONFLICT
    error_type = "conflict"
    title = "Conflict"


class Unprocessable(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_type = "validation-failed"
    title = "Validation failed"


class BudgetExceeded(AppError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    error_type = "budget-exceeded"
    title = "Budget exceeded"


def problem(
    *,
    status_code: int,
    error_type: str,
    title: str,
    detail: str,
    instance: str,
    **extra: Any,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": f"{BASE}/{error_type}",
        "title": title,
        "status": status_code,
        "detail": detail,
        "instance": instance,
        "request_id": request_id_var.get(),
    }
    body.update(extra)
    return JSONResponse(status_code=status_code, content=body, media_type="application/problem+json")


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        return problem(
            status_code=exc.status_code,
            error_type=exc.error_type,
            title=exc.title,
            detail=exc.detail,
            instance=request.url.path,
            **exc.extra,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {"field": ".".join(str(p) for p in e["loc"][1:]), "code": e["type"], "message": e["msg"]}
            for e in exc.errors()
        ]
        return problem(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_type="validation-failed",
            title="Validation failed",
            detail="The request body failed validation.",
            instance=request.url.path,
            errors=errors,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return problem(
            status_code=exc.status_code,
            error_type="http-error",
            title=str(exc.detail),
            detail=str(exc.detail),
            instance=request.url.path,
        )
