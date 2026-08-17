"""SQLite index over immutable run artifacts."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .config import db_path as default_db_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS strategies (
    name TEXT PRIMARY KEY,
    source_sha256 TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    strategy_name TEXT,
    status TEXT,
    symbol TEXT,
    period TEXT,
    from_date TEXT,
    to_date TEXT,
    model INTEGER,
    deposit REAL,
    started_at TEXT,
    finished_at TEXT,
    run_dir TEXT,
    error TEXT
);

CREATE TABLE IF NOT EXISTS experiments (
    experiment_id TEXT PRIMARY KEY,
    type TEXT,
    created_at TEXT,
    payload_json TEXT
);

CREATE TABLE IF NOT EXISTS metrics (
    run_id TEXT,
    key TEXT,
    value REAL,
    PRIMARY KEY (run_id, key)
);

CREATE TABLE IF NOT EXISTS trades (
    run_id TEXT,
    ticket TEXT,
    symbol TEXT,
    side TEXT,
    entry_time TEXT,
    entry_price REAL,
    exit_time TEXT,
    exit_price REAL,
    volume REAL,
    profit REAL,
    commission REAL,
    swap REAL,
    reason TEXT
);
"""


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    db = Path(path) if path else default_db_path()
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def upsert_run(
    manifest: dict[str, Any],
    metrics: dict[str, Any] | None = None,
    trades: list[dict[str, Any]] | None = None,
    db_file: str | Path | None = None,
) -> None:
    test = manifest.get("test") or {}
    strategy = manifest.get("strategy") or {}
    with connect(db_file) as conn:
        conn.execute(
            """
            INSERT INTO strategies(name, source_sha256, created_at)
            VALUES (?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET source_sha256=excluded.source_sha256
            """,
            (strategy.get("name"), strategy.get("source_sha256"), manifest.get("started_at")),
        )
        conn.execute(
            """
            INSERT INTO runs(
                run_id, strategy_name, status, symbol, period, from_date, to_date,
                model, deposit, started_at, finished_at, run_dir, error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                status=excluded.status,
                finished_at=excluded.finished_at,
                error=excluded.error
            """,
            (
                manifest.get("run_id"),
                strategy.get("name"),
                manifest.get("status"),
                test.get("symbol"),
                test.get("period"),
                test.get("from"),
                test.get("to"),
                test.get("model"),
                test.get("deposit"),
                manifest.get("started_at"),
                manifest.get("finished_at"),
                manifest.get("run_dir"),
                (manifest.get("error") or {}).get("message")
                if isinstance(manifest.get("error"), dict)
                else manifest.get("error"),
            ),
        )
        if metrics:
            conn.execute("DELETE FROM metrics WHERE run_id = ?", (manifest.get("run_id"),))
            for key, value in metrics.items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    conn.execute(
                        "INSERT INTO metrics(run_id, key, value) VALUES (?, ?, ?)",
                        (manifest.get("run_id"), key, float(value)),
                    )
        if trades is not None:
            conn.execute("DELETE FROM trades WHERE run_id = ?", (manifest.get("run_id"),))
            for trade in trades:
                conn.execute(
                    """
                    INSERT INTO trades(
                        run_id, ticket, symbol, side, entry_time, entry_price,
                        exit_time, exit_price, volume, profit, commission, swap, reason
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        manifest.get("run_id"),
                        trade.get("ticket"),
                        trade.get("symbol"),
                        trade.get("side"),
                        trade.get("entry_time"),
                        trade.get("entry_price"),
                        trade.get("exit_time"),
                        trade.get("exit_price"),
                        trade.get("volume"),
                        trade.get("profit"),
                        trade.get("commission"),
                        trade.get("swap"),
                        trade.get("reason"),
                    ),
                )
        conn.commit()


def upsert_experiment(record: dict[str, Any], db_file: str | Path | None = None) -> None:
    with connect(db_file) as conn:
        conn.execute(
            """
            INSERT INTO experiments(experiment_id, type, created_at, payload_json)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(experiment_id) DO UPDATE SET payload_json=excluded.payload_json
            """,
            (
                record.get("experiment_id"),
                record.get("type"),
                record.get("created_at"),
                json.dumps(record, ensure_ascii=False),
            ),
        )
        conn.commit()


def fetch_run(run_id: str, db_file: str | Path | None = None) -> dict[str, Any] | None:
    with connect(db_file) as conn:
        row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if not row:
            return None
        metrics = {
            r["key"]: r["value"]
            for r in conn.execute("SELECT key, value FROM metrics WHERE run_id = ?", (run_id,))
        }
        data = dict(row)
        data["metrics"] = metrics
        return data
