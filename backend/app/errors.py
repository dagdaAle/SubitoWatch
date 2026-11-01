"""Problem Details (RFC 9457) for every error, with a stable `code` clients can branch on."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ApiError(Exception):
    def __init__(self, status: int, code: str, detail: str):
        self.status, self.code, self.detail = status, code, detail


def problem(status: int, code: str, detail: str, **extra) -> JSONResponse:
    title = {400: 'Bad Request', 404: 'Not Found', 409: 'Conflict', 412: 'Precondition Failed',
             422: 'Unprocessable Content', 503: 'Service Unavailable'}.get(status, 'Error')
    body = {'type': 'about:blank', 'title': title, 'status': status, 'detail': detail, 'code': code, **extra}
    return JSONResponse(body, status_code=status, media_type='application/problem+json')


def install(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error(_: Request, exc: ApiError):
        return problem(exc.status, exc.code, exc.detail)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException):
        return problem(exc.status_code, 'not_found' if exc.status_code == 404 else 'http_error', str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        errors = [{'loc': list(e['loc']), 'msg': e['msg'], 'type': e['type']} for e in exc.errors()]
        return problem(422, 'validation_error', 'Dati non validi.', errors=errors)
