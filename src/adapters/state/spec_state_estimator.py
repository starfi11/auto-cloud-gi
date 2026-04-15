from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any

from src.adapters.perception import ElementResolver, FrameContext
from src.adapters.runtime.ui_macro import build_ui_backend
from src.domain.perception import PerceptionCandidate, PerceptionResult
from src.domain.state_kernel import StateEstimate
from src.domain.workflow import StateNode, WorkflowPlan
from src.kernel.context_store import RunContext
from src.ports.state_estimator_port import StateEstimatorPort


@dataclass
class _NodeEval:
    state: str
    confidence: float
    matched: int
    total: int
    evidence_refs: list[str]
    detail: str


@dataclass
class _CondEval:
    ok: bool
    score: float
    matched: int
    total: int
    evidence_refs: list[str]
    detail: str


class SpecStateEstimator(StateEstimatorPort):
    """State recognizer based on declarative node.recognition.

    Supports both legacy and expression modes.

    legacy schema:
      {
        "profile": "genshin_cloud",
        "all": ["element_a", "element_b"],
        "any": ["element_x", "element_y"],
        "min_any": 1
      }

    expression schema:
      {
        "profile": "genshin_cloud",
        "expr": {
          "op": "all|any|kof|not",
          "items": [ ... ],
          "k": 2
        }
      }

    leaf schema:
      {"present": "element_id"}
      {"absent": "element_id"}
      {"type": "element_present", "id": "..."}
      {"type": "element_absent", "id": "..."}
    """

    def __init__(self) -> None:
        backend_mode = os.getenv("UI_AUTOMATION_BACKEND", "auto")
        self._backend = build_ui_backend(backend_mode)
        self._resolver = ElementResolver(self._backend)

    def estimate(
        self,
        context: RunContext,
        plan: WorkflowPlan,
        expected_states: list[str] | None = None,
    ) -> StateEstimate:
        sp = plan.state_plan
        if sp is None:
            return StateEstimate(
                state=context.state or "BOOTSTRAP",
                confidence=1.0,
                signals={"source": "context"},
                uncertainty_reason="",
            )

        # Single frame shared across all node evaluations this tick: one
        # full screenshot, per-ROI crop cache, per-(ROI,ocr_key) OCR cache,
        # per-element resolve cache.
        frame = FrameContext(self._backend)

        # Narrow-scan filter: evaluate only the expected_states set (plus
        # current state implicitly — caller should include it if desired).
        # None means broad scan.
        if expected_states is None:
            nodes_to_eval = sp.nodes
            scan_mode = "broad"
        else:
            wanted = set(expected_states)
            nodes_to_eval = [n for n in sp.nodes if n.state in wanted]
            scan_mode = "narrow"

        evals: list[_NodeEval] = []
        candidates: list[PerceptionCandidate] = []
        all_evidence: list[str] = []
        has_any_recognition = False

        for node in nodes_to_eval:
            if node.recognition:
                has_any_recognition = True
            ev = self._evaluate_node(node, frame)
            evals.append(ev)
            candidates.append(
                PerceptionCandidate(
                    label=node.state,
                    confidence=ev.confidence,
                    kind="state",
                    meta={"matched": ev.matched, "total": ev.total, "detail": ev.detail},
                )
            )
            all_evidence.extend(ev.evidence_refs)

        if not evals or not has_any_recognition:
            return StateEstimate(
                state=context.state or sp.initial_state,
                confidence=1.0,
                signals={"source": "context_fallback", "scan_mode": scan_mode},
                uncertainty_reason="",
            )

        best = max(evals, key=lambda e: e.confidence)
        frame_stats = frame.stats()
        if best.confidence <= 0.01:
            return StateEstimate(
                state=context.state or sp.initial_state,
                confidence=0.3,
                signals={
                    "source": "fallback_context",
                    "current": context.state,
                    "scan_mode": scan_mode,
                    "nodes_evaluated": len(evals),
                    "ocr_calls": frame_stats["ocr_calls"],
                },
                perception=PerceptionResult(
                    ok=False,
                    scene_id="state_recognition",
                    candidates=candidates,
                    evidence_refs=all_evidence[:40],
                    uncertainty_reason="no_node_confident_match",
                ),
                uncertainty_reason="no_node_confident_match",
            )

        return StateEstimate(
            state=best.state,
            confidence=best.confidence,
            signals={
                "source": "spec_recognizer",
                "best_state": best.state,
                "scan_mode": scan_mode,
                "nodes_evaluated": len(evals),
                "ocr_calls": frame_stats["ocr_calls"],
            },
            perception=PerceptionResult(
                ok=True,
                scene_id="state_recognition",
                candidates=candidates,
                evidence_refs=all_evidence[:40],
                uncertainty_reason="",
            ),
            uncertainty_reason="",
        )

    def _evaluate_node(self, node: StateNode, frame: FrameContext) -> _NodeEval:
        try:
            rec = node.recognition or {}
            if not rec:
                return _NodeEval(node.state, 0.0, 0, 0, [], "no_recognition")

            profile = str(rec.get("profile", "default")).strip() or "default"
            # timeout_seconds/poll_seconds in recognition dicts are legacy —
            # single-frame resolver has no wait semantics. Values are ignored.

            expr = rec.get("expr")
            if isinstance(expr, dict):
                out = self._eval_expr(expr, profile=profile, frame=frame)
                return _NodeEval(
                    state=node.state,
                    confidence=max(0.0, min(1.0, out.score)),
                    matched=out.matched,
                    total=out.total,
                    evidence_refs=out.evidence_refs,
                    detail=out.detail,
                )

            # Legacy compatibility path
            all_ids = [str(x) for x in rec.get("all", []) if str(x).strip()]
            any_ids = [str(x) for x in rec.get("any", []) if str(x).strip()]
            min_any = int(rec.get("min_any", 1)) if any_ids else 0
            if not all_ids and not any_ids:
                return _NodeEval(node.state, 0.0, 0, 0, [], "empty_legacy")

            matched_all = 0
            matched_any = 0
            evidence_refs: list[str] = []
            for eid in all_ids:
                r = self._match_present(eid, profile=profile, frame=frame)
                if r.ok:
                    matched_all += 1
                    evidence_refs.extend(r.evidence_refs)
            for eid in any_ids:
                r = self._match_present(eid, profile=profile, frame=frame)
                if r.ok:
                    matched_any += 1
                    evidence_refs.extend(r.evidence_refs)

            all_score = 1.0 if not all_ids else (matched_all / max(1, len(all_ids)))
            any_score = 1.0 if not any_ids else (matched_any / max(1, len(any_ids)))
            gated_any = 1.0 if matched_any >= min_any else any_score * 0.5
            confidence = 0.55 * all_score + 0.45 * gated_any
            matched = matched_all + matched_any
            total = len(all_ids) + len(any_ids)
            return _NodeEval(node.state, max(0.0, min(1.0, confidence)), matched, total, evidence_refs, "legacy")
        except Exception as exc:  # noqa: BLE001
            return _NodeEval(
                state=node.state,
                confidence=0.0,
                matched=0,
                total=0,
                evidence_refs=[],
                detail=f"node_eval_error:{type(exc).__name__}:{exc}",
            )

    def _eval_expr(
        self,
        expr: dict[str, Any],
        *,
        profile: str,
        frame: FrameContext,
    ) -> _CondEval:
        op = str(expr.get("op", "")).strip().lower()
        if op in {"all", "any", "kof"}:
            raw_items = expr.get("items", [])
            items = [i for i in raw_items if isinstance(i, dict)] if isinstance(raw_items, list) else []
            if not items:
                return _CondEval(False, 0.0, 0, 0, [], f"{op}_empty")
            evals = [
                self._eval_clause(i, profile=profile, frame=frame)
                for i in items
            ]
            matched = sum(1 for e in evals if e.ok)
            total = len(evals)
            evidence = [x for e in evals for x in e.evidence_refs]
            # Score = matched/total directly. The previous min(raw, 0.45)
            # cap existed to suppress phantom partial matches under broad
            # scan (e.g. `all[absent(a), absent(b), present(c)]` scoring 2/3
            # in unrelated states because the absents are trivially true).
            # Under narrow scan only legal successor states are evaluated,
            # so a partial match is genuine signal and the cap no longer
            # helps — it just creates a dead zone between 0.4 and 0.75.
            raw = matched / max(1, total)
            if op == "all":
                ok = matched == total
                return _CondEval(ok, raw, matched, total, evidence, f"all:{matched}/{total}")
            if op == "any":
                ok = matched >= 1
                return _CondEval(ok, raw, matched, total, evidence, f"any:{matched}/{total}")
            k = int(expr.get("k", 1))
            ok = matched >= k
            return _CondEval(ok, raw, matched, total, evidence, f"kof:{matched}/{total},k={k}")

        if op == "not":
            item = expr.get("item")
            if not isinstance(item, dict):
                return _CondEval(False, 0.0, 0, 1, [], "not_missing_item")
            inner = self._eval_clause(item, profile=profile, frame=frame)
            return _CondEval(not inner.ok, 1.0 if not inner.ok else 0.0, 1 if not inner.ok else 0, 1, inner.evidence_refs, "not")

        return self._eval_clause(expr, profile=profile, frame=frame)

    def _eval_clause(
        self,
        clause: dict[str, Any],
        *,
        profile: str,
        frame: FrameContext,
    ) -> _CondEval:
        # nested expression
        if "op" in clause:
            return self._eval_expr(clause, profile=profile, frame=frame)

        present = str(clause.get("present", "")).strip()
        absent = str(clause.get("absent", "")).strip()
        ctype = str(clause.get("type", "")).strip().lower()
        cid = str(clause.get("id", "")).strip()

        if ctype == "element_present" and cid:
            present = cid
        if ctype == "element_absent" and cid:
            absent = cid

        if present:
            r = self._match_present(present, profile=profile, frame=frame)
            return _CondEval(r.ok, 1.0 if r.ok else 0.0, 1 if r.ok else 0, 1, r.evidence_refs, f"present:{present}")
        if absent:
            r = self._match_present(absent, profile=profile, frame=frame)
            ok = not r.ok
            return _CondEval(ok, 1.0 if ok else 0.0, 1 if ok else 0, 1, r.evidence_refs, f"absent:{absent}")

        return _CondEval(False, 0.0, 0, 1, [], "unknown_clause")

    def _match_present(self, element_id: str, *, profile: str, frame: FrameContext):
        return self._resolver.resolve_once(
            element_id=element_id,
            profile=profile,
            frame=frame,
        )
