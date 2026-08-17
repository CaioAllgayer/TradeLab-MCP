"""Exclusive lock so two backtests never share the same MT5 data directory."""
from __future__ import annotations

import os
import time
from pathlib import Path


class LockBusy(RuntimeError):
    pass


class InstallLock:
    """PID lock file at ``<data>/mt5.lock``.

    V1 is sequential. A second acquire on the same data directory fails (or
    waits if ``timeout`` is set). Stale locks whose PID is dead are reused.
    """

    def __init__(self, lock_path: str | Path) -> None:
        self.path = Path(lock_path)
        self._held = False

    def acquire(self, timeout: float = 0.0, stale_sec: float = 6 * 3600) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.time() + max(timeout, 0.0)
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                try:
                    os.write(fd, f"{os.getpid()}\n{time.time():.3f}\n".encode("ascii"))
                finally:
                    os.close(fd)
                self._held = True
                return
            except FileExistsError:
                if self._stale(stale_sec):
                    try:
                        self.path.unlink()
                    except FileNotFoundError:
                        pass
                    continue
                if time.time() >= deadline:
                    raise LockBusy(f"MT5 lock busy: {self.path}")
                time.sleep(0.1)

    def release(self) -> None:
        if not self._held:
            return
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass
        self._held = False

    def _stale(self, stale_sec: float) -> bool:
        try:
            text = self.path.read_text(encoding="utf-8")
            pid_s, ts_s, *_ = (text.splitlines() + ["0", "0"])[:2]
            pid = int(pid_s.strip() or "0")
            created = float(ts_s.strip() or "0")
        except (OSError, ValueError):
            return True
        if pid and _pid_alive(pid):
            return False
        if created and (time.time() - created) < stale_sec and pid == 0:
            return False
        return True

    def __enter__(self) -> "InstallLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()


def lock_for_layout(data_dir: str | Path) -> InstallLock:
    return InstallLock(Path(data_dir) / "mt5.lock")


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes
            SYNCHRONIZE = 0x00100000
            handle = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, 0, pid)
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
            return False
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False
