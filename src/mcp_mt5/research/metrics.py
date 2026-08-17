"""Coerce Strategy Tester metrics to Python numbers. Does not recompute P&L."""
from __future__ import annotations

from typing import Any


NUMERIC_KEYS = (
    "net_profit",
    "gross_profit",
    "gross_loss",
    "profit_factor",
    "expected_payoff",
    "recovery_factor",
    "sharpe",
    "sharpe_ratio",
    "total_trades",
    "win_rate",
    "max_drawdown",
    "max_drawdown_pct",
    "balance_drawdown",
    "balance_drawdown_pct",
    "equity_drawdown",
    "equity_drawdown_pct",
    "initial_deposit",
    "profit_trades",
    "loss_trades",
)


def normalize_metrics(summary: dict[str, Any], trades: list[dict] | None = None) -> dict[str, Any]:
    """Copy tester-authoritative numbers; fill only obvious derived fields."""
    metrics: dict[str, Any] = {}
    for key in (
        "net_profit",
        "gross_profit",
        "gross_loss",
        "profit_factor",
        "expected_payoff",
        "recovery_factor",
        "sharpe",
        "total_trades",
        "win_rate",
        "max_drawdown",
        "max_drawdown_pct",
        "balance_drawdown",
        "equity_drawdown",
        "initial_deposit",
        "symbol",
        "period",
        "expert",
    ):
        if key in summary and summary[key] is not None:
            metrics[key] = summary[key]
    if "sharpe" not in metrics and summary.get("sharpe_ratio") is not None:
        metrics["sharpe"] = summary["sharpe_ratio"]
    if "balance_drawdown" not in metrics and summary.get("balance_drawdown_max") is not None:
        metrics["balance_drawdown"] = summary["balance_drawdown_max"]
    if "equity_drawdown" not in metrics and summary.get("equity_drawdown_max") is not None:
        metrics["equity_drawdown"] = summary["equity_drawdown_max"]

    if metrics.get("win_rate") is None and trades:
        closed = [
            t for t in trades
            if t.get("profit") is not None and (t.get("exit_time") or t.get("exit_price"))
        ]
        if closed:
            wins = sum(1 for t in closed if float(t["profit"]) > 0)
            metrics["win_rate"] = round(100.0 * wins / len(closed), 4)
    if metrics.get("total_trades") is None and trades:
        closed = [t for t in trades if t.get("exit_time") or t.get("profit")]
        metrics["total_trades"] = len(closed) if closed else len(trades)
    if isinstance(metrics.get("symbol"), str) and metrics["symbol"].lower() in {"tipo", "type", "ativo"}:
        metrics.pop("symbol", None)
    return metrics
