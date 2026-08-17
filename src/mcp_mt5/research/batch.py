"""Sequential multi-symbol backtests. No parallelism in V1."""
from __future__ import annotations

from typing import Any, Callable


def run_batch(
    backtest_fn: Callable[..., dict[str, Any]],
    *,
    strategy: str,
    symbols: list[str],
    period: str,
    from_date: str,
    to_date: str,
    inputs: dict | None = None,
    model: int = 4,
    deposit: float = 100000,
    currency: str = "BRL",
    leverage: str | int = "1:100",
    timeout_sec: int = 1800,
) -> dict[str, Any]:
    if not symbols:
        return {"error": "symbols list is empty", "runs": []}
    runs: list[dict[str, Any]] = []
    for symbol in symbols:
        result = backtest_fn(
            strategy=strategy,
            symbol=symbol,
            timeframe=period,
            from_date=from_date,
            to_date=to_date,
            inputs=inputs or {},
            model=model,
            deposit=deposit,
            currency=currency,
            leverage=leverage,
            timeout_sec=timeout_sec,
        )
        runs.append(result)
    completed = sum(1 for r in runs if r.get("status") == "completed")
    return {
        "strategy": strategy,
        "period": period,
        "count": len(runs),
        "completed": completed,
        "failed": len(runs) - completed,
        "runs": runs,
    }
