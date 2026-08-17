"""Exclusive tester.ini generation and date/timeframe normalization."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

MODEL_NAMES = {
    0: "every_tick",
    1: "1min_ohlc",
    2: "open_prices",
    3: "m1_ohlc",
    4: "real_ticks",
}
MODEL_ALIASES = {
    "every_tick": 0,
    "every tick": 0,
    "0": 0,
    "1min_ohlc": 1,
    "1 minute ohlc": 1,
    "1": 1,
    "open_prices": 2,
    "open prices": 2,
    "2": 2,
    "m1_ohlc": 3,
    "3": 3,
    "real_ticks": 4,
    "real ticks": 4,
    "4": 4,
}

PERIOD_ALIASES = {
    "PERIOD_M1": "M1",
    "PERIOD_M5": "M5",
    "PERIOD_M15": "M15",
    "PERIOD_M30": "M30",
    "PERIOD_H1": "H1",
    "PERIOD_H4": "H4",
    "PERIOD_D1": "D1",
    "PERIOD_W1": "W1",
    "PERIOD_MN1": "MN1",
    "1": "M1",
    "5": "M5",
    "15": "M15",
    "30": "M30",
    "16385": "H1",
    "16388": "H4",
    "16408": "D1",
    "32769": "W1",
    "49153": "MN1",
}


def normalize_date(value: str) -> str:
    text = (value or "").strip().replace("-", ".")
    datetime.strptime(text, "%Y.%m.%d")
    return text


def normalize_period(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        raise ValueError("period/timeframe is required")
    return PERIOD_ALIASES.get(raw, PERIOD_ALIASES.get(raw.upper(), raw.upper()))


def normalize_model(value: int | str) -> int:
    if isinstance(value, bool):
        raise ValueError("invalid model")
    if isinstance(value, int):
        if value not in MODEL_NAMES:
            raise ValueError(f"unsupported model: {value}")
        return value
    key = str(value).strip().lower()
    if key not in MODEL_ALIASES:
        raise ValueError(f"unsupported model: {value}")
    return MODEL_ALIASES[key]


def model_name(model: int) -> str:
    return MODEL_NAMES.get(model, str(model))


def format_leverage(value: str | int | float) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if float(value) <= 0:
            raise ValueError("leverage must be > 0")
        if float(value).is_integer():
            return str(int(value))
        return str(value)
    text = str(value).strip()
    if re.fullmatch(r"\d+:\d+", text):
        left, right = text.split(":")
        if int(left) <= 0 or int(right) <= 0:
            raise ValueError(f"invalid leverage: {text}")
        return text
    number = float(text)
    if number <= 0:
        raise ValueError("leverage must be > 0")
    return text


def format_tester_input(name: str, value: object) -> str:
    raw = str(value)
    return f"{name}={raw}||{raw}||0||{raw}||N"


def write_tester_ini(
    path: str | Path,
    *,
    expert: str,
    symbol: str,
    period: str,
    from_date: str,
    to_date: str,
    model: int = 4,
    deposit: float = 100000,
    currency: str = "BRL",
    leverage: str | int = "1:100",
    report: str,
    inputs: dict[str, object] | None = None,
    optimization: int = 0,
    visual: int = 0,
    shutdown_terminal: int = 0,
) -> Path:
    """Write a run-exclusive tester.ini. Never patches a shared global file."""
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    from_s = normalize_date(from_date)
    to_s = normalize_date(to_date)
    if datetime.strptime(from_s, "%Y.%m.%d") > datetime.strptime(to_s, "%Y.%m.%d"):
        raise ValueError(f"from_date {from_s} is after to_date {to_s}")
    period_s = normalize_period(period)
    model_i = normalize_model(model)
    leverage_s = format_leverage(leverage)

    lines = [
        "[Tester]",
        f"Expert={expert}",
        f"Symbol={symbol}",
        f"Period={period_s}",
        f"Optimization={int(optimization)}",
        f"Model={model_i}",
        f"FromDate={from_s}",
        f"ToDate={to_s}",
        "ForwardMode=0",
        f"Deposit={_format_deposit(deposit)}",
        f"Currency={currency}",
        f"Leverage={leverage_s}",
        "ExecutionMode=0",
        f"Visual={int(visual)}",
        f"ShutdownTerminal={1 if int(shutdown_terminal) else 0}",
        "ReplaceReport=1",
        f"Report={report}",
        "",
        "[TesterInputs]",
    ]
    for name, value in (inputs or {}).items():
        lines.append(format_tester_input(name, value))
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return dest


def _format_deposit(deposit: float | int | str) -> str:
    number = float(deposit)
    if number <= 0:
        raise ValueError("deposit must be > 0")
    if float(number).is_integer():
        return str(int(number))
    return str(number)


def parse_ini_sections(path: str | Path) -> dict[str, dict[str, str]]:
    sections: dict[str, dict[str, str]] = {}
    current = ""
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith(";") or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1]
            sections.setdefault(current, {})
            continue
        if "=" in line and current:
            key, value = line.split("=", 1)
            sections[current][key.strip()] = value.strip()
    return sections
