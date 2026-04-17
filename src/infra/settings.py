from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "true" if default else "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _load_dotenv(dotenv_path: Path, override: bool) -> None:
    if not dotenv_path.exists():
        return
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if override:
            os.environ[key] = value
        else:
            os.environ.setdefault(key, value)


@dataclass(frozen=True)
class Settings:
    app_env: str
    control_api_host: str
    control_api_port: int
    control_api_token: str
    control_api_frontend_dir: str
    run_concurrency_mode: str
    run_max_queue_size: int
    automation_default_profile: str
    command_source_mode: str
    command_source_file: str
    game_runtime_mode: str
    assistant_runtime_mode: str
    scheduler_mode: str
    notify_mode: str
    runtime_dir: str

    @staticmethod
    def from_env() -> "Settings":
        dotenv_override = _bool_env("DOTENV_OVERRIDE", default=True)
        _load_dotenv(Path(".env"), override=dotenv_override)
        return Settings(
            app_env=os.getenv("APP_ENV", "dev"),
            control_api_host=os.getenv("CONTROL_API_HOST", "0.0.0.0"),
            control_api_port=int(os.getenv("CONTROL_API_PORT", "8788")),
            control_api_token=os.getenv("CONTROL_API_TOKEN", "").strip(),
            control_api_frontend_dir=os.getenv("CONTROL_API_FRONTEND_DIR", "").strip(),
            run_concurrency_mode=os.getenv("RUN_CONCURRENCY_MODE", "single"),
            run_max_queue_size=int(os.getenv("RUN_MAX_QUEUE_SIZE", "10")),
            automation_default_profile=os.getenv("AUTOMATION_DEFAULT_PROFILE", "genshin_cloud_bettergi"),
            command_source_mode=os.getenv("COMMAND_SOURCE_MODE", "local_file"),
            command_source_file=os.getenv("COMMAND_SOURCE_FILE", "./runtime/commands/inbox.json"),
            game_runtime_mode=os.getenv("GAME_RUNTIME_MODE", "python_native"),
            assistant_runtime_mode=os.getenv("ASSISTANT_RUNTIME_MODE", "python_native"),
            scheduler_mode=os.getenv("SCHEDULER_MODE", "noop"),
            notify_mode=os.getenv("NOTIFY_MODE", "stdout"),
            runtime_dir=os.getenv("RUNTIME_DIR", "./runtime"),
        )
