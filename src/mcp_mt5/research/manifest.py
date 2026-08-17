"""Research manifest — provenance for a single Strategy Tester run."""
from __future__ import annotations

from typing import Any

from .store import ResearchStore, utc_now

VALID_STATUSES = ("created", "compiling", "running", "completed", "failed", "timeout")


def new_manifest(run_id: str, strategy_name: str, test: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "status": "created",
        "stage": "created",
        "strategy": {
            "name": strategy_name,
            "source_sha256": None,
            "binary_sha256": None,
            "includes": [],
        },
        "test": test,
        "environment": {
            "terminal_build": None,
            "terminal_hash": None,
            "terminal_sha256": None,
            "broker_server": None,
            "mt5_install": None,
        },
        "files": {
            "config_sha256": None,
            "report": None,
            "trades": None,
            "tester_log": None,
        },
        "error": None,
        "return_code": None,
        "started_at": utc_now(),
        "finished_at": None,
    }


def write_manifest(store: ResearchStore, run_id: str, manifest: dict[str, Any]) -> None:
    status = manifest.get("status")
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid status: {status}")
    existing = None
    try:
        existing = store.read_json(run_id, "manifest.json")
    except FileNotFoundError:
        existing = None
    if existing and existing.get("status") == "completed":
        raise PermissionError(f"run {run_id} is completed and immutable")
    store.write_json(run_id, "manifest.json", manifest)


def read_manifest(store: ResearchStore, run_id: str) -> dict[str, Any]:
    data = store.read_json(run_id, "manifest.json")
    if not data:
        raise FileNotFoundError(f"manifest not found for {run_id}")
    return data


def update_manifest(store: ResearchStore, run_id: str, **changes: Any) -> dict[str, Any]:
    manifest = read_manifest(store, run_id)
    for key, value in changes.items():
        if key in ("strategy", "test", "environment", "files") and isinstance(value, dict):
            manifest.setdefault(key, {}).update(value)
        else:
            manifest[key] = value
    write_manifest(store, run_id, manifest)
    return manifest
