"""Deterministic EA Registry for fast strategy discovery without loading MQL source."""
from __future__ import annotations

import json
import os
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .analysis import extract_inputs
from .parsers import read_text_auto
from .research.hashes import sha256_file


REGISTRY_VERSION = 1
_TAG_RE = re.compile(r"^\s*//\s*@tradelab\.([a-z][a-z0-9_]*)\s*:\s*(.*?)\s*$", re.MULTILINE)
_PROPERTY_VERSION_RE = re.compile(r'^\s*#property\s+version\s+"([^"]+)"', re.MULTILINE)
_INDICATORS = {
    "iRSI": "RSI",
    "iATR": "ATR",
    "iBands": "Bollinger Bands",
    "iMA": "Moving Average",
    "iMACD": "MACD",
    "iADX": "ADX",
    "iStochastic": "Stochastic",
}
_ALIASES = {
    "ifr": "rsi",
    "connorsrsi": "rsi",
    "rubber": "rubberband",
    "bandas": "bollinger",
    "band": "bollinger",
    "bands": "bollinger",
    "media": "ma",
    "moving": "ma",
    "average": "ma",
}
_STOPWORDS = {
    "a", "as", "com", "da", "de", "do", "dos", "e", "ea", "em", "estrategia", "filtro",
    "for", "of", "the", "strategy", "setup", "uma", "um", "with",
}


def default_experts_dir() -> Path:
    explicit = os.environ.get("TRADELAB_EXPERTS_DIR")
    if explicit:
        return Path(explicit)
    repo_candidate = Path(__file__).resolve().parents[2] / "experts"
    if repo_candidate.exists():
        return repo_candidate
    return Path(__file__).resolve().parent / "experts"


def _split_tag_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_scalar(value: str) -> Any:
    text = value.strip()
    if text.lower() in {"true", "false"}:
        return text.lower() == "true"
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    if re.fullmatch(r"-?\d+\.\d+", text):
        return float(text)
    return text


def _metadata_tags(text: str) -> dict[str, Any]:
    tags = {match.group(1): _parse_scalar(match.group(2)) for match in _TAG_RE.finditer(text)}
    for key in ("signal_timeframes", "bar_indices", "filters", "indicators", "parameters", "direction"):
        if key in tags:
            tags[key] = _split_tag_list(str(tags[key]))
    if "bar_indices" in tags:
        tags["bar_indices"] = [int(value) for value in tags["bar_indices"] if str(value) in {"0", "1"}]
    return tags


def _input_default(inputs: list[dict[str, str]], *names: str) -> Any:
    wanted = {name.lower() for name in names}
    for item in inputs:
        if item["name"].lower() not in wanted:
            continue
        raw = item["default"].strip().strip('"')
        return _parse_scalar(raw)
    return None


def _description(text: str, fallback: str) -> str:
    lines: list[str] = []
    for raw in text.splitlines()[:20]:
        match = re.match(r"\s*//\|\s*(.*?)\s*\|?\s*$", raw)
        if not match:
            continue
        value = match.group(1).strip(" |")
        if value and not value.lower().endswith(".mq5") and "+---" not in value:
            lines.append(value)
    return " ".join(lines[:2]) or fallback


def _detected_entry(path: Path, root: Path) -> dict[str, Any]:
    text = read_text_auto(path)
    inputs = extract_inputs(path)
    tags = _metadata_tags(text)
    indicators = sorted({label for call, label in _INDICATORS.items() if re.search(rf"\b{call}\s*\(", text)})
    timeframes = sorted(set(re.findall(r"\bPERIOD_(?:M\d+|H\d+|D1|W1|MN1|CURRENT)\b", text)))
    indexes = sorted({int(value) for value in re.findall(r"\[\s*([01])\s*\]", text)})
    version_match = _PROPERTY_VERSION_RE.search(text)
    magic = _input_default(inputs, "InpMagic", "MagicNumber", "Magic")
    risk_pct = _input_default(inputs, "InpRiskPct", "RiskPct")
    has_standard = "TradeLabEA.mqh" in text and "TradeLabOpenPosition" in text
    has_tp = bool(re.search(r"\b(?:TakeProfit|InpTP|InpTakeProfit|\btp\b)", text, re.IGNORECASE))
    has_trailing = bool(re.search(r"\btrailing", text, re.IGNORECASE))
    has_time_stop = bool(re.search(r"\b(?:MaxBars|TimeStop|BarsSinceEntry)\b", text, re.IGNORECASE))
    strategy = str(tags.get("strategy") or path.stem)

    entry: dict[str, Any] = {
        "name": str(tags.get("name") or path.stem),
        "path": path.relative_to(root).as_posix(),
        "setup": strategy,
        "description": str(tags.get("description") or _description(text, strategy)),
        "execution_timeframe": tags.get("execution_timeframe", "CURRENT"),
        "signal_timeframes": tags.get("signal_timeframes") or timeframes or ["CURRENT"],
        "bar_indices": tags.get("bar_indices") or indexes,
        "entry": tags.get("entry", "not documented"),
        "exit": tags.get("exit", "not documented"),
        "stop": tags.get("stop", "detected" if re.search(r"\b(?:StopLoss|\bsl\b|InpAtr)", text) else "not detected"),
        "take_profit": tags.get("take_profit", has_tp),
        "trailing": tags.get("trailing", has_trailing),
        "time_stop": tags.get("time_stop", has_time_stop),
        "position_sizing": tags.get(
            "position_sizing",
            "OrderCalcProfit risk-to-stop" if "OrderCalcProfit" in text else "legacy or not documented",
        ),
        "risk_pct_default": tags.get("risk_pct_default", risk_pct),
        "trade_mode": tags.get("trade_mode", "not documented"),
        "filters": tags.get("filters", []),
        "indicators": tags.get("indicators") or indicators,
        "parameters": tags.get("parameters") or [item["name"] for item in inputs],
        "magic_number": tags.get("magic_number", magic),
        "direction": tags.get("direction", []),
        "variant_of": tags.get("variant_of") or None,
        "version": version_match.group(1) if version_match else None,
        "standard_status": "standard" if has_standard else "legacy",
        "last_modified": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
        "compile_status": "binary_present" if path.with_suffix(".ex5").exists() else "unknown",
        "sha256": sha256_file(path),
    }
    return entry


