from __future__ import annotations

from src.adapters.runtime import (
    NoopAssistantRuntimeAdapter,
    NoopGameRuntimeAdapter,
    PythonNativeAssistantRuntimeAdapter,
    PythonNativeGameRuntimeAdapter,
)
from src.infra.settings import Settings
from src.ports.assistant_runtime_port import AssistantRuntimePort
from src.ports.game_runtime_port import GameRuntimePort


class UnsupportedRuntimeModeError(ValueError):
    pass


def build_game_runtime(settings: Settings) -> GameRuntimePort:
    mode = settings.game_runtime_mode.lower()
    if mode == "python_native":
        return PythonNativeGameRuntimeAdapter()
    if mode == "noop":
        return NoopGameRuntimeAdapter()
    raise UnsupportedRuntimeModeError(f"unsupported GAME_RUNTIME_MODE: {settings.game_runtime_mode}")


def build_assistant_runtime(settings: Settings) -> AssistantRuntimePort:
    mode = settings.assistant_runtime_mode.lower()
    if mode == "python_native":
        return PythonNativeAssistantRuntimeAdapter()
    if mode == "noop":
        return NoopAssistantRuntimeAdapter()
    raise UnsupportedRuntimeModeError(f"unsupported ASSISTANT_RUNTIME_MODE: {settings.assistant_runtime_mode}")
