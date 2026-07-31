"""Tests for the shared test-support helpers (tests/support.py)."""
from __future__ import annotations

import os
import stat
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from support import rmtree_force  # noqa: E402


class RmtreeForceTests(unittest.TestCase):
    def test_removes_tree_containing_read_only_file(self):
        """git object files are read-only; plain rmtree fails on them."""
        tmp = tempfile.mkdtemp(prefix="support_ro_")
        locked = Path(tmp) / "sub" / "readonly.txt"
        locked.parent.mkdir()
        locked.write_text("x", encoding="utf-8")
        os.chmod(locked, stat.S_IREAD)
        rmtree_force(tmp)
        self.assertFalse(Path(tmp).exists())

    def test_survives_a_transiently_held_file(self):
        """A handle briefly held by another actor (antivirus, OneDrive, git)
        blocks deletion on Windows; the helper must retry until it wins.
        On POSIX an open handle does not block deletion, so this simply
        asserts the tree is gone."""
        tmp = tempfile.mkdtemp(prefix="support_lock_")
        held = Path(tmp) / "held.txt"
        held.write_text("x", encoding="utf-8")
        handle = open(held, "r", encoding="utf-8")
        timer = threading.Timer(0.3, handle.close)
        timer.start()
        try:
            rmtree_force(tmp)
        finally:
            timer.cancel()
            if not handle.closed:
                handle.close()
        self.assertFalse(Path(tmp).exists())


if __name__ == "__main__":
    unittest.main()