def _load_overrides(root: Path, overrides_path: Path | None = None) -> dict[str, dict[str, Any]]:
    path = overrides_path or (root / "registry_overrides.json")
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("strategies", payload)
    if isinstance(records, list):
        return {str(item["path"]).replace("\\", "/"): item for item in records}
    return {str(key).replace("\\", "/"): value for key, value in records.items()}


def _normalize_text(value: str) -> str:
    raw = unicodedata.normalize("NFKD", value.lower()).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", raw).strip()


def _tokens(value: str) -> set[str]:
    out: set[str] = set()
    for token in _normalize_text(value).split():
        token = _ALIASES.get(token, token)
        if token not in _STOPWORDS and len(token) > 1:
            match = re.fullmatch(r"([a-z]+)(\d+)", token)
            if match:
                out.update(match.groups())
            else:
                out.add(token)
    return out


def _signature(entry: dict[str, Any]) -> dict[str, Any]:
    semantic = " ".join(
        str(value)
        for value in (
            entry.get("setup", ""),
            entry.get("entry", ""),
            entry.get("exit", ""),
            " ".join(map(str, entry.get("indicators", []))),
            " ".join(map(str, entry.get("filters", []))),
            " ".join(map(str, entry.get("direction", []))),
        )
    )
    return {
        "tokens": sorted(_tokens(semantic)),
        "execution_timeframe": entry.get("execution_timeframe"),
        "signal_timeframes": entry.get("signal_timeframes", []),
        "bar_indices": entry.get("bar_indices", []),
        "trade_mode": entry.get("trade_mode"),
    }


