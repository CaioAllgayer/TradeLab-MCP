from __future__ import annotations

from pathlib import Path

from mcp_mt5 import server


def _ea(path: Path) -> None:
    path.write_text(
        """// @tradelab.strategy: RSI2
// @tradelab.entry: RSI(2)[1] < 10
// @tradelab.exit: RSI(2)[1] > 70
// @tradelab.bar_indices: 1
// @tradelab.trade_mode: SWING
#include "Include/TradeLabEA.mqh"
input double InpRiskPct = 2.0;
void OnTick(){ TradeLabOpenPosition(trade, _Symbol, ORDER_TYPE_BUY, 0, atr, InpRiskPct); }
""",
        encoding="utf-8",
    )


def test_ea_capabilities_exposes_required_defaults():
    result = server.ea_capabilities()
    defaults = {item["capability"]: item["default"] for item in result["capabilities"]}
    assert defaults["Sinal por barra"].startswith("[1]")
    assert defaults["RiskPct"] == "2%"
    assert defaults["Registry"].startswith("Consulta obrigatória")


def test_registry_and_creation_plan_tools(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TRADELAB_EXPERTS_DIR", str(tmp_path))
    _ea(tmp_path / "RSI2.mq5")

    refreshed = server.refresh_ea_registry()
    assert refreshed["registry"]["count"] == 1
    assert server.ea_registry("RSI2")["scenario"] == "equivalent"

    plan = server.plan_ea_creation(
        "RSI2",
        execution_timeframe="D1",
        trade_mode="SWING",
        exit_rule="RSI(2)[1] > 70",
    )
    assert plan["registry"]["scenario"] == "equivalent"
    assert plan["interpretation"]["signal_bar"] == 1
    assert plan["ready_to_implement"] is True


def test_validate_ea_standard_tool(tmp_path: Path):
    source = tmp_path / "RSI2.mq5"
    _ea(source)
    result = server.validate_ea_standard(str(source))
    assert result["compliant"] is True
