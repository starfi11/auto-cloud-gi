from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
import json
import threading
import traceback
import uuid

from src.adapters.local_command_adapter import LocalFileCommandAdapter
from src.adapters.controllers import ActionDispatcherController, BlackboardController, ControllerRouter
from src.adapters.policy import TransitionPolicyEngine
from src.adapters.profiles import GenshinCloudBetterGIProfile
from src.adapters.recovery import NoopAiRecoveryPlanner, TableRecoveryStrategy
from src.adapters.state import SpecStateEstimator
from src.adapters.stdout_notify_adapter import StdoutNotifyAdapter
from src.app.action_dispatcher import ActionDispatcher
from src.app.profile_registry import ProfileRegistry
from src.app.run_executor import RunExecutor
from src.app.run_signals import RunSignalCenter
from src.domain.policies import EffectivePolicy
from src.domain.run_manifest import RunManifest
from src.domain.run_request import RunReceipt, RunRequest
from src.domain.workflow import WorkflowPlan
from src.infra.log_manager import LogManager
from src.infra.state_store import StateStore
from src.kernel.checkpoint_store import CheckpointStore
from src.kernel.context_manager import ContextManager
from src.kernel.context_store import ContextStore, RunContext
from src.kernel.event_bus import EventBus
from src.kernel.event_contract import Event
from src.kernel.exception_router import InterruptError
from src.kernel.resource_arbiter import ResourceArbiter
from src.ports.assistant_runtime_port import AssistantRuntimePort
from src.ports.game_runtime_port import GameRuntimePort
from src.ports.trigger_port import TriggerPort


@dataclass
class RunRecord:
    run_id: str
    status: str
    reason: str = ""
    target_profile: str = ""
    scenario: str = ""
    created_at: str = ""
    started_at: str = ""
    finished_at: str = ""


