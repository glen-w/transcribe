"""Project mutation lock and long-lived OCR job lock."""

from __future__ import annotations

import os
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

_PROCESS_LOCKS: dict[str, threading.Lock] = {}
_PROCESS_LOCKS_GUARD = threading.Lock()


def _process_lock_for(path: Path) -> threading.Lock:
    key = str(path.resolve()) if path.exists() else str(path.absolute())
    with _PROCESS_LOCKS_GUARD:
        lock = _PROCESS_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _PROCESS_LOCKS[key] = lock
        return lock


class LockTimeoutError(TimeoutError):
    pass


class FileLock:
    """Cross-process exclusive lock using fcntl/msvcrt on a lock file."""

    def __init__(self, path: Path, *, timeout: float = 30.0) -> None:
        self.path = Path(path)
        self.timeout = timeout
        self._fd: int | None = None

    def acquire(self, *, blocking: bool = True) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()
        fd = os.open(str(self.path), os.O_RDWR)
        deadline = None if not blocking else time.monotonic() + self.timeout
        while True:
            try:
                if sys.platform == "win32":
                    import msvcrt

                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._fd = fd
                return True
            except OSError:
                if not blocking:
                    os.close(fd)
                    return False
                if deadline is not None and time.monotonic() >= deadline:
                    os.close(fd)
                    raise LockTimeoutError(f"timed out acquiring lock: {self.path}")
                time.sleep(0.05)

    def release(self) -> None:
        if self._fd is None:
            return
        try:
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(self._fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._fd, fcntl.LOCK_UN)
        finally:
            os.close(self._fd)
            self._fd = None

    def __enter__(self) -> FileLock:
        self.acquire(blocking=True)
        return self

    def __exit__(self, *exc: object) -> None:
        self.release()


@contextmanager
def mutation_lock(path: Path, *, timeout: float = 30.0) -> Iterator[None]:
    """Short-lived RMW lock: process-local then file lock."""
    proc = _process_lock_for(path)
    with proc:
        with FileLock(path, timeout=timeout):
            yield


class JobLock:
    """Long-lived exclusive OCR job lock for one project."""

    def __init__(self, path: Path) -> None:
        self._lock = FileLock(path, timeout=0.0)
        self._held = False

    def try_acquire(self) -> bool:
        ok = self._lock.acquire(blocking=False)
        self._held = ok
        return ok

    def acquire(self, *, timeout: float = 0.0) -> bool:
        if timeout <= 0:
            return self.try_acquire()
        self._lock.timeout = timeout
        try:
            self._lock.acquire(blocking=True)
            self._held = True
            return True
        except LockTimeoutError:
            return False

    def release(self) -> None:
        if self._held:
            self._lock.release()
            self._held = False

    @property
    def held(self) -> bool:
        return self._held

    def __enter__(self) -> JobLock:
        if not self.try_acquire():
            raise LockTimeoutError(f"job lock held elsewhere: {self._lock.path}")
        return self

    def __exit__(self, *exc: object) -> None:
        self.release()


def job_lock_held(path: Path) -> bool:
    """Non-blocking probe: True if another process holds the job lock."""
    probe = JobLock(path)
    if probe.try_acquire():
        probe.release()
        return False
    return True
