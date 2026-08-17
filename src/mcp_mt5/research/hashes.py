"""SHA-256 helpers for strategy provenance."""
from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hash_files(paths: list[str | Path]) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in paths:
        path = Path(raw)
        if path.is_file():
            out[str(path)] = sha256_file(path)
    return out
