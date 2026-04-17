from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.adapters.remote.auth import TokenAuth
from src.app.orchestrator import Orchestrator


@dataclass(frozen=True)
class RemoteContext:
    """Shared dependencies handed to every endpoint handler.

    Passed by the server into a Router-building factory so endpoints can
    reach the Orchestrator, the runtime directory (for serving run artifacts),
    and the optional frontend build directory — without each handler importing
    global state.
    """

    orchestrator: Orchestrator
    auth: TokenAuth
    runtime_dir: Path
    frontend_dir: Path | None = None
