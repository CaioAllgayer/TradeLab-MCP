from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from mcp_mt5.ea_standard import (
    bar_index_for_time,
    build_creation_plan,
    daytrade_action,
    normalize_bar_index,
    normalize_risk_volume,
    resolve_stop_policy,
    validate_ea_source,
)


def test_missing_original_stop_receives_atr20_bar1_fallback():
    stop = resolve_stop_policy(None)
    assert stop == {
        "source": "tradelab_fallback",
        "rule": "3 x ATR(20)[1]",
        "indicator": "ATR",
        "period": 20,
        "multiplier": 3.0,
        "bar": 1,
        "fixed_after_entry": True,
        "required": True,
    }


def test_original_stop_is_preserved_exactly():
    stop = resolve_stop_policy("lowest low of the last 3 closed bars")
    assert stop["source"] == "original_setup"
    assert stop["rule"] == "lowest low of the last 3 closed bars"


def test_closed_bar_is_default_and_intrabar_must_be_explicit():
    assert normalize_bar_index(None) == 1
    assert normalize_bar_index(0) == 0
    with pytest.raises(ValueError):
        normalize_bar_index(2)


def test_mtf_plan_distinguishes_current_and_closed_higher_bar():
    closed = build_creation_plan(
        "RSI2 D1 on M5",
        {"scenario": "new"},
        execution_timeframe="M5",
        higher_timeframe="D1",
        trade_mode="SWING",
        exit_rule="RSI2 D1 > 70",
    )
    intrabar = build_creation_plan(
        "RSI2 D1 on M5",
        {"scenario": "new"},
        execution_timeframe="M5",
        higher_timeframe="D1",
        higher_timeframe_bar=0,
        trade_mode="SWING",
        exit_rule="RSI2 D1 > 70",
    )
    assert closed["interpretation"]["higher_timeframe_bar"] == 1
    assert intrabar["interpretation"]["higher_timeframe_bar"] == 0
    assert "congelado" in closed["notices"][-1]
    assert "muda intrabar" in intrabar["notices"][-1]


def test_position_sizing_depends_only_on_loss_to_stop():
    near_stop = normalize_risk_volume(100_000, 2, 500, 0.1, 100, 0.1)
    far_stop = normalize_risk_volume(100_000, 2, 1_000, 0.1, 100, 0.1)
    assert near_stop == 4.0
    assert far_stop == 2.0
    assert normalize_risk_volume(100_000, 2, 0, 0.1, 100, 0.1) == 0.0


def test_daytrade_blocks_and_forces_close_after_cutoff():
    session_end = datetime(2026, 8, 17, 18, 0)
    before = daytrade_action(datetime(2026, 8, 17, 16, 59), session_end, has_position=True)
    after = daytrade_action(datetime(2026, 8, 17, 17, 0), session_end, has_position=True)
    assert before == {"block_entry": False, "force_close": False}
    assert after == {"block_entry": True, "force_close": True}


def test_bar_lookup_does_not_require_exact_deal_timestamp():
    opens = [
        datetime(2026, 8, 17, 15, 0),
        datetime(2026, 8, 17, 14, 55),
        datetime(2026, 8, 17, 14, 50),
    ]
    assert bar_index_for_time(opens, datetime(2026, 8, 17, 14, 55, 23)) == 1


def test_validator_blocks_raw_entry_without_standard_wrapper(tmp_path: Path):
    source = tmp_path / "Legacy.mq5"
    source.write_text(
        "void OnTick(){ trade.Buy(1.0, _Symbol, 0, 0, 0); }\n",
        encoding="utf-8",
    )
    result = validate_ea_source(source)
    rules = {finding["rule"] for finding in result["findings"]}
    assert result["compliant"] is False
    assert "raw_trade_entry" in rules
    assert "missing_guarded_entry" in rules


def test_shared_mql_helpers_encode_required_guards():
    include = Path(__file__).parents[1] / "experts" / "Include" / "TradeLabEA.mqh"
    text = include.read_text(encoding="utf-8")
    assert "OrderCalcProfit" in text
    assert "SymbolInfoSessionTrade" in text
    assert "trade.ResultRetcode()" in text
    assert "iBarShift(symbol, timeframe, event_time, false)" in text
    assert "TradeLabIndicatorValue(fallback_atr20_handle, 0, 1" in text
    assert "TradeLabForceClose" in text
    assert "NormalizeVolume(100.0)" not in text
