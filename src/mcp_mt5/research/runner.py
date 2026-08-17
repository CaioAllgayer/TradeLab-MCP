"""Official Strategy Tester runner — one exclusive run_id, no 'latest file' lookup."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable

from ..analysis import extract_inputs, gen_tester_inputs
from ..parsers import parse_tester_report, read_text_auto
from ..paths import MT5Layout
from . import db as research_db
from .compile import compile_source
from .config import lab_expert_name, research_root
from .hashes import sha256_file
from .health import broker_server, file_sha256, win_file_version
from .ids import new_run_id
from .lab import publish_to_lab
from .lock import InstallLock, lock_for_layout
from .manifest import new_manifest, read_manifest, update_manifest, write_manifest
from .metrics import normalize_metrics
from .snapshot import resolve_strategy_path, snapshot_strategy
from .store import ResearchStore, utc_now
from .tester_ini import model_name, normalize_date, normalize_model, normalize_period, parse_ini_sections, write_tester_ini
from .trades import parse_trades_csv, trades_from_html_rows, write_trades_csv


LaunchFn = Callable[..., dict]
CompileFn = Callable[..., dict]


def common_files_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return Path()
    return Path(appdata) / "MetaQuotes" / "Terminal" / "Common" / "Files"


def launch_terminal(
    layout: MT5Layout,
    config: str | Path,
    timeout_sec: int = 1800,
    portable: bool = False,
) -> dict:
    cmd = [str(layout.terminal), f"/config:{config}"]
    if portable:
        cmd.append("/portable")
    try:
        proc = subprocess.run(cmd, timeout=timeout_sec)
        return {"returncode": proc.returncode, "timeout": False, "cmd": cmd}
    except subprocess.TimeoutExpired:
        try:
            subprocess.run(["taskkill", "/F", "/IM", layout.terminal.name], capture_output=True, text=True)
        except Exception:
            pass
        return {"returncode": -1, "timeout": True, "cmd": cmd}


def _snapshot_logs(folder: Path) -> dict[str, tuple[int, float]]:
    if not folder.exists():
        return {}
    out: dict[str, tuple[int, float]] = {}
    for path in folder.glob("*.log"):
        stat = path.stat()
        out[str(path)] = (stat.st_size, stat.st_mtime)
    return out


def _collect_tester_log(folder: Path, before: dict[str, tuple[int, float]], dest: Path) -> Path | None:
    if not folder.exists():
        return None
    chunks: list[str] = []
    after = list(folder.glob("*.log"))
    for path in sorted(after, key=lambda p: p.name):
        prev = before.get(str(path))
        text = read_text_auto(path)
        if prev is None:
            chunks.append(f"# {path.name}\n{text}")
            continue
        prev_size, _ = prev
        raw = path.read_bytes()
        if len(raw) > prev_size:
            tail = raw[prev_size:]
            if tail[:2] in (b"\xff\xfe", b"\xfe\xff"):
                piece = tail.decode("utf-16", errors="replace")
            else:
                piece = tail.decode("utf-8", errors="replace")
            chunks.append(f"# {path.name} (delta)\n{piece}")
    if not chunks:
        return None
    dest.write_text("\n".join(chunks), encoding="utf-8")
    return dest


def _find_report(report_dir: Path) -> Path | None:
    if not report_dir.exists():
        return None
    for name in ("report.htm", "report.html", "report.htm.htm", "report"):
        candidate = report_dir / name
        if candidate.exists() and candidate.is_file():
            return candidate
    htmls = sorted(report_dir.glob("report*.htm*"))
    return htmls[0] if htmls else None


def _copy_if_exists(source: Path, dest: Path) -> Path | None:
    if not source.exists() or not source.is_file():
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)
    return dest


def _inputs_for_ini(source: Path, user_inputs: dict | None, run_id: str) -> dict[str, object]:
    declared = {item["name"]: item["default"] for item in extract_inputs(source)}
    merged: dict[str, object] = {}
    if declared:
        block = gen_tester_inputs(source)
        for line in block.splitlines():
            if "=" in line and not line.startswith("["):
                name, rest = line.split("=", 1)
                merged[name] = rest.split("||", 1)[0]
    if "InpResearchRunId" in declared:
        merged["InpResearchRunId"] = run_id
    merged.update(user_inputs or {})
    return merged


def _fail(store: ResearchStore, run_id: str, stage: str, error: str, return_code: Any = None) -> dict:
    payload = {"stage": stage, "message": error, "return_code": return_code}
    try:
        store.write_json(run_id, "error.json", payload)
    except Exception:
        pass
    status = "timeout" if stage == "timeout" else "failed"
    try:
        update_manifest(
            store,
            run_id,
            status=status,
            stage=stage,
            error=payload,
            return_code=return_code,
            finished_at=utc_now(),
        )
    except Exception:
        pass
    manifest = store.read_json(run_id, "manifest.json") or {"run_id": run_id, "status": status}
    return {
        "run_id": run_id,
        "status": status,
        "stage": stage,
        "error": error,
        "return_code": return_code,
        "metrics": store.read_json(run_id, "metrics.json") or {},
        "artifacts": store.list_artifacts(run_id) if store.run_dir(run_id).exists() else {},
        "manifest": manifest,
    }


def execute_backtest(
    *,
    layout: MT5Layout,
    strategy: str,
    symbol: str,
    timeframe: str,
    from_date: str,
    to_date: str,
    inputs: dict | None = None,
    model: int | str = 4,
    deposit: float = 100000,
    currency: str = "BRL",
    leverage: str | int = "1:100",
    timeout_sec: int = 1800,
    portable: bool = False,
    store: ResearchStore | None = None,
    compile_fn: CompileFn | None = None,
    launch_fn: LaunchFn | None = None,
    lock: InstallLock | None = None,
    run_id: str | None = None,
) -> dict:
    store = store or ResearchStore(research_root())
    try:
        source = resolve_strategy_path(strategy)
    except FileNotFoundError as exc:
        return {"run_id": None, "status": "failed", "stage": "input", "error": str(exc), "metrics": {}, "artifacts": {}}

    try:
        period = normalize_period(timeframe)
        model_i = normalize_model(model)
        from_s = normalize_date(from_date)
        to_s = normalize_date(to_date)
    except ValueError as exc:
        return {"run_id": None, "status": "failed", "stage": "input", "error": str(exc), "metrics": {}, "artifacts": {}}

    rid = run_id or new_run_id()
    run_dir = store.create_run(rid)
    test_cfg = {
        "symbol": symbol,
        "period": period,
        "from": from_s,
        "to": to_s,
        "model": model_i,
        "model_name": model_name(model_i),
        "deposit": float(deposit),
        "currency": currency,
        "leverage": str(leverage),
    }
    manifest = new_manifest(rid, source.stem, test_cfg)
    manifest["run_dir"] = str(run_dir)
    manifest["environment"] = {
        "terminal_build": win_file_version(layout.terminal),
        "terminal_hash": layout.terminal_hash,
        "terminal_sha256": file_sha256(layout.terminal),
        "broker_server": broker_server(layout),
        "mt5_install": str(layout.install),
    }
    write_manifest(store, rid, manifest)

    held_lock = lock or lock_for_layout(layout.data)
    we_locked = lock is None
    try:
        if we_locked:
            held_lock.acquire(timeout=0)
    except Exception as exc:
        return _fail(store, rid, "lock", str(exc))

    try:
        update_manifest(store, rid, status="compiling", stage="snapshot")
        snap = snapshot_strategy(source, run_dir, mql_root=layout.mql_root)
        snapped = Path(snap["strategy_mq5"])
        update_manifest(
            store,
            rid,
            strategy={
                "name": source.stem,
                "source_sha256": snap["source_sha256"],
                "includes": [
                    {"src": item.get("src"), "sha256": item.get("sha256"), "snap": item.get("snap")}
                    for item in snap["includes"]
                ],
            },
        )

        compile_log = run_dir / "compile.log"
        compile_impl = compile_fn or (
            lambda: compile_source(layout, snapped, include=layout.mql_root, log_file=compile_log)
        )
        compiled = compile_impl() if compile_fn is None else compile_fn(
            layout, snapped, layout.mql_root, compile_log
        )
        if not compiled.get("success", compiled.get("ok")):
            errors = compiled.get("errors") or []
            msg = compiled.get("error") or compiled.get("log_excerpt") or "compile failed"
            if errors:
                msg = errors[0].get("message", msg)
            return _fail(store, rid, "compiling", str(msg), compiled.get("returncode"))

        binary = Path(compiled["binary"]) if compiled.get("binary") else (run_dir / "strategy.ex5")
        if not binary.exists():
            return _fail(store, rid, "compiling", f"binary missing: {binary}")
        if binary.resolve() != (run_dir / "strategy.ex5").resolve():
            shutil.copy2(binary, run_dir / "strategy.ex5")
            binary = run_dir / "strategy.ex5"

        binary_sha = compiled.get("binary_sha256") or sha256_file(binary)
        update_manifest(store, rid, strategy={"binary_sha256": binary_sha, "source_sha256": compiled.get("source_sha256") or snap["source_sha256"]})

        extra = []
        for item in snap.get("includes") or []:
            rel = item.get("snap")
            if not rel or item.get("std_include"):
                continue
            extra.append((run_dir / rel, rel))
        published = publish_to_lab(
            layout,
            name=source.stem,
            source=snapped,
            binary=binary,
            extra_files=extra,
        )
        expert_rel = published["expert"] or lab_expert_name(source.stem)

        tester_rel = Path("Tester") / "TradeLab MCP" / rid
        tester_abs = layout.data / tester_rel
        tester_abs.mkdir(parents=True, exist_ok=True)
        report_key = str(tester_rel / "report")

        ini_inputs = _inputs_for_ini(snapped, inputs, rid)
        ini_path = run_dir / "tester.ini"
        write_tester_ini(
            ini_path,
            expert=expert_rel,
            symbol=symbol,
            period=period,
            from_date=from_s,
            to_date=to_s,
            model=model_i,
            deposit=deposit,
            currency=currency,
            leverage=leverage,
            report=report_key,
            inputs=ini_inputs,
        )
        update_manifest(
            store,
            rid,
            files={"config_sha256": sha256_file(ini_path)},
            strategy={"lab_expert": expert_rel, "lab_dir": published["dir"]},
        )

        log_before = _snapshot_logs(layout.tester_logs)
        update_manifest(store, rid, status="running", stage="tester")
        launcher = launch_fn or launch_terminal
        launched = launcher(layout, ini_path, timeout_sec, portable)
        return_code = launched.get("returncode")

        _collect_tester_log(layout.tester_logs, log_before, run_dir / "tester.log")

        if launched.get("timeout"):
            return _fail(store, rid, "timeout", f"terminal timeout after {timeout_sec}s", return_code)

        report_src = _find_report(tester_abs)
        if report_src is None:
            found = [p.name for p in tester_abs.iterdir()] if tester_abs.exists() else []
            return _fail(
                store,
                rid,
                "report",
                f"no report in {tester_abs} (found: {found or 'empty'})",
                return_code,
            )
        report_dest = run_dir / "report.htm"
        shutil.copy2(report_src, report_dest)
        png = report_src.with_suffix(".png")
        if png.exists():
            shutil.copy2(png, run_dir / "report.png")

        html = read_text_auto(report_dest)
        parsed = parse_tester_report(html)
        summary = parsed.get("summary") or {}

        trades = _collect_trades(layout, rid, run_dir, parsed, symbol)
        metrics = normalize_metrics(summary, trades)
        store.write_json(rid, "metrics.json", metrics)
        if trades:
            write_trades_csv(run_dir / "trades.csv", trades)

        update_manifest(
            store,
            rid,
            status="completed",
            stage="completed",
            return_code=return_code,
            finished_at=utc_now(),
            files={
                "config_sha256": sha256_file(ini_path),
                "report": "report.htm",
                "trades": "trades.csv" if (run_dir / "trades.csv").exists() else None,
                "tester_log": "tester.log" if (run_dir / "tester.log").exists() else None,
            },
        )
        final = read_manifest(store, rid)
        try:
            research_db.upsert_run(final, metrics=metrics, trades=trades, db_file=store.root / "research.db")
        except Exception:
            pass
        return {
            "run_id": rid,
            "status": "completed",
            "symbol": symbol,
            "period": period,
            "model": model_name(model_i),
            "metrics": metrics,
            "artifacts": store.list_artifacts(rid),
            "manifest": final,
        }
    except Exception as exc:
        return _fail(store, rid, "running", str(exc))
    finally:
        if we_locked:
            held_lock.release()


def _collect_trades(layout: MT5Layout, run_id: str, run_dir: Path, parsed: dict, symbol: str) -> list[dict]:
    candidates = [
        common_files_dir() / f"tradelab_{run_id}.csv",
        layout.files_dir / f"tradelab_{run_id}.csv",
        run_dir / "ea_trades.csv",
    ]
    for path in candidates:
        if path.exists():
            copied = run_dir / "ea_trades.csv"
            if path.resolve() != copied.resolve():
                shutil.copy2(path, copied)
            return parse_trades_csv(read_text_auto(copied))
    if parsed.get("closed_trades"):
        return parsed["closed_trades"]
    html_trades = parsed.get("trades") or []
    return trades_from_html_rows(html_trades, symbol=symbol)


def get_run(store: ResearchStore, run_id: str) -> dict:
    try:
        folder = store.require_run(run_id)
    except (FileNotFoundError, ValueError) as exc:
        return {"error": str(exc), "run_id": run_id}
    manifest = store.read_json(run_id, "manifest.json") or {}
    metrics = store.read_json(run_id, "metrics.json") or {}
    error = store.read_json(run_id, "error.json")
    tester = None
    ini = folder / "tester.ini"
    if ini.exists():
        tester = parse_ini_sections(ini)
    return {
        "run_id": run_id,
        "status": manifest.get("status"),
        "manifest": manifest,
        "config": tester,
        "metrics": metrics,
        "files": store.list_artifacts(run_id),
        "error": error,
    }


def get_trades(store: ResearchStore, run_id: str) -> dict:
    try:
        folder = store.require_run(run_id)
    except (FileNotFoundError, ValueError) as exc:
        return {"error": str(exc), "run_id": run_id, "trades": []}
    csv_path = folder / "trades.csv"
    trades = parse_trades_csv(read_text_auto(csv_path)) if csv_path.exists() else []
    return {"run_id": run_id, "count": len(trades), "trades": trades}
