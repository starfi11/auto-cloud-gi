from __future__ import annotations

from src.app.control_api import run_control_api
from src.app.orchestrator import Orchestrator
from src.app.runtime_factory import build_assistant_runtime, build_game_runtime
from src.infra.settings import Settings


def main() -> None:
    settings = Settings.from_env()
    game_runtime = build_game_runtime(settings)
    assistant_runtime = build_assistant_runtime(settings)
    orchestrator = Orchestrator(
        runtime_dir=settings.runtime_dir,
        command_source_file=settings.command_source_file,
        game_runtime=game_runtime,
        assistant_runtime=assistant_runtime,
        concurrency_mode=settings.run_concurrency_mode,
        default_profile=settings.automation_default_profile,
    )
    run_control_api(settings.control_api_host, settings.control_api_port, orchestrator)


if __name__ == "__main__":
    main()
