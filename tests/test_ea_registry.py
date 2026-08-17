from __future__ import annotations

from pathlib import Path

from mcp_mt5.ea_registry import build_registry, find_strategy, load_registry, refresh_registry


def _write_ea(path: Path, strategy: str, indicator_call: str = "iRSI") -> None:
    path.write_text(
        f"""// @tradelab.strategy: {strategy}
// @tradelab.execution_timeframe: D1
// @tradelab.bar_indices: 1
// @tradelab.entry: long signal
// @tradelab.exit: indicator exit
// @tradelab.direction: long
#property version "1.00"
input double InpRiskPct = 2.0;
input ulong InpMagic = 123456;
void OnTick() {{ int h = {indicator_call}(_Symbol, PERIOD_D1, 2, PRICE_CLOSE); }}
""",
        encoding="utf-8",
    )


def test_registry_catalogs_existing_ea(tmp_path: Path):
    _write_ea(tmp_path / "RSI2.mq5", "RSI(2) mean reversion")
    registry = build_registry(tmp_path)
    assert registry["count"] == 1
    ea = registry["strategies"][0]
    assert ea["name"] == "RSI2"
    assert ea["bar_indices"] == [1]
    assert ea["risk_pct_default"] == 2.0
    assert ea["sha256"]


def test_registry_finds_equivalent_and_similar_strategy(tmp_path: Path):
    _write_ea(tmp_path / "RSI2.mq5", "RSI2")
    _write_ea(tmp_path / "RubberBand.mq5", "RubberBand", "iBands")
    registry = build_registry(tmp_path)
    exact = find_strategy("RSI2", registry)
    similar = find_strategy("RubberBand EMA200", registry)
    assert exact["scenario"] == "equivalent"
    assert exact["best_match"]["name"] == "RSI2"
    assert exact["best_match"]["risk_pct_default"] == 2.0
    assert exact["best_match"]["magic_number"] == 123456
    assert similar["scenario"] == "similar"
    assert similar["best_match"]["name"] == "RubberBand"


def test_registry_refreshes_hash_when_ea_changes(tmp_path: Path):
    ea = tmp_path / "RSI2.mq5"
    registry_path = tmp_path / "registry.json"
    summary_path = tmp_path / "REGISTRY.md"
    _write_ea(ea, "RSI2")
    first = refresh_registry(tmp_path, registry_path=registry_path, summary_path=summary_path)
    first_hash = first["registry"]["strategies"][0]["sha256"]

    ea.write_text(ea.read_text(encoding="utf-8") + "// changed\n", encoding="utf-8")
    refreshed = load_registry(tmp_path, registry_path=registry_path, refresh_if_stale=True)
    assert refreshed["strategies"][0]["sha256"] != first_hash
    assert summary_path.exists()


def test_registry_skips_templates(tmp_path: Path):
    templates = tmp_path / "templates"
    templates.mkdir()
    _write_ea(templates / "TradeLabEA.template.mq5", "TEMPLATE")
    assert build_registry(tmp_path)["count"] == 0
