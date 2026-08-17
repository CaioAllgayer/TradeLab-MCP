"""TradeLab EA defaults, creation workflow, and lightweight policy checks."""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from .analysis import _strip_comments_strings, extract_inputs
from .parsers import read_text_auto


TRADELAB_DEFAULTS: dict[str, Any] = {
    "signal_bar": 1,
    "higher_timeframe_bar": 1,
    "allow_intrabar": False,
    "stop": {
        "required": True,
        "fallback_indicator": "ATR",
        "fallback_period": 20,
        "fallback_multiplier": 3.0,
        "fallback_bar": 1,
        "fixed_after_entry": True,
    },
    "position_sizing": {
        "method": "equity_risk_to_stop",
        "calculator": "OrderCalcProfit",
        "risk_pct": 2.0,
        "fallback": None,
    },
    "daytrade": {
        "cutoff_minutes": 60,
        "session_source": "SymbolInfoSessionTrade",
        "block_after_cutoff": True,
        "retry_forced_exit": True,
    },
    "take_profit": "only_when_setup_requires",
    "trailing_stop": "only_when_setup_requires",
    "breakeven": "only_when_setup_requires",
    "extra_filters": "only_when_requested",
}


CAPABILITIES: tuple[dict[str, str], ...] = (
    {"capability": "Sinal por barra", "default": "[1] (barra fechada)"},
    {"capability": "Intrabar", "default": "[0], somente quando explícito"},
    {"capability": "Multi-timeframe", "default": "Suportado"},
    {"capability": "Barra de timeframe maior", "default": "[1]; [0] opcional e explícito"},
    {"capability": "Swing/Position", "default": "Suportado"},
    {"capability": "Daytrade", "default": "Suportado"},
    {"capability": "Encerramento daytrade", "default": "60 min antes da sessão"},
    {"capability": "Stop", "default": "Obrigatório em toda entrada"},
    {"capability": "Stop sem regra original", "default": "3 x ATR(20)[1], fixo"},
    {"capability": "Position sizing", "default": "% do Equity até o SL"},
    {"capability": "RiskPct", "default": "2%"},
    {"capability": "Time Stop", "default": "Opcional"},
    {"capability": "Take Profit", "default": "Somente se o setup pedir"},
    {"capability": "Trailing/Breakeven", "default": "Somente se o setup pedir"},
    {"capability": "Filtros adicionais", "default": "Somente sob solicitação"},
    {"capability": "Registry", "default": "Consulta obrigatória antes da criação"},
)


def capabilities_summary() -> dict[str, Any]:
    """Return the compact menu used by agents before discussing a new EA."""
    return {
        "standard": "TradeLab EA Standard",
        "capabilities": [dict(item) for item in CAPABILITIES],
        "mandatory_sequence": [
            "identify_setup",
            "consult_registry",
            "report_equivalent_similar_or_new",
            "summarize_original_setup",
            "resolve_only_open_decisions",
            "state_applied_defaults",
            "generate_or_modify_ea",
            "validate_and_refresh_registry",
        ],
    }


def normalize_bar_index(value: int | str | None, *, default: int = 1) -> int:
    """Accept only the two officially supported signal-bar modes."""
    if value is None or value == "":
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("bar index must be 0 (intrabar) or 1 (closed bar)") from exc
    if parsed not in (0, 1):
        raise ValueError("bar index must be 0 (intrabar) or 1 (closed bar)")
    return parsed


def resolve_stop_policy(original_stop: str | None) -> dict[str, Any]:
    """Preserve an original stop, otherwise resolve the mandatory TradeLab fallback."""
    if original_stop and original_stop.strip():
        return {
            "source": "original_setup",
            "rule": original_stop.strip(),
            "fixed_after_entry": True,
            "required": True,
        }
    return {
        "source": "tradelab_fallback",
        "rule": "3 x ATR(20)[1]",
        "indicator": "ATR",
        "period": 20,
        "multiplier": 3.0,
        "bar": 1,
        "fixed_after_entry": True,
        "required": True,
    }


