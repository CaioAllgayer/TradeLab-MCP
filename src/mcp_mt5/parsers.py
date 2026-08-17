"""Parsers for MetaEditor compile log and Strategy Tester reports."""
from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterator


def read_text_auto(path: Path) -> str:
    raw = path.read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16", errors="replace")
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8", errors="replace")
    return raw.decode("utf-8", errors="replace")


_DIAG_RE = re.compile(r"^(?P<file>.*?)\((?P<line>\d+),(?P<col>\d+)\)\s*:\s*(?P<sev>error|warning)\s+(?P<code>\d+):\s*(?P<msg>.*)$")
_RESULT_RE = re.compile(r"Result:\s*(\d+)\s*errors?,\s*(\d+)\s*warnings?", re.IGNORECASE)


def parse_compile_log(text: str) -> dict:
    """Extract structured diagnostics + result summary from MetaEditor /log output."""
    errors: list[dict] = []
    warnings: list[dict] = []
    result_errors = result_warnings = None

    for line in text.splitlines():
        m = _DIAG_RE.match(line.strip())
        if m:
            d = {
                "file": m.group("file").strip(),
                "line": int(m.group("line")),
                "col": int(m.group("col")),
                "code": int(m.group("code")),
                "message": m.group("msg").strip(),
            }
            if m.group("sev") == "error":
                errors.append(d)
            else:
                warnings.append(d)
            continue
        rm = _RESULT_RE.search(line)
        if rm:
            result_errors = int(rm.group(1))
            result_warnings = int(rm.group(2))

    return {
        "errors": errors,
        "warnings": warnings,
        "result_errors": result_errors if result_errors is not None else len(errors),
        "result_warnings": result_warnings if result_warnings is not None else len(warnings),
        "ok": (result_errors == 0) if result_errors is not None else len(errors) == 0,
    }


class _ReportParser(HTMLParser):
    """Pull rows out of MT5 tester report HTML tables."""

    def __init__(self) -> None:
        super().__init__()
        self.in_td = False
        self.in_th = False
        self.row: list[str] = []
        self.rows: list[list[str]] = []
        self.cell_buf: list[str] = []

    def handle_starttag(self, tag: str, attrs):
        t = tag.lower()
        if t == "tr":
            self.row = []
        elif t in ("td", "th"):
            self.cell_buf = []
            if t == "td":
                self.in_td = True
            else:
                self.in_th = True

    def handle_endtag(self, tag: str):
        t = tag.lower()
        if t in ("td", "th"):
            self.row.append("".join(self.cell_buf).strip())
            self.in_td = self.in_th = False
        elif t == "tr":
            if self.row:
                self.rows.append(self.row)
            self.row = []

    def handle_data(self, data: str):
        if self.in_td or self.in_th:
            self.cell_buf.append(data)


_LABEL_MAP = {
    "total net profit": "net_profit",
    "lucro líquido total": "net_profit",
    "lucro liquido total": "net_profit",
    "чистая прибыль": "net_profit",
    "gross profit": "gross_profit",
    "lucro bruto": "gross_profit",
    "валовая прибыль": "gross_profit",
    "gross loss": "gross_loss",
    "perda bruta": "gross_loss",
    "prejuízo bruto": "gross_loss",
    "валовый убыток": "gross_loss",
    "profit factor": "profit_factor",
    "fator de lucro": "profit_factor",
    "прибыльность": "profit_factor",
    "expected payoff": "expected_payoff",
    "payoff esperado": "expected_payoff",
    "resultado esperado": "expected_payoff",
    "мат. ожидание": "expected_payoff",
    "recovery factor": "recovery_factor",
    "fator de recuperação": "recovery_factor",
    "fator de recuperacao": "recovery_factor",
    "фактор восстановления": "recovery_factor",
    "sharpe ratio": "sharpe",
    "sharpe": "sharpe",
    "índice de sharpe": "sharpe",
    "indice de sharpe": "sharpe",
    "коэффициент шарпа": "sharpe",
    "total trades": "total_trades",
    "total de negócios": "total_trades",
    "total de negocios": "total_trades",
    "всего сделок": "total_trades",
    "short trades (won %)": "short_trades_won_pct",
    "long trades (won %)": "long_trades_won_pct",
    "profit trades (% of total)": "profit_trades_pct",
    "loss trades (% of total)": "loss_trades_pct",
    "maximal drawdown": "max_drawdown",
    "rebaixamento máximo": "max_drawdown",
    "rebaixamento maximo": "max_drawdown",
    "drawdown máximo": "max_drawdown",
    "максимальная просадка": "max_drawdown",
    "balance drawdown maximal": "balance_drawdown",
    "equity drawdown maximal": "equity_drawdown",
    "initial deposit": "initial_deposit",
    "depósito inicial": "initial_deposit",
    "deposito inicial": "initial_deposit",
    "начальный депозит": "initial_deposit",
    "symbol": "symbol",
    "símbolo": "symbol",
    "simbolo": "symbol",
    "period": "period",
    "período": "period",
    "periodo": "period",
    "expert": "expert",
    "especialista": "expert",
}

