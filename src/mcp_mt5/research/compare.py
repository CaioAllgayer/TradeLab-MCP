"""Compare completed runs by their stored metrics — never by 'latest report'."""
from __future__ import annotations

from typing import Any

from .store import ResearchStore


def compare_runs(store: ResearchStore, run_ids: list[str]) -> dict[str, Any]:
    if len(run_ids) < 2:
        return {"error": "compare_runs requires at least two run_id values"}

    runs: list[dict[str, Any]] = []
    for run_id in run_ids:
        try:
            store.require_run(run_id)
        except FileNotFoundError as exc:
            return {"error": str(exc)}
        manifest = store.read_json(run_id, "manifest.json") or {}
        metrics = store.read_json(run_id, "metrics.json") or {}
        runs.append({
            "run_id": run_id,
            "status": manifest.get("status"),
            "test": manifest.get("test"),
            "strategy": manifest.get("strategy"),
            "metrics": metrics,
        })

    baseline = runs[0]
    diffs: list[dict[str, Any]] = []
    keys = set()
    for run in runs:
        keys.update(run["metrics"].keys())
    for key in sorted(keys):
        row: dict[str, Any] = {"key": key, "values": {}}
        base = baseline["metrics"].get(key)
        row["values"][baseline["run_id"]] = base
        for run in runs[1:]:
            cand = run["metrics"].get(key)
            row["values"][run["run_id"]] = cand
            delta = None
            pct = None
            if isinstance(base, (int, float)) and isinstance(cand, (int, float)):
                delta = round(float(cand) - float(base), 8)
                pct = round((delta / float(base)) * 100.0, 6) if base != 0 else None
            row.setdefault("deltas_vs_baseline", {})[run["run_id"]] = {"delta": delta, "pct": pct}
        diffs.append(row)

    return {
        "baseline": baseline["run_id"],
        "run_ids": run_ids,
        "runs": runs,
        "diffs": diffs,
    }
