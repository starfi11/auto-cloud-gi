from __future__ import annotations

from src.adapters.remote.server import run_remote_server
from src.app.orchestrator import Orchestrator


def run_control_api(
    host: str,
    port: int,
    orchestrator: Orchestrator,
    *,
    token: str = "",
    runtime_dir: str = "./runtime",
    repo_dir: str = ".",
    frontend_dir: str | None = None,
) -> None:
    """Legacy entry point preserved for backwards compatibility.

    Delegates to the remote adapter so old call sites keep working. New code
    should import ``run_remote_server`` directly.
    """
    run_remote_server(
        host=host,
        port=port,
        orchestrator=orchestrator,
        token=token,
        runtime_dir=runtime_dir,
        repo_dir=repo_dir,
        frontend_dir=frontend_dir,
    )
