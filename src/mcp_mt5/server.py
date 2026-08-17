"""Trading Research MCP — MetaTrader 5 Strategy Tester is the execution engine."""
from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

from . import smoke as _smoke
from .lint import validate_tester_ini as _validate_tester_ini
from .parsers import iter_journal_lines, read_text_auto
from .paths import MT5Layout, detect_layout, find_terminal_for_install, list_terminal_origins
from .research.batch import run_batch as _run_batch
from .research.compare import compare_runs as _compare_runs
from .research.compile import compile_source
from .research.health import health_check
from .research.lab import publish_to_lab
from .research.runner import execute_backtest, get_run as _get_run, get_trades as _get_trades
from .research.store import ResearchStore
from .research.walk_forward import run_walk_forward as _run_walk_forward

mcp = FastMCP("mt5")

_layout_cache: Optional[MT5Layout] = None


def layout() -> MT5Layout:
    global _layout_cache
    if _layout_cache is None:
        _layout_cache = detect_layout()
    return _layout_cache


def store() -> ResearchStore:
    return ResearchStore()


def _workdir(source: Path) -> Path:
    explicit = os.environ.get("MT5_WORK_DIR")
    d = Path(explicit) if explicit else (source.parent / ".mt5tmp")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _backtest(**kwargs) -> dict:
    return execute_backtest(layout=layout(), store=store(), **kwargs)


@mcp.tool()
def health() -> dict:
    """Verify MT5 install, MetaEditor, terminal, data dir, Experts, Tester, and build."""
    return health_check(layout())


def env_info() -> dict:
    """Compatibility wrapper used by tests and older clients."""
    info = health()
    return {
        "edition": info["edition"],
        "install": info["install"],
        "data": info["data"],
        "terminal_hash": info["terminal_hash"],
        "metaeditor": info["metaeditor"]["path"],
        "terminal": info["terminal"]["path"],
        "mql_root": info["mql_root"],
        "include_dir": info["include_dir"],
        "experts_dir": info["experts"]["path"],
        "files_dir": str(layout().files_dir),
        "logs_dir": str(layout().logs_dir),
        "tester_dir": info["tester"]["path"],
        "issues": info["issues"],
    }


@mcp.tool()
def list_terminals() -> dict:
    """Enumerate MetaTrader terminal data folders under %APPDATA%\\MetaQuotes\\Terminal."""
    terminals = list_terminal_origins()
    return {"count": len(terminals), "terminals": terminals}


@mcp.tool()
def compile(
    source: str,
    include: Optional[str] = None,
    log_file: Optional[str] = None,
    timeout_sec: int = 300,
    publish: bool = True,
) -> dict:
    """Compile a .mq5/.mq4 source via MetaEditor and publish it to Experts/TradeLab MCP."""
    src = Path(source)
    log_path = Path(log_file) if log_file else (_workdir(src) / f"{src.stem}.compile.log" if src.exists() else None)
    result = compile_source(layout(), src, include=include, log_file=log_path, timeout_sec=timeout_sec)
    if publish and result.get("success") and src.suffix.lower() in {".mq5", ".mq4"}:
        result["published"] = publish_to_lab(
            layout(),
            name=src.stem,
            source=src,
            binary=result.get("binary"),
        )
    return result


@mcp.tool()
def run_backtest(
    strategy: str,
    symbol: str,
    timeframe: str,
    from_date: str,
    to_date: str,
    inputs: Optional[dict] = None,
    model: int = 4,
    deposit: float = 100000,
    currency: str = "BRL",
    leverage: str = "1:100",
    timeout_sec: int = 1800,
) -> dict:
    """Run one official MT5 Strategy Tester backtest and store it under a unique run_id."""
    return _backtest(
        strategy=strategy,
        symbol=symbol,
        timeframe=timeframe,
        from_date=from_date,
        to_date=to_date,
        inputs=inputs or {},
        model=model,
        deposit=deposit,
        currency=currency,
        leverage=leverage,
        timeout_sec=timeout_sec,
    )


@mcp.tool()
def run_batch(
    strategy: str,
    symbols: list[str],
    period: str,
    from_date: str,
    to_date: str,
    inputs: Optional[dict] = None,
    model: int = 4,
    deposit: float = 100000,
    currency: str = "BRL",
    leverage: str = "1:100",
    timeout_sec: int = 1800,
) -> dict:
    """Run the same strategy sequentially on each symbol. Each asset gets its own run_id."""
    return _run_batch(
        _backtest,
        strategy=strategy,
        symbols=symbols,
        period=period,
        from_date=from_date,
        to_date=to_date,
        inputs=inputs,
        model=model,
        deposit=deposit,
        currency=currency,
        leverage=leverage,
        timeout_sec=timeout_sec,
    )


