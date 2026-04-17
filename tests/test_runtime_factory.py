import unittest

from src.app.runtime_factory import build_assistant_runtime, build_game_runtime
from src.infra.settings import Settings


class RuntimeFactoryTest(unittest.TestCase):
    def _settings(self, game_mode: str, assistant_mode: str) -> Settings:
        return Settings(
            app_env="test",
            control_api_host="127.0.0.1",
            control_api_port=8788,
            control_api_token="",
            control_api_frontend_dir="",
            run_concurrency_mode="single",
            run_max_queue_size=10,
            automation_default_profile="genshin_cloud_bettergi",
            command_source_mode="local_file",
            command_source_file="./runtime/commands/inbox.json",
            game_runtime_mode=game_mode,
            assistant_runtime_mode=assistant_mode,
            scheduler_mode="noop",
            notify_mode="stdout",
            runtime_dir="./runtime",
        )

    def test_build_noop_runtimes(self) -> None:
        settings = self._settings("noop", "noop")
        game = build_game_runtime(settings)
        assistant = build_assistant_runtime(settings)
        self.assertIn("Noop", game.__class__.__name__)
        self.assertIn("Noop", assistant.__class__.__name__)

    def test_build_python_native_runtimes(self) -> None:
        settings = self._settings("python_native", "python_native")
        game = build_game_runtime(settings)
        assistant = build_assistant_runtime(settings)
        self.assertIn("PythonNative", game.__class__.__name__)
        self.assertIn("PythonNative", assistant.__class__.__name__)


if __name__ == "__main__":
    unittest.main()
