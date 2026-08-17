"""Snapshot an EA and every #include it actually uses into a run directory."""
from __future__ import annotations

import shutil
from pathlib import Path

from ..analysis import resolve_includes
from .hashes import sha256_file


def flatten_includes(node: dict) -> list[str]:
    out: list[str] = []
    if node.get("exists") and node.get("file") and not node.get("cycle"):
        out.append(node["file"])
    for child in node.get("resolved") or []:
        out.extend(flatten_includes(child))
    return out


def snapshot_strategy(
    source: str | Path,
    dest_dir: str | Path,
    mql_root: str | Path | None = None,
) -> dict:
    """Copy ``source`` as strategy.mq5 plus quoted/project includes.

    Standard library headers resolved from the terminal Include tree are hashed
    but compiled later via ``/include:<mql_root>`` so MetaEditor still finds them.
    """
    src = Path(source).resolve()
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    if not src.exists():
        raise FileNotFoundError(f"strategy not found: {src}")

    dest_src = dest / "strategy.mq5"
    shutil.copy2(src, dest_src)

    tree = resolve_includes(src, mql_root=str(mql_root) if mql_root else None)
    include_records: list[dict] = []
    copied: list[str] = []
    missing = list(tree.get("missing") or [])

    src_dir = src.parent.resolve()
    include_root = Path(mql_root).resolve() / "Include" if mql_root else None

    for raw in flatten_includes(tree):
        path = Path(raw).resolve()
        if path == src:
            continue
        if not path.exists():
            missing.append(str(path))
            continue
        record = {"src": str(path), "sha256": sha256_file(path)}
        try:
            rel = path.relative_to(src_dir)
            target = dest / rel
        except ValueError:
            if include_root:
                try:
                    rel = path.relative_to(include_root)
                    target = dest / "includes" / rel
                    record["std_include"] = True
                except ValueError:
                    target = dest / "includes" / path.name
            else:
                target = dest / "includes" / path.name
        if not record.get("std_include"):
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                shutil.copy2(path, target)
            record["snap"] = str(target.relative_to(dest))
            copied.append(str(target))
        include_records.append(record)
        missing.extend(_collect_missing(tree, path))

    return {
        "source": str(src),
        "strategy_mq5": str(dest_src),
        "includes": include_records,
        "copied": copied,
        "missing": sorted(set(missing)),
        "source_sha256": sha256_file(dest_src),
    }


def _collect_missing(node: dict, for_file: Path) -> list[str]:
    if Path(node.get("file", "")).resolve() == for_file:
        return list(node.get("missing") or [])
    found: list[str] = []
    for child in node.get("resolved") or []:
        found.extend(_collect_missing(child, for_file))
    return found


def resolve_strategy_path(strategy: str) -> Path:
    """Resolve a strategy argument to a .mq5 file on disk."""
    raw = Path(strategy)
    candidates: list[Path] = []
    if raw.exists():
        return raw.resolve()
    if raw.suffix.lower() in {".mq5", ".mq4"}:
        candidates.append(raw)
    else:
        candidates.append(Path(f"{strategy}.mq5"))
        candidates.append(Path("experts") / f"{strategy}.mq5")
        from .config import bundled_experts_dir, repo_root
        candidates.append(bundled_experts_dir() / f"{strategy}.mq5")
        candidates.append(repo_root() / "experts" / f"{strategy}.mq5")
    for cand in candidates:
        if cand.exists():
            return cand.resolve()
    raise FileNotFoundError(f"strategy source not found: {strategy}")