@mcp.tool()
def get_run(run_id: str) -> dict:
    """Load manifest, config, metrics, files, and errors for an existing run_id."""
    return _get_run(store(), run_id)


@mcp.tool()
def get_trades(run_id: str) -> dict:
    """Return normalized trades for a run_id."""
    return _get_trades(store(), run_id)


@mcp.tool()
def compare_runs(run_ids: list[str]) -> dict:
    """Diff stored metrics of two or more runs. Never looks up the latest HTML report."""
    return _compare_runs(store(), run_ids)


@mcp.tool()
def walk_forward(
    strategy: str,
    symbol: str,
    timeframe: str,
    from_date: str,
    to_date: str,
    is_days: int,
    oos_days: int,
    step_days: Optional[int] = None,
    inputs: Optional[dict] = None,
    model: int = 4,
    deposit: float = 100000,
    currency: str = "BRL",
    leverage: str = "1:100",
    timeout_sec: int = 1800,
) -> dict:
    """Walk-forward as a sequence of official tester runs (IS/OOS windows)."""
    return _run_walk_forward(
        store=store(),
        backtest_fn=_backtest,
        strategy=strategy,
        symbol=symbol,
        timeframe=timeframe,
        from_date=from_date,
        to_date=to_date,
        is_days=is_days,
        oos_days=oos_days,
        step_days=step_days,
        inputs=inputs,
        model=model,
        deposit=deposit,
        currency=currency,
        leverage=leverage,
        timeout_sec=timeout_sec,
    )


@mcp.tool()
def smoke_test(
    source: str,
    expert_name: Optional[str] = None,
    symbol: str = "EURUSD",
    period: str = "M15",
    days: int = 1,
    timeout_sec: int = 600,
    model: int = 2,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    deposit: float = 10000,
    currency: str = "USD",
) -> dict:
    """Compile, deploy, run a short official tester pass, and scan the journal."""
    return _smoke.run_smoke(
        layout(),
        source,
        expert_name=expert_name,
        symbol=symbol,
        period=period,
        days=days,
        timeout_sec=timeout_sec,
        model=model,
        from_date=from_date,
        to_date=to_date,
        deposit=deposit,
        currency=currency,
    )


@mcp.tool()
def validate_tester_ini(config: str, source: Optional[str] = None) -> dict:
    """Sanity-check a tester.ini against official MT5 formats (including Leverage=1:100)."""
    return _validate_tester_ini(config, source=source)


@mcp.tool()
def select_terminal(
    origin: Optional[str] = None,
    hash: Optional[str] = None,
    install: Optional[str] = None,
    edition: str = "mt5",
) -> dict:
    """Switch the active terminal data folder for this session."""
    global _layout_cache
    target_install = Path(install) if install else None
    target_hash = hash
    if origin:
        for item in list_terminal_origins():
            if item["origin"] and item["origin"].strip().lower() == origin.strip().lower():
                target_hash = item["hash"]
                break
        if not target_hash:
            return {"error": f"no terminal data folder found for origin: {origin}"}

    if target_install and not target_hash:
        found = find_terminal_for_install(target_install)
        if found:
            target_hash, _ = found

    layout_kwargs: dict = {"edition": edition}
    if target_install:
        layout_kwargs["install"] = str(target_install)
    if target_hash:
        layout_kwargs["terminal_hash"] = target_hash

    new_layout = detect_layout(**layout_kwargs)
    _layout_cache = new_layout
    return {
        "active_install": str(new_layout.install),
        "active_data": str(new_layout.data),
        "active_hash": new_layout.terminal_hash,
        "edition": new_layout.edition,
        "issues": new_layout.issues(),
    }


