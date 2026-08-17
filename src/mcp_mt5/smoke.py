"""Smoke test: compile + 1-day backtest + journal error scan."""
from __future__ import annotations

import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from .parsers import read_text_auto


_RUNTIME_ERROR_PATTERNS = [
    re.compile(r"\berror\b", re.IGNORECASE),
    re.compile(r"\bcritical\b", re.IGNORECASE),
    re.compile(r"\bfatal\b", re.IGNORECASE),
    re.compile(r"OnInit\s+returned\s+(?!INIT_SUCCEEDED)", re.IGNORECASE),
    re.compile(r"unable to load", re.IGNORECASE),
    re.compile(r"failed to (initialize|run)", re.IGNORECASE),
    re.compile(r"access violation", re.IGNORECASE),
    re.compile(r"divide by zero", re.IGNORECASE),
    re.compile(r"array out of range", re.IGNORECASE),
    re.compile(r"stack overflow", re.IGNORECASE),
]

# Lines we explicitly do not want to count as failures.
_BENIGN_PATTERNS = [
    re.compile(r"\b0\s+errors?\b", re.IGNORECASE),
    re.compile(r"no errors", re.IGNORECASE),
    re.compile(r"successfully", re.IGNORECASE),
]


def write_smoke_tester_ini(
    expert_name: str,
    target_path: Path,
    symbol: str = "EURUSD",
    period: str = "M15",
    days: int = 1,
    deposit: float = 10000.0,
    leverage: int | str = 500,
    model: int = 2,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    currency: str = "USD",
    report: str = "smoke_report",
) -> Path:
    """Write a minimal headless tester.ini for a smoke run."""
    if from_date and to_date:
        start_s, end_s = from_date, to_date
    else:
        end = datetime.now().date() - timedelta(days=2)
        start = end - timedelta(days=days)
        start_s, end_s = start.strftime("%Y.%m.%d"), end.strftime("%Y.%m.%d")
    body = f"""\
[Tester]
Expert={expert_name}
Symbol={symbol}
Period={period}
Optimization=0
Model={model}
FromDate={start_s}
ToDate={end_s}
ForwardMode=0
Deposit={deposit}
Currency={currency}
Leverage={leverage}
ExecutionMode=0
Visual=0
ShutdownTerminal=1
ReplaceReport=1
Report={report}

[TesterInputs]
"""
    target_path.write_text(body, encoding="utf-8")
    return target_path


def scan_journal_for_errors(log_path: Path) -> dict:
    """Read a tester journal and return matched error lines (with benign lines filtered)."""
    if not log_path.exists():
        return {"error": f"log not found: {log_path}", "matches": []}
    text = read_text_auto(log_path)
    matches: list[dict] = []
    for i, line in enumerate(text.splitlines(), 1):
        if any(p.search(line) for p in _BENIGN_PATTERNS):
            continue
        for pat in _RUNTIME_ERROR_PATTERNS:
            if pat.search(line):
                matches.append({"line": i, "text": line.strip(), "rule": pat.pattern})
                break
    return {"matches": matches, "match_count": len(matches), "log_path": str(log_path)}


def run_smoke(
    layout,
    source: str | Path,
    expert_name: Optional[str] = None,
    symbol: str = "EURUSD",
    period: str = "M15",
    days: int = 1,
    timeout_sec: int = 600,
    model: int = 2,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    deposit: float = 10000.0,
    currency: str = "USD",
    leverage: int | str = "1:100",
) -> dict:
    """End-to-end smoke harness.

    1. Compile the source.
    2. Deploy the binary.
    3. Write a 1-day headless `tester.ini`.
    4. Launch the terminal and wait for shutdown.
    5. Scan the resulting tester journal for runtime errors.

    Returns a `pass`/`fail` summary plus the full sub-results so the caller can drill in.
    """
    src = Path(source)
    if not src.exists():
        return {"ok": False, "stage": "input", "error": f"source not found: {src}"}

    if not from_date or not to_date:
        end = datetime.now().date() - timedelta(days=2)
        start = end - timedelta(days=days)
        from_date = start.strftime("%Y.%m.%d")
        to_date = end.strftime("%Y.%m.%d")

    from .research.runner import execute_backtest

    started = time.time()
    result = execute_backtest(
        layout=layout,
        strategy=str(src),
        symbol=symbol,
        timeframe=period,
        from_date=from_date,
        to_date=to_date,
        model=model,
        deposit=deposit,
        currency=currency,
        leverage=leverage,
        timeout_sec=timeout_sec,
    )
    elapsed = round(time.time() - started, 2)
    artifacts = result.get("artifacts") or {}
    log_path = artifacts.get("tester.log")
    scan = {"match_count": 0, "matches": []}
    if log_path:
        scan = scan_journal_for_errors(Path(log_path))
    ok = result.get("status") == "completed" and scan["match_count"] == 0
    return {
        "ok": ok,
        "stage": result.get("stage") or result.get("status"),
        "run_id": result.get("run_id"),
        "elapsed_sec": elapsed,
        "expert": expert_name or src.stem,
        "symbol": symbol,
        "period": period,
        "model": model,
        "from_date": from_date,
        "to_date": to_date,
        "tester_log": log_path,
        "errors_found": scan["match_count"],
        "errors_sample": scan["matches"][:20],
        "metrics": result.get("metrics") or {},
        "error": result.get("error"),
    }
