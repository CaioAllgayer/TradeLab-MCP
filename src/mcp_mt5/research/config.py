"""Paths and environment for the research store."""
from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    """TradeLab-MCP repository root when running from a checkout."""
    return Path(__file__).resolve().parents[3]


def packaged_experts_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "experts"


def bundled_experts_dir() -> Path:
    for candidate in (packaged_experts_dir(), repo_root() / "experts", Path.cwd() / "experts"):
        if candidate.exists():
            return candidate
    return packaged_experts_dir()


def research_root(explicit: str | Path | None = None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    env = os.environ.get("TRADE_LAB_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    return (Path.cwd() / "research").resolve()


def runs_dir(root: str | Path | None = None) -> Path:
    return research_root(root) / "runs"


def experiments_dir(root: str | Path | None = None) -> Path:
    return research_root(root) / "experiments"


def db_path(root: str | Path | None = None) -> Path:
    return research_root(root) / "research.db"


# Always publish automatic/test EAs here, relative to the active terminal Experts/.
# Example: %APPDATA%\MetaQuotes\Terminal\<hash>\MQL5\Experts\TradeLab MCP
LAB_EXPERTS_SUBDIR = "TradeLab MCP"


def lab_experts_dir(layout) -> Path:
    return Path(layout.experts_dir) / LAB_EXPERTS_SUBDIR


def lab_expert_name(strategy_name: str) -> str:
    """Value for tester.ini Expert= (backslash, no extension)."""
    return f"{LAB_EXPERTS_SUBDIR}\\{strategy_name}"
