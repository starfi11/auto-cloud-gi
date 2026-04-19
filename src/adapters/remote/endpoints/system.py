from __future__ import annotations

import json
import os
import re
import subprocess
from http import HTTPStatus

from src.adapters.remote.context import RemoteContext
from src.adapters.remote.router import JsonResponse, Request, Router

_SAFE_BRANCH = re.compile(r"^[A-Za-z0-9._/-]{1,128}$")


def _git_output_tail(text: str, *, limit: int = 3000) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]


def _git_rev(cwd: str, args: list[str]) -> str:
    try:
        cp = subprocess.run(
            args,
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=8,
        )
        out = (cp.stdout or "").strip()
        return out if cp.returncode == 0 else ""
    except Exception:
        return ""


def register(router: Router, context: RemoteContext) -> None:
    def health(_req: Request) -> JsonResponse:
        active = context.orchestrator.active_run_id()
        return JsonResponse(
            payload={
                "ok": True,
                "auth_enabled": context.auth.enabled,
                "active_run_id": active,
                "runtime_dir": str(context.runtime_dir),
                "repo_dir": str(context.repo_dir),
                "frontend_dir": str(context.frontend_dir) if context.frontend_dir else None,
            }
        )

    def git_pull(req: Request) -> JsonResponse:
        body: dict = {}
        if req.body:
            try:
                parsed = json.loads(req.body.decode("utf-8"))
            except json.JSONDecodeError:
                return JsonResponse(
                    status=HTTPStatus.BAD_REQUEST,
                    payload={"ok": False, "error": "invalid_json"},
                )
            if not isinstance(parsed, dict):
                return JsonResponse(
                    status=HTTPStatus.BAD_REQUEST,
                    payload={"ok": False, "error": "invalid_json"},
                )
            body = parsed

        remote = str(body.get("remote", "origin")).strip() or "origin"
        branch = str(body.get("branch", "")).strip()
        if remote != "origin":
            return JsonResponse(
                status=HTTPStatus.BAD_REQUEST,
                payload={"ok": False, "error": "invalid_remote", "allowed_remote": "origin"},
            )
        if branch and (not _SAFE_BRANCH.match(branch) or ".." in branch or branch.startswith("-")):
            return JsonResponse(
                status=HTTPStatus.BAD_REQUEST,
                payload={"ok": False, "error": "invalid_branch"},
            )

        repo_dir = context.repo_dir.resolve()
        if not (repo_dir / ".git").exists():
            return JsonResponse(
                status=HTTPStatus.BAD_REQUEST,
                payload={"ok": False, "error": "git_repo_not_found", "repo_dir": str(repo_dir)},
            )

        cmd = ["git", "pull", "origin"]
        if branch:
            cmd.append(branch)
        timeout_seconds = max(5, int(os.getenv("CONTROL_API_GIT_PULL_TIMEOUT_SECONDS", "180")))
        before = _git_rev(str(repo_dir), ["git", "rev-parse", "HEAD"])
        current_branch = _git_rev(str(repo_dir), ["git", "rev-parse", "--abbrev-ref", "HEAD"])
        try:
            cp = subprocess.run(
                cmd,
                cwd=str(repo_dir),
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            return JsonResponse(
                status=HTTPStatus.GATEWAY_TIMEOUT,
                payload={"ok": False, "error": "git_pull_timeout", "timeout_seconds": timeout_seconds},
            )
        except Exception as exc:  # noqa: BLE001
            return JsonResponse(
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
                payload={"ok": False, "error": f"git_pull_failed:{type(exc).__name__}:{exc}"},
            )
        after = _git_rev(str(repo_dir), ["git", "rev-parse", "HEAD"])

        payload = {
            "ok": cp.returncode == 0,
            "repo_dir": str(repo_dir),
            "branch": branch or current_branch,
            "command": cmd,
            "returncode": cp.returncode,
            "before_head": before,
            "after_head": after,
            "stdout": _git_output_tail(cp.stdout or ""),
            "stderr": _git_output_tail(cp.stderr or ""),
        }
        status = HTTPStatus.OK if cp.returncode == 0 else HTTPStatus.CONFLICT
        context.orchestrator.logs.control_api_event(
            "git_pull_executed",
            {
                "ok": payload["ok"],
                "repo_dir": payload["repo_dir"],
                "branch": payload["branch"],
                "before_head": before,
                "after_head": after,
                "returncode": cp.returncode,
            },
            level="INFO" if cp.returncode == 0 else "WARN",
        )
        return JsonResponse(status=status, payload=payload)

    router.register("GET", "/api/v1/health", health)
    router.register("POST", "/api/v1/system/git/pull", git_pull)
