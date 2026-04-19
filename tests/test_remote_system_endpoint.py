import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.adapters.remote.auth import TokenAuth
from src.adapters.remote.context import RemoteContext
from src.adapters.remote.endpoints import system
from src.adapters.remote.router import Request, Router


class _FakeLogs:
    def control_api_event(self, *_args, **_kwargs) -> None:
        return


class _FakeOrchestrator:
    def __init__(self) -> None:
        self.logs = _FakeLogs()

    def active_run_id(self):
        return None


class RemoteSystemEndpointTest(unittest.TestCase):
    def _register_router(self, runtime_dir: Path, repo_dir: Path) -> Router:
        router = Router()
        context = RemoteContext(
            orchestrator=_FakeOrchestrator(),
            auth=TokenAuth(token=""),
            runtime_dir=runtime_dir,
            repo_dir=repo_dir,
            frontend_dir=None,
        )
        system.register(router, context)
        return router

    def test_git_pull_rejects_invalid_branch(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / ".git").mkdir()
            router = self._register_router(root / "runtime", root)
            match = router.match("POST", "/api/v1/system/git/pull")
            assert match is not None
            req = Request(
                method="POST",
                path="/api/v1/system/git/pull",
                body=json.dumps({"branch": "../evil"}).encode("utf-8"),
            )
            resp = match.handler(req)
            self.assertEqual(resp.status, 400)

    def test_git_pull_rejects_missing_repo(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            router = self._register_router(root / "runtime", root / "missing-repo")
            match = router.match("POST", "/api/v1/system/git/pull")
            assert match is not None
            req = Request(
                method="POST",
                path="/api/v1/system/git/pull",
                body=b"{}",
            )
            resp = match.handler(req)
            self.assertEqual(resp.status, 400)

    @patch("src.adapters.remote.endpoints.system.subprocess.run")
    def test_git_pull_success(self, run_mock) -> None:
        class _CP:
            def __init__(self, returncode: int, stdout: str, stderr: str) -> None:
                self.returncode = returncode
                self.stdout = stdout
                self.stderr = stderr

        run_mock.side_effect = [
            _CP(0, "deadbeef\n", ""),  # before rev
            _CP(0, "rebuild/v2.0\n", ""),  # branch
            _CP(0, "Already up to date.\n", ""),  # pull
            _CP(0, "deadbeef\n", ""),  # after rev
        ]
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / ".git").mkdir()
            router = self._register_router(root / "runtime", root)
            match = router.match("POST", "/api/v1/system/git/pull")
            assert match is not None
            req = Request(
                method="POST",
                path="/api/v1/system/git/pull",
                body=json.dumps({"branch": "rebuild/v2.0"}).encode("utf-8"),
            )
            resp = match.handler(req)
            status, _headers, body, _file = resp.render()
            payload = json.loads((body or b"{}").decode("utf-8"))
            self.assertEqual(status, 200)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["command"], ["git", "pull", "origin", "rebuild/v2.0"])


if __name__ == "__main__":
    unittest.main()
