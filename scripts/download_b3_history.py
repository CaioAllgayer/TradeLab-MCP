"""Download M1 history for the B3 research universe via a live MT5 terminal."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import MetaTrader5 as mt5

UNIVERSE = [
    "PETR4", "VALE3", "ITUB4", "BBDC4", "BBAS3",
    "B3SA3", "WEGE3", "ABEV3", "PRIO3", "SUZB3",
    "RENT3", "EQTL3", "VIVT3", "GGBR4", "CSAN3",
]
FROM = datetime(2018, 1, 1)
TO = datetime(2026, 1, 1)


def download_symbol(name: str) -> dict:
    info = mt5.symbol_info(name)
    if info is None:
        return {"symbol": name, "ok": False, "error": "not in Market Watch catalog"}
    if not mt5.symbol_select(name, True):
        return {"symbol": name, "ok": False, "error": f"symbol_select failed {mt5.last_error()}"}

    years = []
    total = 0
    first = last = None
    year = FROM.year
    while year < TO.year:
        start = datetime(year, 1, 1)
        end = datetime(year + 1, 1, 1)
        rates = mt5.copy_rates_range(name, mt5.TIMEFRAME_M1, start, end)
        count = 0 if rates is None else len(rates)
        years.append({"year": year, "m1_bars": count})
        if rates is not None and count:
            total += count
            if first is None:
                first = int(rates[0]["time"])
            last = int(rates[-1]["time"])
        year += 1

    d1 = mt5.copy_rates_range(name, mt5.TIMEFRAME_D1, FROM, TO)
    return {
        "symbol": name,
        "ok": total > 0,
        "visible": bool(mt5.symbol_info(name).visible),
        "m1_bars": total,
        "d1_bars": 0 if d1 is None else len(d1),
        "first_m1": datetime.fromtimestamp(first, tz=timezone.utc).isoformat() if first else None,
        "last_m1": datetime.fromtimestamp(last, tz=timezone.utc).isoformat() if last else None,
        "years": years,
        "error": None if total > 0 else f"no M1 bars {mt5.last_error()}",
    }


def main() -> int:
    if not mt5.initialize():
        print("initialize failed", mt5.last_error())
        return 1
    acc = mt5.account_info()
    print("account", None if acc is None else acc.login, None if acc is None else acc.server)
    results = []
    for name in UNIVERSE:
        row = download_symbol(name)
        results.append(row)
        print(f"{name:8} ok={row['ok']} m1={row.get('m1_bars')} d1={row.get('d1_bars')} {row.get('first_m1')} -> {row.get('last_m1')} {row.get('error') or ''}")
    out = Path(__file__).resolve().parents[1] / "research" / "experiments" / "b3_rsi2_universe"
    out.mkdir(parents=True, exist_ok=True)
    payload = {
        "downloaded_at": datetime.now().isoformat(),
        "from": FROM.isoformat(),
        "to": TO.isoformat(),
        "results": results,
    }
    (out / "download.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    mt5.shutdown()
    failed = [r["symbol"] for r in results if not r["ok"]]
    print("failed", failed or "none")
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
