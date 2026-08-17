"""Per-run artifact directories. Nothing is retrieved by 'latest file'."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .config import research_root
from .ids import is_run_id

RUN_FILES = (
    "tester.ini",
    "strategy.mq5",
    "strategy.ex5",
    "report.htm",
    "tester.log",
    "trades.csv",
    "metrics.json",
    "manifest.json",
    "compile.log",
    "error.json",
)

TERMINAL_STATES = ("created", "compiling", "running", "completed", "failed", "timeout")
FROZEN_STATES = {"completed"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ResearchStore:
    def __init__(self, root: str | Path | None = None) -> None:
        self.root = research_root(root)
        self.runs = self.root / "runs"
        self.experiments = self.root / "experiments"
        self.runs.mkdir(parents=True, exist_ok=True)
        self.experiments.mkdir(parents=True, exist_ok=True)

    def run_dir(self, run_id: str) -> Path:
        if not is_run_id(run_id):
            raise ValueError(f"invalid run_id: {run_id}")
        return self.runs / run_id

    def create_run(self, run_id: str) -> Path:
        path = self.run_dir(run_id)
        if path.exists():
            raise FileExistsError(f"run already exists: {run_id}")
        path.mkdir(parents=True)
        return path

    def require_run(self, run_id: str) -> Path:
        path = self.run_dir(run_id)
        if not path.exists():
            raise FileNotFoundError(f"run not found: {run_id}")
        return path

    def manifest_path(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "manifest.json"

    def read_json(self, run_id: str, name: str) -> dict | None:
        path = self.run_dir(run_id) / name
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def write_json(self, run_id: str, name: str, payload: dict) -> Path:
        path = self.require_run(run_id) / name
        if self.is_frozen(run_id) and name != "manifest.json":
            raise PermissionError(f"run {run_id} is completed and immutable")
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(path)
        return path

    def write_text(self, run_id: str, name: str, text: str) -> Path:
        if self.is_frozen(run_id):
            raise PermissionError(f"run {run_id} is completed and immutable")
        path = self.require_run(run_id) / name
        path.write_text(text, encoding="utf-8")
        return path

    def copy_into(self, run_id: str, source: str | Path, dest_name: str) -> Path:
        if self.is_frozen(run_id):
            raise PermissionError(f"run {run_id} is completed and immutable")
        src = Path(source)
        dest = self.require_run(run_id) / dest_name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(src.read_bytes())
        return dest

    def is_frozen(self, run_id: str) -> bool:
        manifest = self.read_json(run_id, "manifest.json")
        if not manifest:
            return False
        return manifest.get("status") in FROZEN_STATES

    def list_artifacts(self, run_id: str) -> dict[str, str | None]:
        folder = self.require_run(run_id)
        out: dict[str, str | None] = {}
        for name in RUN_FILES:
            path = folder / name
            out[name] = str(path) if path.exists() else None
        includes = folder / "includes"
        if includes.exists():
            out["includes"] = str(includes)
        return out

    def experiment_path(self, experiment_id: str) -> Path:
        return self.experiments / f"{experiment_id}.json"

    def write_experiment(self, experiment_id: str, payload: dict) -> Path:
        path = self.experiment_path(experiment_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(path)
        return path

    def read_experiment(self, experiment_id: str) -> dict:
        path = self.experiment_path(experiment_id)
        if not path.exists():
            raise FileNotFoundError(f"experiment not found: {experiment_id}")
        return json.loads(path.read_text(encoding="utf-8"))
