"""Unique identifiers for runs and experiments."""
from __future__ import annotations

import re
import secrets
from datetime import datetime

RUN_ID_RE = re.compile(r"^\d{8}_\d{6}_[0-9a-f]{6}$")


def new_run_id(now: datetime | None = None) -> str:
    stamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    return f"{stamp}_{secrets.token_hex(3)}"


def new_experiment_id(now: datetime | None = None) -> str:
    stamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    return f"exp_{stamp}_{secrets.token_hex(3)}"


def is_run_id(value: str) -> bool:
    return bool(RUN_ID_RE.match(value or ""))
