"""
Cost guard (tiêu chí 8) — track cumulative LLM spend in Redis and enforce budget.
"""
from datetime import datetime, timezone

from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

# Giá USD / 1K tokens (tham khảo gpt-4o-mini)
PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006


def _budget_keys() -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    return (
        f"cost:daily:{now.strftime('%Y-%m-%d')}",
        f"cost:monthly:{now.strftime('%Y-%m')}",
    )


def check_budget() -> None:
    """Check accumulated spend in Redis before calling LLM; raise 402 if exceeded."""
    if r is None:
        raise HTTPException(status_code=503, detail="Cost guard store unavailable")

    daily_key, monthly_key = _budget_keys()
    try:
        daily_spent = float(r.get(daily_key) or 0.0)
        monthly_spent = float(r.get(monthly_key) or 0.0)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Cost guard store error") from exc

    if daily_spent >= settings.daily_budget_usd or monthly_spent >= settings.monthly_budget_usd:
        raise HTTPException(
            status_code=402,
            detail="LLM budget exceeded",
        )


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Record request cost in Redis after calling LLM and return request cost in USD."""
    cost = (
        (input_tokens / 1000.0) * PRICE_INPUT_PER_1K
        + (output_tokens / 1000.0) * PRICE_OUTPUT_PER_1K
    )
    if r is None:
        return cost

    daily_key, monthly_key = _budget_keys()
    try:
        pipe = r.pipeline()
        pipe.incrbyfloat(daily_key, cost)
        pipe.expire(daily_key, 2 * 24 * 3600)
        pipe.incrbyfloat(monthly_key, cost)
        pipe.expire(monthly_key, 32 * 24 * 3600)
        pipe.execute()
    except Exception:
        pass
    return cost