@mcp.tool()
def kill_terminal() -> dict:
    """Force-kill terminal processes for the configured edition."""
    target = layout().terminal.name
    try:
        proc = subprocess.run(["taskkill", "/F", "/IM", target], capture_output=True, text=True)
        return {"returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}
    except Exception as exc:
        return {"error": str(exc)}


def deploy_ea(source_ex: str, name: Optional[str] = None) -> dict:
    src = Path(source_ex)
    if not src.exists():
        return {"error": f"binary not found: {src}"}
    if not layout().experts_dir.exists():
        return {"error": f"Experts dir missing: {layout().experts_dir}"}
    target = layout().experts_dir / (name or src.name)
    shutil.copy2(src, target)
    return {"copied_to": str(target), "size": target.stat().st_size}


def install_include(source: str, target_name: Optional[str] = None) -> dict:
    src = Path(source)
    if not src.exists():
        return {"error": f"source not found: {src}"}
    layout().include_dir.mkdir(parents=True, exist_ok=True)
    target = layout().include_dir / (target_name or src.name)
    shutil.copy2(src, target)
    return {"copied_to": str(target)}


def list_experts(pattern: str = "*.ex5", recurse: bool = True) -> dict:
    if not layout().experts_dir.exists():
        return {"error": f"Experts dir missing: {layout().experts_dir}"}
    glob = layout().experts_dir.rglob if recurse else layout().experts_dir.glob
    files = [
        {
            "name": p.name,
            "rel": str(p.relative_to(layout().experts_dir)),
            "size": p.stat().st_size,
            "mtime": datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
        }
        for p in glob(pattern)
    ]
    return {"count": len(files), "files": files[:200]}


def tail_log(mode: str = "live", lines: int = 100, date: Optional[str] = None, structured: bool = False) -> dict:
    L = layout()
    if mode == "live":
        path = L.files_dir / "LiveLog.txt"
    elif mode == "journal":
        path = L.logs_dir / f"{date or datetime.now().strftime('%Y%m%d')}.log"
    elif mode == "tester":
        if not L.tester_logs.exists():
            return {"error": f"tester logs dir missing: {L.tester_logs}"}
        files = sorted(L.tester_logs.glob("*.log"), key=lambda p: p.name)
        if not files:
            return {"error": "no tester logs"}
        path = files[-1]
    else:
        return {"error": f"unknown mode: {mode}"}
    if not path.exists():
        return {"error": f"log not found: {path}", "path": str(path)}
    text = read_text_auto(path)
    tail_lines = text.splitlines()[-lines:]
    out: dict = {"path": str(path), "line_count": len(tail_lines)}
    if structured and mode in ("journal", "tester"):
        out["records"] = list(iter_journal_lines("\n".join(tail_lines)))
    else:
        out["content"] = "\n".join(tail_lines)
    return out


def patch_tester_ini(config: str, updates: dict) -> dict:
    p = Path(config)
    if not p.exists():
        return {"error": f"config not found: {p}"}
    lines = p.read_text(encoding="utf-8").splitlines()
    applied: list[str] = []
    skipped: list[str] = []
    section_keys: dict[str, dict[str, str]] = {}
    for key, value in updates.items():
        if "." not in key:
            skipped.append(key)
            continue
        sec, name = key.split(".", 1)
        section_keys.setdefault(sec, {})[name] = str(value)

    out: list[str] = []
    current_section = ""
    pending = {s: dict(d) for s, d in section_keys.items()}
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if current_section in pending:
                for name, value in pending[current_section].items():
                    out.append(f"{name}={value}")
                    applied.append(f"{current_section}.{name}")
                pending[current_section] = {}
            current_section = stripped[1:-1]
            out.append(line)
            continue
        parts = stripped.split("=", 1) if "=" in stripped and not stripped.startswith(";") else None
        if parts and current_section in pending:
            name = parts[0].strip()
            if name in pending[current_section]:
                value = pending[current_section].pop(name)
                out.append(f"{name}={value}")
                applied.append(f"{current_section}.{name}")
                continue
        out.append(line)

    if current_section in pending:
        for name, value in pending[current_section].items():
            out.append(f"{name}={value}")
            applied.append(f"{current_section}.{name}")
        pending[current_section] = {}

    for sec, kv in pending.items():
        if not kv:
            continue
        out.append("")
        out.append(f"[{sec}]")
        for name, value in kv.items():
            out.append(f"{name}={value}")
            applied.append(f"{sec}.{name}")

    p.write_text("\n".join(out) + "\n", encoding="utf-8")
    return {"applied": applied, "skipped": skipped, "config": str(p)}


@mcp.resource("mt5://livelog")
def livelog_resource() -> str:
    path = layout().files_dir / "LiveLog.txt"
    if not path.exists():
        return f"(no LiveLog at {path})"
    return "\n".join(read_text_auto(path).splitlines()[-500:])


@mcp.resource("mt5://journal")
def journal_resource() -> str:
    today = datetime.now().strftime("%Y%m%d")
    path = layout().logs_dir / f"{today}.log"
    if not path.exists():
        return f"(no journal for {today} at {path})"
    return "\n".join(read_text_auto(path).splitlines()[-500:])


@mcp.resource("mt5://tester-log")
def tester_log_resource() -> str:
    if not layout().tester_logs.exists():
        return "(no tester log dir)"
    files = sorted(layout().tester_logs.glob("*.log"), key=lambda p: p.name)
    if not files:
        return "(no tester logs)"
    return f"# {files[-1].name}\n" + "\n".join(read_text_auto(files[-1]).splitlines()[-500:])


def main():
    mcp.run()


if __name__ == "__main__":
    main()
