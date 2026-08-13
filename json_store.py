from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from pathlib import Path

_LOCK_SUFFIX = ".lock"
_LOCK_POLL_SEC = 0.05
_LOCK_TIMEOUT_SEC = 15.0


def _lock_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + _LOCK_SUFFIX)


@contextmanager
def file_lock(path: Path, *, timeout: float = _LOCK_TIMEOUT_SEC):
    path = Path(path)
    lock_file = _lock_path(path)
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    handle = open(lock_file, "a+b")
    deadline = time.monotonic() + max(0.1, float(timeout))
    acquired = False
    try:
        while time.monotonic() < deadline:
            try:
                if os.name == "nt":
                    import msvcrt

                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except (OSError, BlockingIOError):
                time.sleep(_LOCK_POLL_SEC)
        if not acquired:
            raise TimeoutError(f"file lock timeout: {path}")
        yield
    finally:
        if acquired:
            try:
                if os.name == "nt":
                    import msvcrt

                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        handle.close()


def read_json(path: Path, default=None):
    path = Path(path)
    if not path.is_file():
        return default
    try:
        with file_lock(path):
            with open(path, encoding="utf-8") as handle:
                return json.load(handle)
    except (json.JSONDecodeError, OSError, TimeoutError):
        return default


def write_json(path: Path, data, *, indent: int = 2) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with file_lock(path):
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=indent)
        tmp.replace(path)