def normalize_risk_volume(
    equity: float,
    risk_pct: float,
    loss_per_lot: float,
    volume_min: float,
    volume_max: float,
    volume_step: float,
) -> float:
    """Pure mirror of the MQL sizing policy, useful for deterministic tests.

    ``loss_per_lot`` must come from ``OrderCalcProfit`` in a real EA. Returning
    zero is deliberate: the standard has no fixed-lot or notional fallback.
    """
    values = (equity, risk_pct, loss_per_lot, volume_min, volume_max, volume_step)
    if any(value <= 0 for value in values) or volume_max < volume_min:
        return 0.0
    raw = (equity * risk_pct / 100.0) / loss_per_lot
    if raw < volume_min:
        return 0.0
    steps = int((raw - volume_min + 1e-12) // volume_step)
    normalized = volume_min + steps * volume_step
    return round(min(normalized, volume_max), 8)


def bar_index_for_time(bar_opens_desc: Iterable[datetime], event_time: datetime) -> int:
    """Return the nearest containing/previous bar without exact-time equality."""
    for index, opened_at in enumerate(bar_opens_desc):
        if opened_at <= event_time:
            return index
    return -1


def daytrade_action(
    now: datetime,
    session_end: datetime | None,
    *,
    has_position: bool,
    cutoff_minutes: int = 60,
) -> dict[str, bool]:
    """Resolve the fail-closed daytrade action for a known exchange session."""
    if session_end is None or cutoff_minutes < 0:
        return {"block_entry": True, "force_close": has_position}
    cutoff = session_end - timedelta(minutes=cutoff_minutes)
    after_cutoff = now >= cutoff
    return {"block_entry": after_cutoff, "force_close": after_cutoff and has_position}


def build_creation_plan(
    setup: str,
    registry_match: dict[str, Any],
    *,
    execution_timeframe: str | None = None,
    signal_timeframe: str | None = None,
    signal_bar: int | str | None = None,
    higher_timeframe: str | None = None,
    higher_timeframe_bar: int | str | None = None,
    trade_mode: str | None = None,
    exit_rule: str | None = None,
    time_stop: str | None = None,
    original_stop: str | None = None,
    filters: list[str] | None = None,
) -> dict[str, Any]:
    """Build the mandatory, concise pre-generation decision record."""
    if not setup or not setup.strip():
        raise ValueError("setup is required")

    resolved_signal_bar = normalize_bar_index(signal_bar)
    resolved_higher_bar = normalize_bar_index(higher_timeframe_bar) if higher_timeframe else None
    mode = trade_mode.strip().upper() if trade_mode else None
    if mode in {"SWING/POSITION", "POSITION"}:
        mode = "SWING"
    if mode not in {None, "DAYTRADE", "SWING"}:
        raise ValueError("trade_mode must be DAYTRADE or SWING/POSITION")

    defaults_applied: list[str] = []
    notices: list[str] = []
    if signal_bar is None:
        defaults_applied.append("signal_bar=[1]")
    if resolved_signal_bar == 0:
        notices.append("Sinal intrabar [0] explicitamente solicitado; o valor muda durante a barra.")
    else:
        notices.append("Sinal [1] usa somente a barra fechada e executa na barra seguinte.")
    if higher_timeframe:
        if higher_timeframe_bar is None:
            defaults_applied.append(f"higher_timeframe_bar={higher_timeframe}[1]")
        if resolved_higher_bar == 0:
            notices.append(
                f"{higher_timeframe}[0] é barra em formação e muda intrabar; escolha explícita registrada."
            )
        else:
            notices.append(
                f"{higher_timeframe}[1] fica congelado até a próxima barra desse timeframe."
            )

    stop = resolve_stop_policy(original_stop)
    if stop["source"] == "tradelab_fallback":
        defaults_applied.append("stop=3 x ATR(20)[1], fixo")
    defaults_applied.append("RiskPct=2%; sizing pelo prejuízo de 1 lote via OrderCalcProfit")
    if mode == "DAYTRADE":
        defaults_applied.append("daytrade_cutoff=60 minutos antes do fim da sessão")

    unresolved: list[dict[str, str]] = []
    if not execution_timeframe:
        unresolved.append({"field": "execution_timeframe", "reason": "altera quando as ordens podem ser executadas"})
    if not mode:
        unresolved.append({"field": "trade_mode", "reason": "definir DAYTRADE ou SWING/POSITION"})
    if not exit_rule:
        unresolved.append({"field": "exit_rule", "reason": "não existe default TradeLab para saída do setup"})

    return {
        "setup": setup.strip(),
        "registry": registry_match,
        "interpretation": {
            "execution_timeframe": execution_timeframe,
            "signal_timeframe": signal_timeframe or execution_timeframe,
            "signal_bar": resolved_signal_bar,
            "higher_timeframe": higher_timeframe,
            "higher_timeframe_bar": resolved_higher_bar,
            "trade_mode": mode,
            "exit_rule": exit_rule,
            "time_stop": time_stop,
            "stop": stop,
            "filters": filters or [],
        },
        "defaults_applied": defaults_applied,
        "notices": notices,
        "unresolved_decisions": unresolved,
        "ready_to_implement": not unresolved,
        "generation_rule": (
            "reuse equivalent; derive a clearly named variant from a similar EA; "
            "otherwise start from the TradeLab template"
        ),
    }


def validate_ea_source(source: str | Path) -> dict[str, Any]:
    """Statically check whether an EA opts into the enforceable standard path.

    The check is intentionally deterministic and conservative. It does not claim
    to prove trading semantics; compilation and Strategy Tester validation remain
    separate gates.
    """
    path = Path(source)
    if not path.exists():
        return {"error": f"not found: {path}"}
    text = read_text_auto(path)
    cleaned = _strip_comments_strings(text)
    findings: list[dict[str, Any]] = []

    def add(rule: str, message: str, severity: str = "error") -> None:
        findings.append({"rule": rule, "severity": severity, "message": message})

    standard_include = bool(re.search(r'#include\s+[<"](?:[^>"]*[\\/])?TradeLabEA\.mqh[>"]', text))
    if not standard_include:
        add("missing_standard_include", "EA não inclui TradeLabEA.mqh")
    if "@tradelab.strategy:" not in text:
        add("missing_strategy_metadata", "EA não possui metadados @tradelab para o Registry", "warning")

    raw_trade = re.search(r"\btrade\s*\.\s*(?:Buy|Sell|PositionOpen)\s*\(", cleaned, re.IGNORECASE)
    standard_open = re.search(r"\bTradeLabOpenPosition\s*\(", cleaned)
    if raw_trade and not standard_open:
        add("raw_trade_entry", "Entrada usa CTrade diretamente e pode contornar o SL/sizing obrigatório")
    if not standard_open:
        add("missing_guarded_entry", "EA não usa TradeLabOpenPosition para validar SL e volume")

    if re.search(r"\biBarShift\s*\([^;\n]*,\s*true\s*\)", cleaned):
        add("exact_bar_shift", "iBarShift(..., exact=true) não é robusto para horários de negócios")

    if re.search(r"\b(?:InpLots|FixedLots|fixed_lot)\b", cleaned, re.IGNORECASE):
        add("fixed_lot_fallback", "Lote fixo não pertence ao position sizing padrão", "warning")
    if re.search(r"\bNormalizeVolume\s*\(\s*100(?:\.0)?\s*\)", cleaned):
        add("unsafe_volume_fallback", "Fallback de 100 lots é proibido")

    inputs = {item["name"]: item for item in extract_inputs(path)}
    risk = inputs.get("InpRiskPct")
    if risk is None:
        add("missing_risk_input", "InpRiskPct configurável não foi encontrado", "warning")

    errors = [item for item in findings if item["severity"] == "error"]
    return {
        "file": str(path),
        "standard": "TradeLab EA Standard",
        "compliant": not errors,
        "findings": findings,
        "error_count": len(errors),
        "warning_count": sum(item["severity"] == "warning" for item in findings),
    }
