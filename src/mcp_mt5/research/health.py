"""Inspect the local MetaTrader installation used as the research engine."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from ..parsers import read_text_auto
from ..paths import MT5Layout
from .config import LAB_EXPERTS_SUBDIR, lab_experts_dir


def file_sha256(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def win_file_version(path: Path) -> str | None:
    if os.name != "nt" or not path.exists():
        return None
    try:
        import ctypes
        from ctypes import wintypes

        size = ctypes.windll.version.GetFileVersionInfoSizeW(str(path), None)
        if not size:
            return None
        buf = ctypes.create_string_buffer(size)
        if not ctypes.windll.version.GetFileVersionInfoW(str(path), 0, size, buf):
            return None
        lptr = ctypes.c_void_p()
        llen = wintypes.UINT()
        if not ctypes.windll.version.VerQueryValueW(buf, r"\StringFileInfo\040904b0\FileVersion", ctypes.byref(lptr), ctypes.byref(llen)):
            if not ctypes.windll.version.VerQueryValueW(buf, r"\StringFileInfo\040904B0\ProductVersion", ctypes.byref(lptr), ctypes.byref(llen)):
                return _fixed_file_info(buf)
        return ctypes.wstring_at(lptr.value, max(llen.value - 1, 0)).strip() or None
    except Exception:
        return None


def _fixed_file_info(buf) -> str | None:
    try:
        import ctypes
        from ctypes import wintypes

        class VS_FIXEDFILEINFO(ctypes.Structure):
            _fields_ = [
                ("dwSignature", wintypes.DWORD),
                ("dwStrucVersion", wintypes.DWORD),
                ("dwFileVersionMS", wintypes.DWORD),
                ("dwFileVersionLS", wintypes.DWORD),
            ]

        lptr = ctypes.c_void_p()
        llen = wintypes.UINT()
        if not ctypes.windll.version.VerQueryValueW(buf, "\\", ctypes.byref(lptr), ctypes.byref(llen)):
            return None
        info = ctypes.cast(lptr, ctypes.POINTER(VS_FIXEDFILEINFO)).contents
        major = info.dwFileVersionMS >> 16
        minor = info.dwFileVersionMS & 0xFFFF
        build = info.dwFileVersionLS >> 16
        rev = info.dwFileVersionLS & 0xFFFF
        return f"{major}.{minor}.{build}.{rev}"
    except Exception:
        return None


def _ini_value(path: Path, key: str) -> str | None:
    if not path.exists():
        return None
    try:
        text = read_text_auto(path)
    except Exception:
        return None
    needle = key.lower() + "="
    for raw in text.splitlines():
        line = raw.strip()
        if line.lower().startswith(needle):
            return line.split("=", 1)[1].strip() or None
    return None


def broker_server(layout: MT5Layout) -> str | None:
    for rel in ("config/common.ini", "config/terminal.ini", "config/settings.ini"):
        value = _ini_value(layout.data / rel, "Server")
        if value:
            return value
        value = _ini_value(layout.data / rel, "LastServer")
        if value:
            return value
    return None


def health_check(layout: MT5Layout) -> dict:
    issues = layout.issues()
    tester_ok = layout.tester_dir.exists()
    if not tester_ok:
        issues.append(f"missing Tester dir: {layout.tester_dir}")
    data_ok = layout.data.exists()
    if not data_ok:
        issues.append(f"missing data directory: {layout.data}")

    terminal_ver = win_file_version(layout.terminal)
    editor_ver = win_file_version(layout.metaeditor)
    terminal_sha = file_sha256(layout.terminal)

    can_compile = layout.metaeditor.exists() and layout.metaeditor.is_file()
    can_test = layout.terminal.exists() and layout.terminal.is_file() and tester_ok

    return {
        "ok": len(issues) == 0,
        "edition": layout.edition,
        "install": str(layout.install),
        "data": str(layout.data),
        "terminal_hash": layout.terminal_hash,
        "terminal_build": terminal_ver,
        "terminal_sha256": terminal_sha,
        "broker_server": broker_server(layout),
        "metaeditor": {
            "path": str(layout.metaeditor),
            "exists": layout.metaeditor.exists(),
            "version": editor_ver,
        },
        "terminal": {
            "path": str(layout.terminal),
            "exists": layout.terminal.exists(),
            "version": terminal_ver,
            "sha256": terminal_sha,
        },
        "experts": {"path": str(layout.experts_dir), "exists": layout.experts_dir.exists()},
        "lab_experts": {
            "subdir": LAB_EXPERTS_SUBDIR,
            "path": str(lab_experts_dir(layout)),
            "exists": lab_experts_dir(layout).exists(),
        },
        "tester": {"path": str(layout.tester_dir), "exists": tester_ok},
        "mql_root": str(layout.mql_root),
        "include_dir": str(layout.include_dir),
        "can_compile": can_compile,
        "can_run_tester": can_test,
        "issues": issues,
    }