def build_registry(
    experts_dir: str | Path | None = None,
    *,
    overrides_path: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(experts_dir) if experts_dir else default_experts_dir()
    overrides = _load_overrides(root, Path(overrides_path) if overrides_path else None)
    entries: list[dict[str, Any]] = []
    if root.exists():
        for path in sorted(root.rglob("*.mq5")):
            if "templates" in {part.lower() for part in path.relative_to(root).parts}:
                continue
            entry = _detected_entry(path, root)
            override = overrides.get(entry["path"], {})
            immutable = {key: entry[key] for key in ("path", "last_modified", "sha256", "compile_status")}
            entry.update(override)
            entry.update(immutable)
            entry["logical_signature"] = _signature(entry)
            entries.append(entry)
    return {
        "schema_version": REGISTRY_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "experts_root": str(root.resolve()),
        "count": len(entries),
        "strategies": entries,
    }


def _summary_markdown(registry: dict[str, Any]) -> str:
    lines = [
        "# TradeLab EA Registry",
        "",
        "> Gerado por `refresh_ea_registry`; não editar manualmente. Metadados curados ficam em `registry_overrides.json`.",
        "",
        "| EA | Setup | TF execução | Barras | Modo | Status |",
        "|---|---|---|---|---|---|",
    ]
    for item in registry["strategies"]:
        bars = ", ".join(f"[{value}]" for value in item.get("bar_indices", [])) or "?"
        lines.append(
            f"| `{item['name']}.mq5` | {item.get('setup', '')} | "
            f"{item.get('execution_timeframe', '?')} | {bars} | "
            f"{item.get('trade_mode', '?')} | {item.get('standard_status', '?')} |"
        )
    lines.extend(["", f"Total: **{registry['count']}** EA(s).", ""])
    return "\n".join(lines)


def refresh_registry(
    experts_dir: str | Path | None = None,
    *,
    registry_path: str | Path | None = None,
    summary_path: str | Path | None = None,
    overrides_path: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(experts_dir) if experts_dir else default_experts_dir()
    registry = build_registry(root, overrides_path=overrides_path)
    target = Path(registry_path) if registry_path else (root / "registry.json")
    summary = Path(summary_path) if summary_path else (root / "REGISTRY.md")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary.write_text(_summary_markdown(registry), encoding="utf-8")
    return {
        "registry": registry,
        "registry_path": str(target),
        "summary_path": str(summary),
    }


def _registry_is_stale(registry: dict[str, Any], root: Path) -> bool:
    recorded = {item["path"]: item.get("sha256") for item in registry.get("strategies", [])}
    current_paths = [
        path for path in root.rglob("*.mq5")
        if "templates" not in {part.lower() for part in path.relative_to(root).parts}
    ] if root.exists() else []
    if {path.relative_to(root).as_posix() for path in current_paths} != set(recorded):
        return True
    return any(sha256_file(path) != recorded[path.relative_to(root).as_posix()] for path in current_paths)


def load_registry(
    experts_dir: str | Path | None = None,
    *,
    registry_path: str | Path | None = None,
    refresh_if_stale: bool = True,
) -> dict[str, Any]:
    root = Path(experts_dir) if experts_dir else default_experts_dir()
    target = Path(registry_path) if registry_path else (root / "registry.json")
    if not target.exists():
        return refresh_registry(root, registry_path=target)["registry"]
    registry = json.loads(target.read_text(encoding="utf-8"))
    if refresh_if_stale and _registry_is_stale(registry, root):
        return refresh_registry(root, registry_path=target)["registry"]
    return registry


def _match_score(query: str, entry: dict[str, Any]) -> float:
    query_normalized = _normalize_text(query).replace(" ", "")
    names = [entry.get("name", ""), entry.get("setup", "")]
    if any(query_normalized == _normalize_text(str(value)).replace(" ", "") for value in names):
        return 1.0
    query_tokens = _tokens(query)
    semantic_tokens = set(entry.get("logical_signature", {}).get("tokens", []))
    core_tokens = _tokens(" ".join(str(value) for value in names))
    semantic_tokens |= core_tokens
    if not query_tokens or not semantic_tokens:
        return 0.0

    semantic_overlap = len(query_tokens & semantic_tokens)
    semantic_score = (2.0 * semantic_overlap) / (len(query_tokens) + len(semantic_tokens))
    core_overlap = len(query_tokens & core_tokens)
    core_score = 0.0
    if core_tokens and core_overlap:
        query_coverage = core_overlap / len(query_tokens)
        core_coverage = core_overlap / len(core_tokens)
        core_score = 0.7 * query_coverage + 0.3 * core_coverage
    return round(max(semantic_score, core_score), 4)


def find_strategy(query: str, registry: dict[str, Any] | None = None, *, limit: int = 5) -> dict[str, Any]:
    if not query or not query.strip():
        raise ValueError("strategy query is required")
    catalog = registry or load_registry()
    ranked = sorted(
        ((item, _match_score(query, item)) for item in catalog.get("strategies", [])),
        key=lambda pair: (-pair[1], pair[0].get("name", "")),
    )
    candidates = [
        {
            "score": score,
            "name": item.get("name"),
            "path": item.get("path"),
            "setup": item.get("setup"),
            "description": item.get("description"),
            "entry": item.get("entry"),
            "exit": item.get("exit"),
            "stop": item.get("stop"),
            "position_sizing": item.get("position_sizing"),
            "execution_timeframe": item.get("execution_timeframe"),
            "signal_timeframes": item.get("signal_timeframes"),
            "bar_indices": item.get("bar_indices"),
            "parameters": item.get("parameters"),
            "risk_pct_default": item.get("risk_pct_default"),
            "trade_mode": item.get("trade_mode"),
            "filters": item.get("filters"),
            "indicators": item.get("indicators"),
            "magic_number": item.get("magic_number"),
            "standard_status": item.get("standard_status"),
            "variant_of": item.get("variant_of"),
        }
        for item, score in ranked[:limit]
        if score >= 0.2
    ]
    best = candidates[0] if candidates else None
    if best and best["score"] >= 0.9:
        scenario = "equivalent"
    elif best:
        scenario = "similar"
    else:
        scenario = "new"
    return {
        "query": query,
        "scenario": scenario,
        "best_match": best,
        "candidates": candidates,
        "instruction": {
            "equivalent": "reuse the existing EA; do not create a duplicate",
            "similar": "derive a clearly named variant from the closest EA",
            "new": "start from the TradeLab EA Standard template",
        }[scenario],
    }
