from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from timelapse_manager.sunset_score.jsonl_client import SunsetScoreJsonlClient
from timelapse_manager.sunset_score.jsonl_protocol import (
    decode_event,
    encode_request,
    ready_error,
)


class SunsetScoreJsonlTests(unittest.TestCase):
    def test_client_uses_only_the_public_cli(self) -> None:
        runtime = SimpleNamespace()

        client = SunsetScoreJsonlClient(
            runtime,  # type: ignore[arg-type]
            ("/tools/sunsetscore",),
            interval=7,
            application_version="0.10.0",
        )

        self.assertEqual(
            client.argv,
            ["/tools/sunsetscore", "--serve-jsonl", "--interval", "7"],
        )

    def test_request_and_ready_event_follow_versioned_protocol(self) -> None:
        line = encode_request(
            4,
            "scan",
            session_id="task-1",
            directory="/photos/hdr_enfuse",
        )

        self.assertEqual(
            json.loads(line),
            {
                "id": 4,
                "command": "scan",
                "session": "task-1",
                "directory": "/photos/hdr_enfuse",
            },
        )
        event = decode_event(
            '{"event":"ready","protocol_version":1,"application_version":"0.10.0"}'
        )
        assert event is not None
        self.assertEqual(ready_error(event, "0.10.0"), "")
        self.assertIn("协议版本", ready_error(event | {"protocol_version": 2}, "0.10.0"))


if __name__ == "__main__":
    unittest.main()
