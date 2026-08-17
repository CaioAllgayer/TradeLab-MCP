"""Normalize tester deals/trades into a stable research schema."""
from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

from ..parsers import parse_number, read_text_auto

TRADE_FIELDS = (
    "ticket",
    "symbol",
    "side",
    "entry_time",
    "entry_price",
    "exit_time",
    "exit_price",
    "volume",
    "profit",
    "commission",
    "swap",
    "reason",
)


def empty_trade() -> dict[str, Any]:
    return {k: None for k in TRADE_FIELDS}


def write_trades_csv(path: str | Path, trades: list[dict[str, Any]]) -> Path:
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(TRADE_FIELDS))
        writer.writeheader()
        for trade in trades:
            writer.writerow({k: trade.get(k, "") for k in TRADE_FIELDS})
    return dest


def read_trades_csv(path: str | Path) -> list[dict[str, Any]]:
    text = read_text_auto(Path(path))
    return parse_trades_csv(text)


def parse_trades_csv(text: str) -> list[dict[str, Any]]:
    sample = text.lstrip("\ufeff")
    if not sample.strip():
        return []
    reader = csv.DictReader(io.StringIO(sample))
    if not reader.fieldnames:
        return []
    fields = [f.strip().lower() for f in reader.fieldnames]
    if _is_deal_export(fields):
        deals = []
        for row in reader:
            deals.append({(k or "").strip().lower(): (v or "").strip() for k, v in row.items()})
        return pair_deals(deals)
    trades: list[dict[str, Any]] = []
    for row in reader:
        normalized = empty_trade()
        for key, value in row.items():
            canon = (key or "").strip().lower()
            if canon in TRADE_FIELDS:
                normalized[canon] = _coerce_field(canon, value)
        trades.append(normalized)
    return trades


def _is_deal_export(fields: list[str]) -> bool:
    return "position_id" in fields or "deal" in fields and "entry" in fields


def _coerce_field(name: str, value: Any) -> Any:
    if value is None or value == "":
        return None
    if name in {"entry_price", "exit_price", "volume", "profit", "commission", "swap"}:
        return parse_number(value)
    if name == "side":
        return str(value).strip().lower()
    return str(value).strip()


def pair_deals(deals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group IN/OUT deals by position_id into the research trade schema."""
    groups: dict[str, list[dict[str, Any]]] = {}
    unmatched: list[dict[str, Any]] = []
    for deal in deals:
        pid = str(deal.get("position_id") or deal.get("position") or "").strip()
        if not pid:
            unmatched.append(deal)
            continue
        groups.setdefault(pid, []).append(deal)

    trades: list[dict[str, Any]] = []
    for pid, rows in groups.items():
        rows_sorted = sorted(rows, key=lambda d: str(d.get("time") or d.get("entry_time") or ""))
        entry = _first_entry(rows_sorted)
        exit_ = _last_exit(rows_sorted)
        if entry is None:
            entry = rows_sorted[0]
        if exit_ is None:
            exit_ = rows_sorted[-1]
        side = _side_from_deal(entry)
        profit = _sum_num(rows_sorted, "profit")
        commission = _sum_num(rows_sorted, "commission")
        swap = _sum_num(rows_sorted, "swap")
        trades.append({
            "ticket": str(pid),
            "symbol": entry.get("symbol") or exit_.get("symbol"),
            "side": side,
            "entry_time": entry.get("time") or entry.get("entry_time"),
            "entry_price": parse_number(entry.get("price") or entry.get("entry_price")),
            "exit_time": exit_.get("time") or exit_.get("exit_time"),
            "exit_price": parse_number(exit_.get("price") or exit_.get("exit_price")),
            "volume": parse_number(entry.get("volume") or entry.get("qty")),
            "profit": profit,
            "commission": commission,
            "swap": swap,
            "reason": exit_.get("reason") or exit_.get("comment") or "",
        })
    for deal in unmatched:
        trades.append({
            "ticket": deal.get("deal") or deal.get("ticket"),
            "symbol": deal.get("symbol"),
            "side": _side_from_deal(deal),
            "entry_time": deal.get("time") or deal.get("entry_time"),
            "entry_price": parse_number(deal.get("price") or deal.get("entry_price")),
            "exit_time": deal.get("time") or deal.get("exit_time"),
            "exit_price": parse_number(deal.get("price") or deal.get("exit_price")),
            "volume": parse_number(deal.get("volume")),
            "profit": parse_number(deal.get("profit")),
            "commission": parse_number(deal.get("commission")),
            "swap": parse_number(deal.get("swap")),
            "reason": deal.get("reason") or deal.get("comment") or "",
        })
    return trades


def _first_entry(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    for row in rows:
        entry = str(row.get("entry") or "").lower()
        if entry in {"in", "1", "deal_entry_in"}:
            return row
    return None


def _last_exit(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    for row in reversed(rows):
        entry = str(row.get("entry") or "").lower()
        if entry in {"out", "2", "deal_entry_out", "inout", "out_by"}:
            return row
    return None


def _side_from_deal(deal: dict[str, Any]) -> str:
    raw = str(deal.get("side") or deal.get("type") or "").strip().lower()
    if raw in {"buy", "0", "deal_type_buy"}:
        return "buy"
    if raw in {"sell", "1", "deal_type_sell"}:
        return "sell"
    return raw or "buy"


def _sum_num(rows: list[dict[str, Any]], key: str) -> float | None:
    total = 0.0
    seen = False
    for row in rows:
        number = parse_number(row.get(key))
        if number is not None:
            total += number
            seen = True
    return round(total, 8) if seen else None


def trades_from_html_rows(rows: list[dict[str, Any]], symbol: str | None = None) -> list[dict[str, Any]]:
    """Best-effort mapping of tester HTML order/deal rows."""
    out: list[dict[str, Any]] = []
    for row in rows:
        trade = empty_trade()
        trade["ticket"] = row.get("ticket") or row.get("order") or row.get("deal")
        trade["symbol"] = row.get("symbol") or symbol
        trade["side"] = (row.get("side") or row.get("type") or "").lower() or None
        trade["entry_time"] = row.get("time") or row.get("entry_time")
        trade["entry_price"] = parse_number(row.get("price") or row.get("entry_price"))
        trade["exit_time"] = row.get("exit_time")
        trade["exit_price"] = parse_number(row.get("exit_price"))
        trade["volume"] = parse_number(row.get("volume") or row.get("size"))
        trade["profit"] = parse_number(row.get("profit"))
        trade["commission"] = parse_number(row.get("commission"))
        trade["swap"] = parse_number(row.get("swap"))
        trade["reason"] = row.get("reason") or row.get("comment")
        if any(trade.get(k) is not None for k in ("ticket", "profit", "entry_price")):
            out.append(trade)
    return out
