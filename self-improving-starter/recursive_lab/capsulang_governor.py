"""Fail-closed host bridge for an optional Capsulang promotion governor.

Capsulang checks and advances the lifecycle machine.  This module deliberately
does not execute the returned effect intents; the Python host records them as
evidence and retains authority over repositories, evaluators, and deployment.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from typing import Any, Callable, Mapping

from .governance import EvaluationEvidence, PromotionDecision


class CapsulangGovernorError(RuntimeError):
    """The external governor could not produce trusted, matching evidence."""


@dataclass(frozen=True, slots=True)
class PromotionEvidence:
    benchmark_admitted: bool
    gain_bps: int
    external_regret_bps: int
    parity_checked: bool

    def __post_init__(self) -> None:
        for name in ("benchmark_admitted", "parity_checked"):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"{name} must be a bool")
        for name in ("gain_bps", "external_regret_bps"):
            if type(getattr(self, name)) is not int:
                raise TypeError(f"{name} must be an integer")

    @property
    def host_promotes(self) -> bool:
        return (
            self.benchmark_admitted
            and self.parity_checked
            and self.gain_bps > 0
            and self.external_regret_bps >= 0
        )

    def to_dict(self) -> dict[str, bool | int]:
        return {
            "benchmark_admitted": self.benchmark_admitted,
            "gain_bps": self.gain_bps,
            "external_regret_bps": self.external_regret_bps,
            "parity_checked": self.parity_checked,
        }


@dataclass(frozen=True, slots=True)
class GovernorReceipt:
    semantic_hash: str
    decision: str
    final_state: str
    evidence: PromotionEvidence
    effect_intents: tuple[str, ...]
    transitions: tuple[tuple[str, str, str], ...]

    @property
    def promoted(self) -> bool:
        return self.decision == "promote"

    def to_dict(self) -> dict[str, Any]:
        return {
            "semantic_hash": self.semantic_hash,
            "decision": self.decision,
            "final_state": self.final_state,
            "evidence": self.evidence.to_dict(),
            "effect_intents": list(self.effect_intents),
            "transitions": [
                {"from": source, "event": event, "to": target}
                for source, event, target in self.transitions
            ],
        }


class CapsulangGovernor:
    """Advance a pinned Capsulang machine and return non-executed intents."""

    def __init__(
        self,
        capsule: Path,
        *,
        expected_semantic_hash: str,
        executable: str = "caps",
        timeout_seconds: float = 15.0,
        decision_mode: str = "scenario",
    ) -> None:
        if not isinstance(capsule, Path):
            raise TypeError("capsule must be a Path")
        if (
            len(expected_semantic_hash) != 64
            or any(character not in "0123456789abcdef" for character in expected_semantic_hash)
        ):
            raise ValueError("expected_semantic_hash must be a SHA-256 hex digest")
        if not executable:
            raise ValueError("executable must be non-empty")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if decision_mode not in {"scenario", "legacy-step"}:
            raise ValueError("decision_mode must be 'scenario' or 'legacy-step'")
        self._capsule = capsule.resolve()
        self._expected_semantic_hash = expected_semantic_hash
        self._executable = executable
        self._timeout_seconds = float(timeout_seconds)
        self._decision_mode = decision_mode
        try:
            self._source_hash = hashlib.sha256(self._capsule.read_bytes()).hexdigest()
        except OSError as error:
            raise CapsulangGovernorError(f"cannot read Capsulang capsule: {error}") from error
        self._pin_verified = False

    @property
    def semantic_hash(self) -> str:
        return self._expected_semantic_hash

    @property
    def decision_mode(self) -> str:
        return self._decision_mode

    def _invoke(self, *arguments: str, expect_success: bool = True) -> Mapping[str, Any]:
        try:
            completed = subprocess.run(
                [self._executable, *arguments],
                check=False,
                capture_output=True,
                text=True,
                timeout=self._timeout_seconds,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as error:
            raise CapsulangGovernorError(f"Capsulang unavailable: {error}") from error
        raw = completed.stdout or completed.stderr
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, TypeError) as error:
            raise CapsulangGovernorError("Capsulang returned invalid JSON") from error
        if not isinstance(payload, dict):
            raise CapsulangGovernorError("Capsulang returned a non-object result")
        if expect_success and completed.returncode != 0:
            codes = [
                item.get("code", "unknown")
                for item in payload.get("diagnostics", [])
                if isinstance(item, dict)
            ]
            raise CapsulangGovernorError(
                f"Capsulang rejected the transition: {', '.join(codes) or 'unknown'}"
            )
        return payload

    def _step(
        self,
        event: str,
        *,
        state: str,
        context: Mapping[str, object],
        payload: Mapping[str, object] | None = None,
    ) -> Mapping[str, Any]:
        arguments = [
            "machine-step",
            str(self._capsule),
            "RecursivePromotion",
            event,
            "--state",
            state,
            "--context",
            json.dumps(context, sort_keys=True, separators=(",", ":")),
        ]
        if payload is not None:
            arguments.extend(
                ["--payload", json.dumps(payload, sort_keys=True, separators=(",", ":"))]
            )
        arguments.append("--json")
        result = self._invoke(*arguments)
        if result.get("from") != state or result.get("event") != event:
            raise CapsulangGovernorError("Capsulang transition identity mismatch")
        return result

    def _verify_pin(self) -> None:
        try:
            current_source_hash = hashlib.sha256(self._capsule.read_bytes()).hexdigest()
        except OSError as error:
            raise CapsulangGovernorError(f"cannot read Capsulang capsule: {error}") from error
        if current_source_hash != self._source_hash:
            raise CapsulangGovernorError("Capsulang source changed after governor creation")
        if self._pin_verified:
            return
        graph = self._invoke("agent-graph", "--json", str(self._capsule))
        if graph.get("semanticHash") != self._expected_semantic_hash:
            raise CapsulangGovernorError(
                "Capsulang semantic hash differs from the pinned governor"
            )
        self._pin_verified = True

    @staticmethod
    def _receipt(
        evidence: PromotionEvidence,
        *,
        semantic_hash: str,
        steps: tuple[Mapping[str, Any], ...],
    ) -> GovernorReceipt:
        decision = "promote" if evidence.host_promotes else "reject"
        expected_state = "promoted" if decision == "promote" else "quarantined"
        if len(steps) != 3 or steps[-1].get("to") != expected_state:
            raise CapsulangGovernorError("Capsulang decision disagrees with host policy")
        if steps[1].get("context") != evidence.to_dict():
            raise CapsulangGovernorError("Capsulang altered or omitted evaluation evidence")
        expected_events = ("Propose", "Evidence", decision.title())
        if tuple(step.get("event") for step in steps) != expected_events:
            raise CapsulangGovernorError("Capsulang transition sequence mismatch")
        if tuple(step.get("from") for step in steps) != (
            "idle",
            "evaluating",
            "decision",
        ):
            raise CapsulangGovernorError("Capsulang transition source mismatch")
        effects = tuple(
            f"{effect['name']}"
            + (
                ":" + ",".join(str(arg) for arg in effect.get("args", []))
                if effect.get("args")
                else ""
            )
            for step in steps
            for effect in step.get("effects", [])
        )
        transitions = tuple(
            (str(step["from"]), str(step["event"]), str(step["to"])) for step in steps
        )
        return GovernorReceipt(
            semantic_hash=semantic_hash,
            decision=decision,
            final_state=expected_state,
            evidence=evidence,
            effect_intents=effects,
            transitions=transitions,
        )

    def _decide_legacy(self, evidence: PromotionEvidence) -> GovernorReceipt:
        context: dict[str, object] = {
            "benchmark_admitted": False,
            "gain_bps": 0,
            "external_regret_bps": 0,
            "parity_checked": False,
        }
        proposal = self._step("Propose", state="idle", context=context)
        evaluated = self._step(
            "Evidence",
            state=str(proposal["to"]),
            context=context,
            payload=evidence.to_dict(),
        )
        returned_context = evaluated.get("context")
        if returned_context != evidence.to_dict():
            raise CapsulangGovernorError("Capsulang altered or omitted evaluation evidence")
        decision = "promote" if evidence.host_promotes else "reject"
        decided = self._step(
            decision.title(),
            state=str(evaluated["to"]),
            context=returned_context,
        )
        steps = (proposal, evaluated, decided)
        return self._receipt(
            evidence,
            semantic_hash=self._expected_semantic_hash,
            steps=steps,
        )

    def _decide_scenario(self, evidence: PromotionEvidence) -> GovernorReceipt:
        decision = "Promote" if evidence.host_promotes else "Reject"
        expected_state = "promoted" if evidence.host_promotes else "quarantined"
        scenario = {
            "machine": "RecursivePromotion",
            "context": {
                "benchmark_admitted": False,
                "gain_bps": 0,
                "external_regret_bps": 0,
                "parity_checked": False,
            },
            "events": [
                {"event": "Propose", "payload": {}},
                {"event": "Evidence", "payload": evidence.to_dict()},
                {"event": decision, "payload": {}},
            ],
            "expect_state": expected_state,
        }
        scenario_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                suffix=".json",
                prefix="nextai-capsulang-",
                delete=False,
            ) as handle:
                json.dump(scenario, handle, sort_keys=True, separators=(",", ":"))
                scenario_path = Path(handle.name)
            report = self._invoke(
                "test",
                str(self._capsule),
                "--scenario",
                str(scenario_path),
                "--json",
            )
        finally:
            if scenario_path is not None:
                scenario_path.unlink(missing_ok=True)
        scenario_tests = [
            test
            for test in report.get("tests", [])
            if isinstance(test, dict) and str(test.get("name", "")).startswith("scenario:")
        ]
        if (
            report.get("ok") is not True
            or len(scenario_tests) != 1
            or scenario_tests[0].get("status") != "passed"
            or scenario_tests[0].get("final_state") != expected_state
        ):
            raise CapsulangGovernorError("Capsulang scenario did not pass exactly once")
        steps = tuple(
            step["plan"]
            for step in scenario_tests[0].get("steps", [])
            if isinstance(step, dict) and isinstance(step.get("plan"), dict)
        )
        return self._receipt(
            evidence,
            semantic_hash=self._expected_semantic_hash,
            steps=steps,
        )

    def decide(self, evidence: PromotionEvidence) -> GovernorReceipt:
        if not isinstance(evidence, PromotionEvidence):
            raise TypeError("evidence must be PromotionEvidence")
        self._verify_pin()
        if self._decision_mode == "legacy-step":
            return self._decide_legacy(evidence)
        return self._decide_scenario(evidence)


class CapsulangPromotionCorroborator:
    """Adapt the machine bridge to StrategyLab's promotion-governor protocol."""

    def __init__(
        self,
        governor: CapsulangGovernor,
        evidence_builder: Callable[[EvaluationEvidence], PromotionEvidence],
    ) -> None:
        if not isinstance(governor, CapsulangGovernor):
            raise TypeError("governor must be a CapsulangGovernor")
        if not callable(evidence_builder):
            raise TypeError("evidence_builder must be callable")
        self._governor = governor
        self._evidence_builder = evidence_builder
        identity = (
            "recursive-lab.capsulang-corroborator.v2:"
            + governor.semantic_hash
            + ":"
            + governor.decision_mode
        )
        self.governor_digest = hashlib.sha256(identity.encode()).hexdigest()

    def corroborate(
        self,
        decision: PromotionDecision,
        evidence: EvaluationEvidence,
    ) -> Mapping[str, Any]:
        if not isinstance(decision, PromotionDecision) or not decision.promoted:
            raise TypeError("only a promoted Python decision can be corroborated")
        if not isinstance(evidence, EvaluationEvidence):
            raise TypeError("evidence must be EvaluationEvidence")
        promotion_evidence = self._evidence_builder(evidence)
        if not isinstance(promotion_evidence, PromotionEvidence):
            raise TypeError("evidence_builder must return PromotionEvidence")
        receipt = self._governor.decide(promotion_evidence)
        if not receipt.promoted:
            raise CapsulangGovernorError(
                "Capsulang did not corroborate the Python promotion decision"
            )
        return receipt.to_dict()
