"""Walk-forward as a sequence of official Strategy Tester runs."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Callable

from .ids import new_experiment_id
from .store import ResearchStore, utc_now


def parse_day(value: str) -> datetime:
    text = value.strip().replace("-", ".")
    return datetime.strptime(text, "%Y.%m.%d")


def fmt_day(value: datetime) -> str:
    return value.strftime("%Y.%m.%d")


def build_windows(
    from_date: str,
    to_date: str,
    is_days: int,
    oos_days: int,
    step_days: int | None = None,
) -> list[dict[str, str]]:
    if is_days <= 0 or oos_days <= 0:
        raise ValueError("is_days and oos_days must be > 0")
    step = step_days if step_days is not None else oos_days
    if step <= 0:
        raise ValueError("step_days must be > 0")

    start = parse_day(from_date)
    end = parse_day(to_date)
    windows: list[dict[str, str]] = []
    cursor = start
    while True:
        is_start = cursor
        is_end = is_start + timedelta(days=is_days - 1)
        oos_start = is_end + timedelta(days=1)
        oos_end = oos_start + timedelta(days=oos_days - 1)
        if oos_end > end:
            break
        windows.append({
            "is_from": fmt_day(is_start),
            "is_to": fmt_day(is_end),
            "oos_from": fmt_day(oos_start),
            "oos_to": fmt_day(oos_end),
        })
        cursor = cursor + timedelta(days=step)
    return windows


def run_walk_forward(
    *,
    store: ResearchStore,
    backtest_fn: Callable[..., dict[str, Any]],
    strategy: str,
    symbol: str,
    timeframe: str,
    from_date: str,
    to_date: str,
    is_days: int,
    oos_days: int,
    step_days: int | None = None,
    inputs: dict | None = None,
    model: int = 4,
    deposit: float = 100000,
    currency: str = "BRL",
    leverage: str | int = "1:100",
    timeout_sec: int = 1800,
) -> dict[str, Any]:
    windows = build_windows(from_date, to_date, is_days, oos_days, step_days)
    experiment_id = new_experiment_id()
    record: dict[str, Any] = {
        "experiment_id": experiment_id,
        "type": "walk_forward",
        "created_at": utc_now(),
        "strategy": strategy,
        "symbol": symbol,
        "timeframe": timeframe,
        "from": from_date,
        "to": to_date,
        "is_days": is_days,
        "oos_days": oos_days,
        "step_days": step_days if step_days is not None else oos_days,
        "model": model,
        "windows": [],
    }

    for spec in windows:
        is_run = backtest_fn(
            strategy=strategy,
            symbol=symbol,
            timeframe=timeframe,
            from_date=spec["is_from"],
            to_date=spec["is_to"],
            inputs=inputs or {},
            model=model,
            deposit=deposit,
            currency=currency,
            leverage=leverage,
            timeout_sec=timeout_sec,
        )
        oos_run = backtest_fn(
            strategy=strategy,
            symbol=symbol,
            timeframe=timeframe,
            from_date=spec["oos_from"],
            to_date=spec["oos_to"],
            inputs=inputs or {},
            model=model,
            deposit=deposit,
            currency=currency,
            leverage=leverage,
            timeout_sec=timeout_sec,
        )
        record["windows"].append({
            **spec,
            "is_run": is_run.get("run_id"),
            "oos_run": oos_run.get("run_id"),
            "is_status": is_run.get("status"),
            "oos_status": oos_run.get("status"),
            "is_metrics": is_run.get("metrics") or {},
            "oos_metrics": oos_run.get("metrics") or {},
        })

    store.write_experiment(experiment_id, record)
    return record
