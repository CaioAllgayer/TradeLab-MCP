"""Publish automatic test EAs into the terminal Experts/TradeLab MCP folder."""
from __future__ import annotations

import shutil
from pathlib import Path

from ..paths import MT5Layout
from .config import LAB_EXPERTS_SUBDIR, lab_expert_name, lab_experts_dir

_README = """TradeLab MCP
============

Pasta padrao do TradeLab-MCP no terminal.

Todo EA de teste automatico e publicado aqui (fonte + .ex5 + includes locais).
No Strategy Tester o expert aparece como: TradeLab MCP\\<Nome>

O EA-base do laboratorio ainda nao esta nesta pasta. Ele sera padronizado
depois (CTrade, ArraySetAsSeries, uma posicao, sem simulacao de fill).
"""


def ensure_lab_experts(layout: MT5Layout) -> Path:
    dest = lab_experts_dir(layout)
    dest.mkdir(parents=True, exist_ok=True)
    readme = dest / "README.txt"
    if not readme.exists():
        readme.write_text(_README, encoding="utf-8")
    return dest


def publish_to_lab(
    layout: MT5Layout,
    *,
    name: str,
    source: str | Path,
    binary: str | Path | None = None,
    extra_files: list[tuple[str | Path, str]] | None = None,
) -> dict:
    """Copy EA source/binary/includes into Experts/TradeLab MCP/<name>.

    ``extra_files`` is a list of (absolute source, path relative to the lab folder).
    """
    dest = ensure_lab_experts(layout)
    src = Path(source)
    dest_src = dest / f"{name}{src.suffix.lower() or '.mq5'}"
    shutil.copy2(src, dest_src)

    dest_bin = None
    if binary:
        bin_path = Path(binary)
        if bin_path.exists():
            dest_bin = dest / f"{name}{bin_path.suffix}"
            shutil.copy2(bin_path, dest_bin)

    copied: list[str] = []
    for raw_src, rel in extra_files or []:
        extra = Path(raw_src)
        if not extra.exists():
            continue
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(extra, target)
        copied.append(str(target))

    include_dir = src.parent / "Include"
    if include_dir.is_dir():
        for path in include_dir.rglob("*"):
            if not path.is_file():
                continue
            rel = Path("Include") / path.relative_to(include_dir)
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            copied.append(str(target))

    return {
        "dir": str(dest),
        "subdir": LAB_EXPERTS_SUBDIR,
        "expert": lab_expert_name(name),
        "source": str(dest_src),
        "binary": str(dest_bin) if dest_bin else None,
        "includes": copied,
    }