_NUMERIC_SUMMARY = {
    "net_profit",
    "gross_profit",
    "gross_loss",
    "profit_factor",
    "expected_payoff",
    "recovery_factor",
    "sharpe",
    "sharpe_ratio",
    "total_trades",
    "max_drawdown",
    "max_drawdown_pct",
    "balance_drawdown",
    "balance_drawdown_max",
    "equity_drawdown",
    "equity_drawdown_max",
    "initial_deposit",
    "win_rate",
    "profit_trades",
    "loss_trades",
}

_MONEY_PCT_RE = re.compile(
    r"(?P<money>[-+]?\d[\d\s.\u00a0']*[,\.]?\d*)\s*\(\s*(?P<pct>[-+]?\d[\d\s.,]*)\s*%?\s*\)"
)
_COUNT_PCT_RE = re.compile(
    r"(?P<count>[-+]?\d[\d\s.,]*)\s*\(\s*(?P<pct>[-+]?\d[\d\s.,]*)\s*%?\s*\)"
)


def parse_number(value) -> float | None:
    """Parse tester numeric text into a Python float.

    Accepts ``1,234.56``, ``1.234,56``, ``1 234.56``, ``1234,56`` and
    already-numeric values. Returns None when the text is not a number.
    """
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace("\xa0", " ").replace("'", "")
    if not text or text in {"-", "n/a", "N/A"}:
        return None
    match = re.search(r"[-+]?\d[\d\s.,]*", text)
    if not match:
        return None
    token = match.group(0).replace(" ", "")
    if "," in token and "." in token:
        if token.rfind(",") > token.rfind("."):
            token = token.replace(".", "").replace(",", ".")
        else:
            token = token.replace(",", "")
    elif "," in token:
        left, right = token.rsplit(",", 1)
        if len(right) in (1, 2, 3) and left.replace(".", "").isdigit():
            token = left.replace(".", "") + "." + right
        else:
            token = token.replace(",", "")
    try:
        return float(token)
    except ValueError:
        return None


def _canon_label(label: str) -> str:
    return re.sub(r"\s+", " ", label.rstrip(":").strip().lower())


def _lookup_label(label: str) -> str | None:
    return _LABEL_MAP.get(_canon_label(label))


def _assign_metric(summary: dict, key: str, raw: str) -> None:
    text = (raw or "").strip()
    if key in {"symbol", "period", "expert"}:
        summary[key] = text
        return

    money_pct = _MONEY_PCT_RE.search(text)
    if money_pct and "drawdown" in key:
        summary[key] = parse_number(money_pct.group("money"))
        summary[f"{key}_pct"] = parse_number(money_pct.group("pct"))
        return

    count_pct = _COUNT_PCT_RE.search(text)
    if count_pct and key in {"profit_trades_pct", "loss_trades_pct", "short_trades_won_pct", "long_trades_won_pct"}:
        count = parse_number(count_pct.group("count"))
        pct = parse_number(count_pct.group("pct"))
        if key == "profit_trades_pct":
            summary["profit_trades"] = int(count) if count is not None else None
            summary["win_rate"] = pct
        elif key == "loss_trades_pct":
            summary["loss_trades"] = int(count) if count is not None else None
        summary[key] = pct
        return

    number = parse_number(text)
    if key in _NUMERIC_SUMMARY or number is not None and key not in {"symbol", "period", "expert"}:
        if key == "total_trades" and number is not None:
            summary[key] = int(number)
        else:
            summary[key] = number if number is not None else text
        return
    summary[key] = text


