"""Compile MQL via MetaEditor and return hashes of source + binary."""
from __future__ import annotations

import subprocess
from pathlib import Path

from ..parsers import parse_compile_log, read_text_auto
from ..paths import MT5Layout
from .hashes import sha256_file


def compiled_binary_path(source: Path, edition: str = "mt5") -> Path:
    ext = ".ex5" if edition != "mt4" else ".ex4"
    return source.with_suffix(ext)


def compile_source(
    layout: MT5Layout,
    source: str | Path,
    include: str | Path | None = None,
    log_file: str | Path | None = None,
    timeout_sec: int = 300,
) -> dict:
    src = Path(source)
    if not src.exists():
        return {"success": False, "ok": False, "error": f"source not found: {src}"}
    if not layout.metaeditor.exists():
        return {"success": False, "ok": False, "error": f"MetaEditor missing: {layout.metaeditor}"}

    inc = Path(include) if include else layout.mql_root
    log_path = Path(log_file) if log_file else src.with_suffix(".compile.log")
    log_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        str(layout.metaeditor),
        f"/compile:{src}",
        f"/include:{inc}",
        f"/log:{log_path}",
    ]
    stdout = ""
    stderr = ""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec)
        rc = proc.returncode
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
    except subprocess.TimeoutExpired as exc:
        rc = -1
        stderr = f"timeout after {timeout_sec}s: {exc}"

    parsed = {"errors": [], "warnings": [], "result_errors": None, "result_warnings": None, "ok": False}
    excerpt = ""
    if log_path.exists():
        try:
            text = read_text_auto(log_path)
            parsed = parse_compile_log(text)
            excerpt = "\n".join(text.splitlines()[-80:])
        except Exception as exc:
            excerpt = f"(log read failed: {exc})"

    binary = compiled_binary_path(src, layout.edition)
    binary_exists = binary.exists()
    success = bool(parsed["ok"] and binary_exists)
    source_sha = sha256_file(src)
    binary_sha = sha256_file(binary) if binary_exists else None

    return {
        "success": success,
        "ok": success,
        "returncode": rc,
        "cmd": " ".join(cmd),
        "log_path": str(log_path),
        "errors": parsed["errors"][:50],
        "warnings": parsed["warnings"][:50],
        "result_errors": parsed["result_errors"],
        "result_warnings": parsed["result_warnings"],
        "binary": str(binary) if binary_exists else None,
        "source_sha256": source_sha,
        "binary_sha256": binary_sha,
        "log_excerpt": excerpt,
        "stdout_tail": stdout[-2000:],
        "stderr_tail": stderr[-2000:],
    }