class Orchestrator(TriggerPort):
    def __init__(
        self,
        runtime_dir: str,
        command_source_file: str,
        game_runtime: GameRuntimePort,
        assistant_runtime: AssistantRuntimePort,
        concurrency_mode: str = "single",
        default_profile: str = "genshin_cloud_bettergi",
    ) -> None:
        self._runtime_dir = Path(runtime_dir)
        self._runtime_dir.mkdir(parents=True, exist_ok=True)
        self._manifests_dir = self._runtime_dir / "manifests"
        self._manifests_dir.mkdir(parents=True, exist_ok=True)

        self._contexts = ContextStore()
        self._checkpoints = CheckpointStore(runtime_dir)
        self._command_source = LocalFileCommandAdapter(command_source_file)
        self._notify = StdoutNotifyAdapter()
        self._logs = LogManager(runtime_dir)
        self._event_bus = EventBus(on_publish=self._on_event_published, on_dispatch=self._on_event_dispatched)
        self._signals = RunSignalCenter()
        self._profiles = ProfileRegistry(
            _profiles={
                "genshin_cloud_bettergi": GenshinCloudBetterGIProfile(),
            },
            _default_profile=default_profile,
        )

        dispatcher = ActionDispatcher(
            game_runtime=game_runtime,
            assistant_runtime=assistant_runtime,
            interrupt_check=self._is_interrupted,
            risk_check=self._is_risk_stopped,
        )
        self._context_manager = ContextManager(default_context_id="global")
        controller_router = ControllerRouter(
            controllers=[
                BlackboardController(),
                ActionDispatcherController(
                    _controller_id="genshin_controller",
                    dispatcher=dispatcher,
                    supported_prefixes=("game.",),
                ),
                ActionDispatcherController(
                    _controller_id="bettergi_controller",
                    dispatcher=dispatcher,
                    supported_prefixes=("assistant.", "system."),
                ),
            ],
            context_manager=self._context_manager,
            logs=self._logs,
        )
        self._executor = RunExecutor(
            logs=self._logs,
            checkpoints=self._checkpoints,
            runtime=controller_router,
            interrupt_check=self._is_interrupted,
            risk_check=self._is_risk_stopped,
            state_estimator=SpecStateEstimator(),
            policy_engine=TransitionPolicyEngine(),
            context_manager=self._context_manager,
            recovery_strategy=TableRecoveryStrategy(),
            resource_arbiter=ResourceArbiter(),
            ai_recovery_planner=NoopAiRecoveryPlanner(),
        )

        self._concurrency_mode = concurrency_mode
        self._idempotency_map: dict[str, str] = {}
        self._records: dict[str, RunRecord] = {}
        self._state_store = StateStore(runtime_dir)
        self._active_run_lock = threading.Lock()
        self._active_run_id: str | None = None
        self._workers: dict[str, threading.Thread] = {}

        self._load_persisted_state()

        self._logs.system_event(
            "orchestrator_initialized",
            {
                "runtime_dir": str(self._runtime_dir),
                "command_source_file": command_source_file,
                "concurrency_mode": concurrency_mode,
                "default_profile": default_profile,
                "profiles": ["genshin_cloud_bettergi"],
            },
        )

    @property
    def logs(self) -> LogManager:
        return self._logs

    def _persist_state(self) -> None:
        record_dict = {run_id: asdict(rec) for run_id, rec in self._records.items()}
        self._state_store.save(self._idempotency_map, record_dict)

    def _load_persisted_state(self) -> None:
        idem, recs = self._state_store.load()
        self._idempotency_map = idem
        parsed: dict[str, RunRecord] = {}
        for run_id, payload in recs.items():
            if not isinstance(payload, dict):
                continue
            try:
                parsed[run_id] = RunRecord(**payload)
            except TypeError:
                continue
        self._records = parsed

    def _utc_now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _on_event_published(self, event: Event) -> None:
        if event.run_id:
            self._logs.run_event(event.run_id, f"event_published:{event.type}", event.payload)

    def _on_event_dispatched(self, event: Event) -> None:
        if event.run_id:
            self._logs.run_event(event.run_id, f"event_dispatched:{event.type}", event.payload)

    def _is_interrupted(self, run_id: str) -> tuple[bool, str]:
        snap = self._signals.snapshot(run_id)
        return snap.interrupted, snap.interrupt_reason

    def _is_risk_stopped(self, run_id: str) -> tuple[bool, str]:
        snap = self._signals.snapshot(run_id)
        return snap.risk_stopped, snap.risk_reason

    def _execute_run(self, run_id: str, context: RunContext, workflow_plan: dict[str, object]) -> None:
        try:
            rec = self._records[run_id]
            rec.status = "running"
            rec.started_at = self._utc_now()
            self._persist_state()
            self._event_bus.publish(Event(type="RUN.STARTED", source="executor", run_id=run_id, payload={}))
            self._event_bus.dispatch_once()

            plan = WorkflowPlan.from_dict(workflow_plan)
            self._executor.execute(context, plan)

            rec.status = "finished"
            rec.reason = "ok"
            rec.finished_at = self._utc_now()
            self._logs.write_run_summary(
                run_id,
                {
                    "run_id": run_id,
                    "status": rec.status,
                    "trigger": context.manifest.get("trigger", ""),
                    "target_profile": rec.target_profile,
                    "scenario": rec.scenario,
                    "reason": rec.reason,
                },
            )
            self._logs.write_run_diagnostics(
                run_id,
                {
                    "run_id": run_id,
                    "status": "finished",
                    "state": context.state,
                    "context_id": context.active_context_id,
                    "controller_id": context.layered_state.controller_layer.active_controller_id,
                    "last_error": context.last_error,
                },
            )
            self._event_bus.publish(Event(type="RUN.FINISHED", source="executor", run_id=run_id, payload={}))
            self._event_bus.dispatch_once()
        except InterruptError as exc:
            rec = self._records.get(run_id)
            reason = str(exc)
            status = "interrupted"
            if reason.startswith("risk_stop:"):
                status = "risk_stopped"
            if rec is not None:
                rec.status = status
                rec.reason = reason
                rec.finished_at = self._utc_now()
            self._logs.run_event(run_id, "run_execution_interrupted", {"reason": reason}, level="WARN")
            self._logs.write_run_summary(
                run_id,
                {
                    "run_id": run_id,
                    "status": status,
                    "trigger": context.manifest.get("trigger", ""),
                    "target_profile": context.manifest.get("target_profile", ""),
                    "scenario": context.manifest.get("scenario", ""),
                    "reason": reason,
                },
            )
            self._logs.write_run_diagnostics(
                run_id,
                {
                    "run_id": run_id,
                    "status": status,
                    "state": context.state,
                    "context_id": context.active_context_id,
                    "controller_id": context.layered_state.controller_layer.active_controller_id,
                    "reason": reason,
                    "last_error": context.last_error,
                },
            )
            self._event_bus.publish(
                Event(type="RUN.INTERRUPTED", source="executor", run_id=run_id, payload={"reason": reason})
            )
            self._event_bus.dispatch_once()
        except Exception as exc:
            rec = self._records.get(run_id)
            if rec is not None:
                rec.status = "failed"
                rec.reason = str(exc) or f"{type(exc).__name__}"
                rec.finished_at = self._utc_now()
            self._logs.run_event(
                run_id,
                "run_execution_failed",
                {
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "error_repr": repr(exc),
                    "traceback": traceback.format_exc(),
                },
                level="ERROR",
            )
            self._logs.write_run_summary(
                run_id,
                {
                    "run_id": run_id,
                    "status": "failed",
                    "trigger": context.manifest.get("trigger", ""),
                    "target_profile": context.manifest.get("target_profile", ""),
                    "scenario": context.manifest.get("scenario", ""),
                    "reason": str(exc) or f"{type(exc).__name__}",
                },
            )
            self._logs.write_run_diagnostics(
                run_id,
                {
                    "run_id": run_id,
                    "status": "failed",
                    "state": context.state,
                    "context_id": context.active_context_id,
                    "controller_id": context.layered_state.controller_layer.active_controller_id,
                    "reason": str(exc) or f"{type(exc).__name__}",
                    "error_type": type(exc).__name__,
                    "error_repr": repr(exc),
                    "traceback": traceback.format_exc(),
                    "last_error": context.last_error,
                },
            )
            self._event_bus.publish(
                Event(
                    type="RUN.FAILED",
                    source="executor",
                    run_id=run_id,
                    payload={"error": str(exc), "error_type": type(exc).__name__},
                )
            )
            self._event_bus.dispatch_once()
        finally:
            self._persist_state()
            self._signals.cleanup_run(run_id)
            self._workers.pop(run_id, None)
            if self._concurrency_mode == "single":
                with self._active_run_lock:
                    if self._active_run_id == run_id:
                        self._active_run_id = None

    def start_run(self, request: RunRequest) -> RunReceipt:
        self._logs.system_event(
            "run_request_received",
            {
                "trigger": request.trigger,
                "idempotency_key": request.idempotency_key,
                "target_profile": request.target_profile,
                "scenario": request.scenario,
                "requested_policy_override": request.requested_policy_override,
            },
        )
        if request.idempotency_key in self._idempotency_map:
            existing_run_id = self._idempotency_map[request.idempotency_key]
            self._logs.run_event(
                existing_run_id,
                "run_request_idempotent_reuse",
                {"idempotency_key": request.idempotency_key},
            )
            return RunReceipt(run_id=existing_run_id, accepted=True, reason="idempotent_reuse")

        if self._concurrency_mode == "single":
            with self._active_run_lock:
                if self._active_run_id is not None:
                    self._logs.system_event(
                        "run_request_rejected",
                        {"reason": "run_in_progress", "active_run_id": self._active_run_id},
                        level="WARN",
                    )
                    return RunReceipt(run_id="", accepted=False, reason="run_in_progress")

                run_id = str(uuid.uuid4())
                self._active_run_id = run_id
        else:
            run_id = str(uuid.uuid4())

        try:
            effective_overrides = self._command_source.fetch_effective_overrides()
            effective_overrides.update(request.requested_policy_override)
            effective_policy = EffectivePolicy(profile={}, overrides=effective_overrides).materialize()
            workflow_plan = self._profiles.build_plan(request)

            manifest = RunManifest.build(
                run_id=run_id,
                trigger=request.trigger,
                target_profile=request.target_profile,
                scenario=request.scenario,
                workflow_plan=workflow_plan.to_dict(),
                effective_policy=effective_policy,
            )
            manifest_path = self._manifests_dir / f"{run_id}.json"
            manifest_path.write_text(json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
            self._logs.run_event(
                run_id,
                "run_manifest_written",
                {
                    "manifest_path": str(manifest_path),
                    "trigger": request.trigger,
                    "target_profile": request.target_profile,
                    "scenario": request.scenario,
                },
            )
            self._logs.action_event(
                run_id,
                "profile_plan_resolved",
                "ok",
                {
                    "profile": workflow_plan.profile,
                    "game": workflow_plan.game,
                    "scenario": workflow_plan.scenario,
                    "mode": workflow_plan.mode,
                    "steps": [s.name for s in workflow_plan.steps],
                    "states": [n.state for n in workflow_plan.state_plan.nodes] if workflow_plan.state_plan else [],
                },
            )

            ctx = RunContext(run_id=run_id, manifest=manifest.to_dict(), state="BOOTSTRAP")
            self._contexts.put(ctx)
            checkpoint_path = self._checkpoints.save(ctx)
            self._logs.run_event(
                run_id,
                "run_checkpoint_written",
                {"checkpoint_path": str(checkpoint_path), "state": ctx.state},
            )

            self._event_bus.publish(
                Event(
                    type="RUN.ACCEPTED",
                    source="orchestrator",
                    run_id=run_id,
                    payload={
                        "trigger": request.trigger,
                        "target_profile": request.target_profile,
                        "scenario": request.scenario,
                    },
                )
            )
            self._event_bus.dispatch_once()

            self._idempotency_map[request.idempotency_key] = run_id
            self._records[run_id] = RunRecord(
                run_id=run_id,
                status="accepted",
                reason="accepted",
                target_profile=request.target_profile,
                scenario=request.scenario,
                created_at=self._utc_now(),
            )
            self._persist_state()
            self._signals.init_run(run_id)

            self._notify.notify(
                "run accepted",
                (
                    f"run_id={run_id} trigger={request.trigger} "
                    f"profile={request.target_profile} scenario={request.scenario}"
                ),
            )

            worker = threading.Thread(
                target=self._execute_run,
                args=(run_id, ctx, workflow_plan.to_dict()),
                daemon=True,
            )
            self._workers[run_id] = worker
            worker.start()

            return RunReceipt(run_id=run_id, accepted=True, reason="accepted")
        except Exception as exc:
            self._logs.system_event(
                "run_request_failed",
                {
                    "trigger": request.trigger,
                    "idempotency_key": request.idempotency_key,
                    "target_profile": request.target_profile,
                    "scenario": request.scenario,
                    "error": str(exc),
                },
                level="ERROR",
            )
            if self._concurrency_mode == "single":
                with self._active_run_lock:
                    if self._active_run_id == run_id:
                        self._active_run_id = None
            raise

    def get_run(self, run_id: str) -> RunRecord | None:
        return self._records.get(run_id)

    def list_runs(self) -> list[RunRecord]:
        return list(self._records.values())

    def active_run_id(self) -> str | None:
        with self._active_run_lock:
            return self._active_run_id

    def interrupt_run(self, run_id: str, reason: str = "manual_interrupt") -> bool:
        ok = self._signals.interrupt(run_id, reason)
        if ok:
            self._logs.run_event(run_id, "run_interrupt_requested", {"reason": reason}, level="WARN")
            self._event_bus.publish(
                Event(type="RUN.INTERRUPT_REQUESTED", source="control_api", run_id=run_id, payload={"reason": reason})
            )
            self._event_bus.dispatch_once()
        return ok

    def risk_stop_run(self, run_id: str, reason: str = "risk_detected") -> bool:
        ok = self._signals.risk_stop(run_id, reason)
        if ok:
            self._logs.run_event(run_id, "run_risk_stop_requested", {"reason": reason}, level="WARN")
            self._event_bus.publish(
                Event(type="RUN.RISK_STOP_REQUESTED", source="risk_guard", run_id=run_id, payload={"reason": reason})
            )
            self._event_bus.dispatch_once()
        return ok

    def wait_run(self, run_id: str, timeout_seconds: float | None = None) -> bool:
        worker = self._workers.get(run_id)
        if worker is None:
            return True
        worker.join(timeout=timeout_seconds)
        alive = worker.is_alive()
        if not alive:
            self._workers.pop(run_id, None)
        return not alive
