import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.adapters.local_command_adapter import LocalFileCommandAdapter


class LocalCommandAdapterTest(unittest.TestCase):
    def test_legacy_overrides_supported(self) -> None:
        with TemporaryDirectory() as td:
            p = Path(td) / "commands.json"
            p.write_text(json.dumps({"overrides": {"task": "a"}}), encoding="utf-8")
            adapter = LocalFileCommandAdapter(str(p))
            self.assertEqual(adapter.fetch_effective_overrides(), {"task": "a"})

    def test_priority_and_expiry(self) -> None:
        with TemporaryDirectory() as td:
            p = Path(td) / "commands.json"
            p.write_text(
                json.dumps(
                    {
                        "commands": [
                            {
                                "key": "task.domain",
                                "value": "old",
                                "priority": 10,
                                "created_at": "2026-04-01T00:00:00Z",
                                "expires_at": "2099-01-01T00:00:00Z",
                            },
                            {
                                "key": "task.domain",
                                "value": "new",
                                "priority": 100,
                                "created_at": "2026-04-02T00:00:00Z",
                                "expires_at": "2099-01-01T00:00:00Z",
                            },
                            {
                                "key": "feature.skip",
                                "value": True,
                                "priority": 1,
                                "created_at": "2026-04-02T00:00:00Z",
                                "expires_at": "2000-01-01T00:00:00Z",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            adapter = LocalFileCommandAdapter(str(p))
            self.assertEqual(adapter.fetch_effective_overrides(), {"task.domain": "new"})


if __name__ == "__main__":
    unittest.main()
