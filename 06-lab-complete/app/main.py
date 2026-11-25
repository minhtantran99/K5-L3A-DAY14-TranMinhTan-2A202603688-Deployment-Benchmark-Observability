"""
Production AI Agent — Part 6 Final Project.
"""
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import logging
import signal
import sys
import time

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget, record_cost
from app.rate_limiter import check_rate_limit
from app.redis_client import r, redis_healthy
from utils.mock_llm import ask as llm_ask


class JsonFormatter(logging.Formatter):
    """Format every log record as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "lvl": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extra_fields = getattr(record, "fields", None)
        if isinstance(extra_fields, dict):
            payload.update(extra_fields)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def _configure_logging() -> logging.Logger:
    log = logging.getLogger("production_agent")
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    log.setLevel(level)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    log.handlers = [handler]
    log.propagate = False
    return log


logger = _configure_logging()

_previous_sigterm = signal.getsignal(signal.SIGTERM)


def _handle_sigterm(signum, frame):
    """Log SIGTERM receipt and delegate to uvicorn's original handler for graceful exit."""
    logger.info("Received SIGTERM, initiating graceful shutdown", extra={"fields": {"event": "sigterm"}})
    if callable(_previous_sigterm):
        _previous_sigterm(signum, frame)


signal.signal(signal.SIGTERM, _handle_sigterm)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Manage startup and graceful shutdown lifecycle."""
    logger.info(
        "Agent starting",
        extra={"fields": {"event": "startup", "environment": settings.environment, "port": settings.port}},
    )
    yield
    logger.info("Agent shutting down gracefully", extra={"fields": {"event": "shutdown"}})
    if r is not None:
        try:
            r.close()
        except Exception:
            pass


app = FastAPI(
    title="Production AI Agent",
    lifespan=lifespan,
    docs_url="/docs" if settings.environment != "production" else None,
)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    """Log every HTTP request as structured JSON without exposing secrets."""
    started = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    logger.info(
        "HTTP request completed",
        extra={
            "fields": {
                "event": "request",
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "ms": elapsed_ms,
            }
        },
    )
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(_request: Request, exc: Exception):
    """Return clean 500 JSON without leaking stack traces."""
    logger.error(
        "Unhandled error",
        extra={"fields": {"event": "error", "error": type(exc).__name__}},
    )
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    user_id: str = Field(default="anonymous", max_length=128)


@app.get("/health")
def health():
    """Liveness probe — always returns 200 while process is alive."""
    return {"status": "ok", "environment": settings.environment}


@app.get("/ready")
def ready():
    """Readiness probe — returns 200 when Redis is reachable, 503 otherwise."""
    if not redis_healthy():
        raise HTTPException(status_code=503, detail="Redis unavailable")
    return {"status": "ready"}


@app.post("/ask")
def ask(body: AskRequest, api_key: str = Depends(verify_api_key)):
    """Protected AI agent endpoint with auth, Redis rate limiting, and cost guard."""
    check_rate_limit(api_key)
    check_budget()

    answer = llm_ask(body.question)

    input_tokens = max(1, len(body.question.split()) * 2)
    output_tokens = max(1, len(answer.split()) * 2)
    cost_usd = record_cost(input_tokens, output_tokens)

    return {
        "question": body.question,
        "answer": answer,
        "user_id": body.user_id,
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": round(cost_usd, 8),
        },
    }
