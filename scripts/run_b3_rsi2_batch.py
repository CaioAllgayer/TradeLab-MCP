"""Sequential RSI2 batch on the B3 universe. MT5 Strategy Tester only."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from mcp_mt5.paths import detect_layout
from mcp_mt5.research.config import bundled_experts_dir
from mcp_mt5.research.ids import new_experiment_id
from mcp_mt5.research.runner import execute_backtest
from mcp_mt5.research.store import ResearchStore, utc_now

UNIVERSE = [
    "PETR4", "VALE3", "ITUB4", "BBDC4", "BBAS3",
    "B3SA3", "WEGE3", "ABEV3", "PRIO3", "SUZB3",
    "RENT3", "EQTL3", "VIVT3", "GGBR4", "CSAN3",
]
WINDOWS = {
    "IS": ("2018.01.01", "2023.12.31"),
    "OOS": ("2024.01.01", "2025.12.31"),
}
INPUTS = {
    "InpRSIPeriod": 2,
    "InpRSIBuy": 10,
    "InpRSIExit": 70,
    "InpAtrPeriod": 20,
    "InpAtrMult": 3,
    "InpMaxBars": 9,
    "InpTrendPeriod": 50,
    "InpRiskPct": 1,
    "InpLots": 0,
    "InpMagic": 20260817,
}


def main() -> int:
    root = Path(__file__).resolve().parents[1] / "research"
    store = ResearchStore(root)
    layout = detect_layout()
    ea = bundled_experts_dir() / "RSI2.mq5"
    experiment_id = new_experiment_id()
    record = {
        "experiment_id": experiment_id,
        "type": "universe_batch",
        "strategy": "RSI2",
        "created_at": utc_now(),
        "model": 1,
        "deposit": 100000,
        "currency": "BRL",
        "inputs": INPUTS,
        "windows": WINDOWS,
        "symbols": UNIVERSE,
        "runs": [],
    }

    for symbol in UNIVERSE:
        for window, (start, end) in WINDOWS.items():
            print(f"=== {symbol} {window} {start} {end} ===", flush=True)
            result = execute_backtest(
                layout=layout,
                strategy=str(ea),
                symbol=symbol,
                timeframe="D1",
                from_date=start,
                to_date=end,
                inputs=INPUTS,
                model=1,
                deposit=100000,
                currency="BRL",
                leverage="1:100",
                timeout_sec=900,
                store=store,
            )
            metrics = result.get("metrics") or {}
            row = {
                "symbol": symbol,
                "window": window,
                "from": start,
                "to": end,
                "run_id": result.get("run_id"),
                "status": result.get("status"),
                "error": result.get("error"),
                "metrics": metrics,
            }
            record["runs"].append(row)
            print(
                f"    {result.get('status')} {result.get('run_id')} "
                f"trades={metrics.get('total_trades')} pf={metrics.get('profit_factor')} "
                f"net={metrics.get('net_profit')} {result.get('error') or ''}",
                flush=True,
            )

    dest = root / "experiments" / "b3_rsi2_universe"
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / f"{experiment_id}.json"
    path.write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
    store.write_experiment(experiment_id, record)
    _write_ranking(dest, record)
    print("wrote", path)
    return 0


def _write_ranking(dest: Path, record: dict) -> None:
    by_symbol: dict[str, dict] = {}
    for row in record["runs"]:
        by_symbol.setdefault(row["symbol"], {})[row["window"]] = row
    lines = [
        "symbol,is_status,is_trades,is_net,is_pf,is_dd,is_win,oos_status,oos_trades,oos_net,oos_pf,oos_dd,oos_win,is_run,oos_run"
    ]
    for symbol in record["symbols"]:
        is_ = by_symbol.get(symbol, {}).get("IS", {})
        oos = by_symbol.get(symbol, {}).get("OOS", {})
        im, om = is_.get("metrics") or {}, oos.get("metrics") or {}
        lines.append(
            ",".join([
                symbol,
                str(is_.get("status") or ""),
                _n(im.get("total_trades")),
                _n(im.get("net_profit")),
                _n(im.get("profit_factor")),
                _n(im.get("equity_drawdown")),
                _n(im.get("win_rate")),
                str(oos.get("status") or ""),
                _n(om.get("total_trades")),
                _n(om.get("net_profit")),
                _n(om.get("profit_factor")),
                _n(om.get("equity_drawdown")),
                _n(om.get("win_rate")),
                str(is_.get("run_id") or ""),
                str(oos.get("run_id") or ""),
            ])
        )
    (dest / "ranking.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _n(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
