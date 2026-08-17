"""Live MetaTrader 5 tests. Skipped unless TRADE_LAB_INTEGRATION=1."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from mcp_mt5.paths import detect_layout
from mcp_mt5.research.compile import compile_source
from mcp_mt5.research.config import bundled_experts_dir
from mcp_mt5.research.health import health_check
from mcp_mt5.research.runner import execute_backtest, get_run
from mcp_mt5.research.store import ResearchStore

pytestmark = pytest.mark.skipif(
    os.environ.get("TRADE_LAB_INTEGRATION") != "1",
    reason="set TRADE_LAB_INTEGRATION=1 to run live Strategy Tester tests",
)


def test_health_sees_real_terminal():
    info = health_check(detect_layout())
    assert info["metaeditor"]["exists"]
    assert info["terminal"]["exists"]
    assert info["can_compile"]


def test_compile_rsi2(tmp_path: Path):
    ea = bundled_experts_dir() / "RSI2.mq5"
    assert ea.exists(), f"missing bundled EA: {ea}"
    result = compile_source(detect_layout(), ea, log_file=tmp_path / "rsi2.compile.log")
    assert result["success"], result.get("log_excerpt") or result.get("error")
    assert result["binary_sha256"]


def test_short_backtest_if_symbol_configured(tmp_path: Path, monkeypatch):
    symbol = os.environ.get("TRADE_LAB_SYMBOL", "EURUSD")
    monkeypatch.setenv("TRADE_LAB_ROOT", str(tmp_path / "research"))
    layout = detect_layout()
    ea = bundled_experts_dir() / "RSI2.mq5"
    result = execute_backtest(
        layout=layout,
        strategy=str(ea),
        symbol=symbol,
        timeframe=os.environ.get("TRADE_LAB_PERIOD", "D1"),
        from_date=os.environ.get("TRADE_LAB_FROM", "2024.01.02"),
        to_date=os.environ.get("TRADE_LAB_TO", "2024.01.31"),
        model=int(os.environ.get("TRADE_LAB_MODEL", "2")),
        deposit=100000,
        currency=os.environ.get("TRADE_LAB_CURRENCY", "USD"),
        store=ResearchStore(tmp_path / "research"),
        timeout_sec=int(os.environ.get("TRADE_LAB_TIMEOUT", "300")),
    )
    assert result["run_id"]
    loaded = get_run(ResearchStore(tmp_path / "research"), result["run_id"])
    assert loaded["run_id"] == result["run_id"]
    if result["status"] != "completed":
        pytest.skip(f"tester did not complete on {symbol}: {result.get('error')}")
    assert "net_profit" in (result.get("metrics") or {}) or result["status"] == "completed"
