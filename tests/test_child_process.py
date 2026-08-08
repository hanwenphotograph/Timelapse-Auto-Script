from __future__ import annotations

import os
import sys
import time
import unittest

from timelapse_manager.child_process import ManagedChild


class ManagedChildTests(unittest.TestCase):
    def test_poll_drains_output_before_reporting_exit(self) -> None:
        events: list[str] = []

        def on_line(line: str) -> None:
            time.sleep(0.1)
            events.append(f"line:{line}")

        child = ManagedChild(
            "test-child",
            [sys.executable, "-c", "print('done', flush=True)"],
            cwd=None,
            env=os.environ.copy(),
            log=lambda _message: None,
            on_line=on_line,
            on_started=lambda _child: None,
            on_exited=lambda _child, code: events.append(f"exit:{code}"),
            stop_timeout=1,
        ).start()
        assert child.process is not None
        deadline = time.monotonic() + 5
        while child.process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.01)

        self.assertEqual(child.poll(), 0)
        self.assertEqual(events, ["line:done", "exit:0"])


if __name__ == "__main__":
    unittest.main()