def _header_map(row: list[str]) -> dict[int, str] | None:
    normalized = [_canon_label(c) for c in row]
    joined = " ".join(normalized)
    interesting = {"time", "type", "deal", "order", "price", "profit", "volume", "size", "symbol"}
    if not any(cell in interesting or cell.startswith("buy") for cell in normalized) and "time" not in joined:
        return None
    mapping: dict[int, str] = {}
    aliases = {
        "time": "time",
        "hora": "time",
        "type": "type",
        "tipo": "type",
        "deal": "deal",
        "negócio": "deal",
        "negocio": "deal",
        "order": "order",
        "ordem": "order",
        "size": "volume",
        "volume": "volume",
        "price": "price",
        "preço": "price",
        "preco": "price",
        "profit": "profit",
        "lucro": "profit",
        "commission": "commission",
        "comissao": "commission",
        "comissão": "commission",
        "swap": "swap",
        "symbol": "symbol",
        "símbolo": "symbol",
        "comment": "comment",
        "direction": "entry",
        "entry": "entry",
        "ticket": "ticket",
    }
    for i, cell in enumerate(normalized):
        if cell in aliases:
            mapping[i] = aliases[cell]
    return mapping or None


def _row_to_trade(row: list[str], header: dict[int, str] | None) -> dict | None:
    if header:
        item = {"cols": row}
        for idx, key in header.items():
            if idx < len(row):
                item[key] = row[idx].strip()
        if any(item.get(k) for k in ("type", "deal", "order", "profit", "price")):
            return item
        return None
    if len(row) < 8:
        return None
    for cell in row[:4]:
        c = cell.lower().strip()
        if c.startswith("buy") or c.startswith("sell") or c in ("in", "out"):
            return {
                "cols": row,
                "time": row[0],
                "type": row[1],
                "order": row[2],
                "volume": row[3],
                "price": row[4] if len(row) > 4 else None,
                "profit": row[7] if len(row) > 7 else None,
            }
    return None


def parse_tester_report(html: str) -> dict:
    """Structured parse of an MT5 tester HTML report.

    Numeric summary fields are converted to int/float. Trade rows are mapped
    when a deals/orders table is present.
    """
    parser = _ReportParser()
    parser.feed(html)
    rows = parser.rows

    summary: dict = {}
    for row in rows:
        if len(row) >= 2:
            key = _lookup_label(row[0])
            if key:
                _assign_metric(summary, key, row[1])
        if len(row) >= 4:
            for i in range(0, len(row) - 1, 2):
                key = _lookup_label(row[i])
                if key:
                    _assign_metric(summary, key, row[i + 1])

    if summary.get("sharpe") is not None:
        summary["sharpe_ratio"] = summary["sharpe"]
    if summary.get("balance_drawdown") is not None:
        summary["balance_drawdown_max"] = summary["balance_drawdown"]
    if summary.get("equity_drawdown") is not None:
        summary["equity_drawdown_max"] = summary["equity_drawdown"]

    trade_rows: list[dict] = []
    header: dict[int, str] | None = None
    for row in rows:
        maybe_header = _header_map(row)
        if maybe_header and ("time" in maybe_header.values() or "type" in maybe_header.values()):
            header = maybe_header
            continue
        item = _row_to_trade(row, header)
        if item:
            trade_rows.append(item)

    return {
        "summary": summary,
        "trade_rows_detected": len(trade_rows),
        "trades_sample": trade_rows[:5],
        "trades": trade_rows,
    }


def iter_journal_lines(text: str) -> Iterator[dict]:
    """Parse MT5 journal lines: 'YYYY.MM.DD HH:MM:SS.mmm  Source\tMessage'."""
    pat_full = re.compile(r"^(?P<ts>\d{4}\.\d{2}\.\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?)\s+(?P<src>[^\t]+?)\t(?P<msg>.*)$")
    pat_simple = re.compile(r"^(?P<ts>\d{4}\.\d{2}\.\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?)\s+(?P<msg>.*)$")
    for line in text.splitlines():
        m = pat_full.match(line)
        if m:
            yield {"ts": m.group("ts"), "source": m.group("src").strip(), "message": m.group("msg")}
            continue
        m = pat_simple.match(line)
        if m:
            yield {"ts": m.group("ts"), "source": "", "message": m.group("msg")}
