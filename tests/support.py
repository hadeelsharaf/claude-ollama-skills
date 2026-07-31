"""Shared helpers for the test suite and the e2e script. Standard library only."""
from __future__ import annotations

import os
import shutil
import stat
import time


def rmtree_force(path: str, attempts: int = 5, delay: float = 0.25) -> None:
    """shutil.rmtree that clears read-only bits and survives transient
    Windows file locks.

    Antivirus, OneDrive, or git can briefly hold a handle on a file being
    deleted (observed live: PermissionError WinError 5 unlinking a read-only
    .git object in tearDown, passing on immediate re-run). A single
    chmod-and-retry does not cover that window, so failed passes are retried
    with a short delay before giving up.
    """
    def onerror(func, p, _exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)

    for attempt in range(attempts):
        try:
            shutil.rmtree(path, onerror=onerror)
            return
        except OSError:
            if attempt == attempts - 1:
                raise
            time.sleep(delay)
