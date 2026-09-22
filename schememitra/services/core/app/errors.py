"""RFC 7807 problem+json errors. Citizens never see codes or traces — clients map
`user_message_key` to a friendly localized sentence."""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.logging import get_logger

log = get_logger("errors")
PROBLEM = "application/problem+json"


class ProblemError(Exception):
    def __init__(
        self,
        status: int,
        title: str,
        user_message_key: str = "errors.generic",
        detail: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(title)
        self.status = status
        self.title = title
        self.user_message_key = user_message_key
        self.detail = detail
        self.extra = extra or {}


def not_found(what: str) -> ProblemError:
    return ProblemError(404, f"{what} not found", "errors.not_found")


def forbidden(detail: str = "Not allowed for this role") -> ProblemError:
    return ProblemError(403, "Forbidden", "errors.forbidden", detail)


def conflict(detail: str, key: str = "errors.conflict") -> ProblemError:
    return ProblemError(409, "Conflict", key, detail)


def _problem(status: int, title: str, key: str, request: Request, detail: str | None = None,
             extra: dict[str, Any] | None = None) -> JSONResponse:
    body: dict[str, Any] = {
        "type": f"https://schememitra.dev/problems/{key.replace('.', '-')}",
        "title": title,
        "status": status,
        "instance": request.url.path,
        "user_message_key": key,
    }
    if detail:
        body["detail"] = detail
    body.update(extra or {})
    return JSONResponse(body, status_code=status, media_type=PROBLEM)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ProblemError)
    async def _problem_error(request: Request, exc: ProblemError) -> JSONResponse:
        return _problem(exc.status, exc.title, exc.user_message_key, request, exc.detail, exc.extra)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
        return _problem(422, "Invalid request", "errors.validation", request, extra={"errors": errors})

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        key = {401: "errors.unauthorized", 403: "errors.forbidden", 404: "errors.not_found",
               429: "errors.rate_limited"}.get(exc.status_code, "errors.generic")
        return _problem(exc.status_code, str(exc.detail), key, request)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error on %s", request.url.path)
        return _problem(500, "Internal error", "errors.generic", request)
