"""Cross-check Capsulang governance scenarios against the experiment evidence.

The scenarios in ``capsulang/scenarios/`` drive the pinned ``RecursivePromotion``
machine declared in ``capsulang/e53_recursive_governor.caps``.  Each of them
carries a single ``Evidence`` event whose payload is a literal tuple: the machine
is *told* what the benchmark said, it never reads the benchmark.  Capsulang does
not close that gap either -- the ``(metric ... "experiments/E45-support-guard.json")``
bindings in the objective and eval-suite are declarative.  ``caps check`` reports
``checked`` and ``caps improvement-report`` reports ``improvement-governed`` even
when those paths point at files that do not exist, and the objective obligation
stays at status ``declared``.  Nothing in the toolchain ever opens an experiment
report.

That matters because this repository already stores the measurements those
literals claim to represent, and at least one of them disagrees.
``experiments/E51-benchmark-admission.json`` records ``"admitted": false`` with
``"decision": "reject and redesign cohort"``, while
``capsulang/scenarios/e45_promote.json`` asserts ``benchmark_admitted: true`` and
expects the ``promoted`` terminal state.  The showcase promotion path therefore
asserts as evidence a fact the project's own audit refuted, and a scenario suite
built that way can only confirm that the machine promotes when it is handed a
promotable tuple.  It cannot say whether the evidence supports promoting.

This module closes the loop from the outside, without touching the immutable
evidence chain and without changing any existing runner:

* every scenario must appear in :data:`SCENARIO_BINDINGS`, so an unreviewed
  governance fixture cannot be added silently;
* every ``Evidence`` field is either :class:`Measured` -- pinned to a key in a
  named ``experiments/E*.json`` report -- or :class:`Declared`, a scenario-local
  literal that must carry a written justification and still match exactly;
* every cited experiment report must reproduce its own ``report_digest``, so the
  checker cannot be satisfied by editing the evidence it reads;
* every scenario's ``expect_state`` must agree with the immutable host policy in
  :class:`recursive_lab.capsulang_governor.PromotionEvidence`, which is the same
  conjunction the machine guard evaluates;
* at least one fully measured scenario must end outside ``promoted``, so the
  suite always contains a demonstration that the governor refuses a promotion on
  real evidence rather than only ever granting one.

A scenario that diverges from a :class:`Measured` source is a *contradiction* and
fails the run.  A scenario may instead declare itself hypothetical in its own
JSON (``"evidence_status": "hypothetical"`` plus a non-empty ``claim_boundary``);
its divergences are then downgraded to *assumptions*, still printed on every run
and still failing under ``--strict``.  That is deliberately not a silent
exemption: ``e45_promote.json`` demonstrates the ``Promote`` transition under an
assumed admitted benchmark, and this checker makes the assumption impossible to
mistake for a measurement.

Run ``python3 verify_capsulang_evidence.py`` (add ``--strict`` to fail on
assumptions too, or ``--json`` for a machine-readable report).  The exit code is
non-zero whenever the governance layer's claims and the evidence chain disagree.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import hashlib
import json
from numbers import Real
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

from recursive_lab.capsulang_governor import PromotionEvidence  # noqa: E402


ROOT = Path(__file__).resolve().parent
SCENARIO_DIRECTORY = ROOT / "capsulang" / "scenarios"
EXPERIMENT_DIRECTORY = ROOT / "experiments"

EVIDENCE_FIELDS = (
    "benchmark_admitted",
    "gain_bps",
    "external_regret_bps",
    "parity_checked",
)
BASIS_POINTS = 10_000

CONTRADICTION = "contradiction"
ASSUMPTION = "assumption"


class EvidenceConsistencyError(RuntimeError):
    """The checker itself could not be run against a trustworthy input."""


@dataclass(frozen=True, slots=True)
class Measured:
    """An evidence field pinned to a key in an immutable experiment report.

    ``basis_points`` reads a fractional measurement (for example
    ``macro_target_hit_rate_delta``) and converts it to the integer basis points
    the machine context uses; otherwise the stored value must already be a bool.
    """

    experiment: str
    key: str
    basis_points: bool = False

    @property
    def source(self) -> str:
        return f"experiments/{self.experiment}#{self.key}"

    def resolve(self, report: Mapping[str, Any]) -> bool | int:
        if self.key not in report:
            raise EvidenceConsistencyError(
                f"{self.source} is missing from the experiment report"
            )
        value = report[self.key]
        if self.basis_points:
            if isinstance(value, bool) or not isinstance(value, Real):
                raise EvidenceConsistencyError(
                    f"{self.source} must be a real number, not {type(value).__name__}"
                )
            return round(float(value) * BASIS_POINTS)
        if not isinstance(value, bool):
            raise EvidenceConsistencyError(
                f"{self.source} must be a bool, not {type(value).__name__}"
            )
        return value


@dataclass(frozen=True, slots=True)
class Declared:
    """A scenario-local literal that must carry a written justification."""

    value: bool | int
    reason: str

    def __post_init__(self) -> None:
        if type(self.value) not in (bool, int):
            raise EvidenceConsistencyError("Declared.value must be a bool or an int")
        if not self.reason.strip():
            raise EvidenceConsistencyError("Declared.reason must be non-empty")

    @property
    def source(self) -> str:
        return f"declared literal ({self.reason})"


Binding = Measured | Declared


@dataclass(frozen=True, slots=True)
class ScenarioBinding:
    """How one governance scenario is allowed to justify its evidence payload."""

    purpose: str
    fields: Mapping[str, Binding]
    hypothetical: bool = False

    def __post_init__(self) -> None:
        if not self.purpose.strip():
            raise EvidenceConsistencyError("ScenarioBinding.purpose must be non-empty")
        if tuple(sorted(self.fields)) != tuple(sorted(EVIDENCE_FIELDS)):
            raise EvidenceConsistencyError(
                "ScenarioBinding.fields must bind exactly the evidence fields "
                f"{sorted(EVIDENCE_FIELDS)}"
            )

    @property
    def fully_measured(self) -> bool:
        return not self.hypothetical and all(
            isinstance(binding, Measured) for binding in self.fields.values()
        )


SCENARIO_BINDINGS: Mapping[str, ScenarioBinding] = {
    "e45_promote.json": ScenarioBinding(
        purpose=(
            "demonstrate the Promote transition under an assumed admitted "
            "benchmark; E51 refuted that assumption for the real cohort"
        ),
        hypothetical=True,
        fields={
            "benchmark_admitted": Measured("E51-benchmark-admission.json", "admitted"),
            "gain_bps": Measured(
                "E45-support-guard.json",
                "macro_target_hit_rate_delta",
                basis_points=True,
            ),
            "external_regret_bps": Measured(
                "E45-support-guard.json",
                "external_domain_regret",
                basis_points=True,
            ),
            "parity_checked": Measured("E52-metta-parity.json", "decision_parity"),
        },
    ),
    "e51_quarantine.json": ScenarioBinding(
        purpose=(
            "quarantine an inadmissible benchmark that also claims no gain"
        ),
        fields={
            "benchmark_admitted": Measured("E51-benchmark-admission.json", "admitted"),
            "gain_bps": Declared(
                0,
                "this fixture withholds any gain claim; the measured E45 gain is "
                "exercised by e51_real_evidence_quarantine.json instead",
            ),
            "external_regret_bps": Measured(
                "E45-support-guard.json",
                "external_domain_regret",
                basis_points=True,
            ),
            "parity_checked": Measured("E52-metta-parity.json", "decision_parity"),
        },
    ),
    "e51_real_evidence_quarantine.json": ScenarioBinding(
        purpose=(
            "refuse promotion on measured evidence: a real +302 bps held-out "
            "gain with checked parity is still quarantined because E51 rejected "
            "the benchmark cohort"
        ),
        fields={
            "benchmark_admitted": Measured("E51-benchmark-admission.json", "admitted"),
            "gain_bps": Measured(
                "E45-support-guard.json",
                "macro_target_hit_rate_delta",
                basis_points=True,
            ),
            "external_regret_bps": Measured(
                "E45-support-guard.json",
                "external_domain_regret",
                basis_points=True,
            ),
            "parity_checked": Measured("E52-metta-parity.json", "decision_parity"),
        },
    ),
}


@dataclass(frozen=True, slots=True)
class Finding:
    """One disagreement between the governance layer and the evidence chain."""

    severity: str
    scenario: str
    message: str
    field_name: str = ""
    scenario_value: bool | int | None = None
    evidence_value: bool | int | None = None
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "scenario": self.scenario,
            "message": self.message,
            "field": self.field_name,
            "scenario_value": self.scenario_value,
            "evidence_value": self.evidence_value,
            "source": self.source,
        }

    def describe(self) -> str:
        location = f"{self.scenario}"
        if self.field_name:
            location += f"::{self.field_name}"
        return f"[{self.severity}] {location}: {self.message}"


@dataclass(frozen=True, slots=True)
class VerificationReport:
    """The outcome of one cross-check over every governance scenario."""

    findings: tuple[Finding, ...] = ()
    scenarios_checked: tuple[str, ...] = ()
    measured_refusals: tuple[str, ...] = ()
    experiments_verified: tuple[str, ...] = ()

    @property
    def contradictions(self) -> tuple[Finding, ...]:
        return tuple(item for item in self.findings if item.severity == CONTRADICTION)

    @property
    def assumptions(self) -> tuple[Finding, ...]:
        return tuple(item for item in self.findings if item.severity == ASSUMPTION)

    def ok(self, *, strict: bool = False) -> bool:
        if self.contradictions:
            return False
        return not (strict and self.assumptions)

    def to_dict(self, *, strict: bool = False) -> dict[str, Any]:
        return {
            "ok": self.ok(strict=strict),
            "strict": strict,
            "scenarios_checked": list(self.scenarios_checked),
            "measured_refusals": list(self.measured_refusals),
            "experiments_verified": list(self.experiments_verified),
            "findings": [item.to_dict() for item in self.findings],
        }


@dataclass
class _EvidenceLoader:
    """Load experiment reports once and refuse tampered ones."""

    directory: Path
    _cache: dict[str, Mapping[str, Any]] = field(default_factory=dict)
    _verified: list[str] = field(default_factory=list)

    @property
    def verified(self) -> tuple[str, ...]:
        return tuple(sorted(self._verified))

    def load(self, name: str) -> Mapping[str, Any]:
        cached = self._cache.get(name)
        if cached is not None:
            return cached
        path = self.directory / name
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as error:
            raise EvidenceConsistencyError(
                f"cannot read cited evidence experiments/{name}: {error}"
            ) from error
        try:
            report = json.loads(raw)
        except json.JSONDecodeError as error:
            raise EvidenceConsistencyError(
                f"experiments/{name} is not valid JSON: {error}"
            ) from error
        if not isinstance(report, dict):
            raise EvidenceConsistencyError(f"experiments/{name} is not a JSON object")
        stored_digest = report.get("report_digest")
        if not isinstance(stored_digest, str):
            raise EvidenceConsistencyError(
                f"experiments/{name} has no report_digest to verify"
            )
        body = {key: value for key, value in report.items() if key != "report_digest"}
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
        recomputed = hashlib.sha256(canonical.encode()).hexdigest()
        if recomputed != stored_digest:
            raise EvidenceConsistencyError(
                f"experiments/{name} does not reproduce its report_digest "
                f"({stored_digest} recorded, {recomputed} recomputed); the cited "
                "evidence has been altered"
            )
        self._cache[name] = report
        self._verified.append(name)
        return report


def _read_scenario(path: Path) -> Mapping[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as error:
        raise EvidenceConsistencyError(
            f"cannot read scenario {path.name}: {error}"
        ) from error
    try:
        scenario = json.loads(raw)
    except json.JSONDecodeError as error:
        raise EvidenceConsistencyError(
            f"scenario {path.name} is not valid JSON: {error}"
        ) from error
    if not isinstance(scenario, dict):
        raise EvidenceConsistencyError(f"scenario {path.name} is not a JSON object")
    return scenario


def _evidence_events(scenario: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    events = scenario.get("events")
    if not isinstance(events, list) or not events:
        raise EvidenceConsistencyError(f"scenario {name} declares no events")
    payloads = [
        item.get("payload")
        for item in events
        if isinstance(item, dict) and item.get("event") == "Evidence"
    ]
    if len(payloads) != 1:
        raise EvidenceConsistencyError(
            f"scenario {name} must carry exactly one Evidence event, "
            f"found {len(payloads)}"
        )
    payload = payloads[0]
    if not isinstance(payload, dict):
        raise EvidenceConsistencyError(
            f"scenario {name} has a non-object Evidence payload"
        )
    if tuple(sorted(payload)) != tuple(sorted(EVIDENCE_FIELDS)):
        raise EvidenceConsistencyError(
            f"scenario {name} Evidence payload must contain exactly "
            f"{sorted(EVIDENCE_FIELDS)}, found {sorted(payload)}"
        )
    return payload


def _promotion_evidence(payload: Mapping[str, Any], name: str) -> PromotionEvidence:
    try:
        return PromotionEvidence(
            benchmark_admitted=payload["benchmark_admitted"],
            gain_bps=payload["gain_bps"],
            external_regret_bps=payload["external_regret_bps"],
            parity_checked=payload["parity_checked"],
        )
    except TypeError as error:
        raise EvidenceConsistencyError(
            f"scenario {name} Evidence payload is ill-typed: {error}"
        ) from error


def _terminal_event(scenario: Mapping[str, Any], name: str) -> str:
    events = scenario.get("events")
    if not isinstance(events, list) or not events:
        raise EvidenceConsistencyError(f"scenario {name} declares no events")
    last = events[-1]
    if not isinstance(last, dict) or not isinstance(last.get("event"), str):
        raise EvidenceConsistencyError(f"scenario {name} has an unnamed final event")
    return str(last["event"])


def _check_declaration(
    scenario: Mapping[str, Any],
    name: str,
    binding: ScenarioBinding,
) -> list[Finding]:
    declared_status = scenario.get("evidence_status")
    boundary = scenario.get("claim_boundary")
    findings: list[Finding] = []
    if binding.hypothetical:
        if declared_status != "hypothetical":
            findings.append(
                Finding(
                    CONTRADICTION,
                    name,
                    "scenario is reviewed as hypothetical but does not declare "
                    '"evidence_status": "hypothetical" in its own JSON, so a '
                    "reader cannot tell its evidence is assumed",
                )
            )
        if not isinstance(boundary, str) or not boundary.strip():
            findings.append(
                Finding(
                    CONTRADICTION,
                    name,
                    "a hypothetical scenario must carry a non-empty claim_boundary "
                    "explaining which evidence it assumes rather than measures",
                )
            )
    elif declared_status == "hypothetical":
        findings.append(
            Finding(
                CONTRADICTION,
                name,
                'scenario declares "evidence_status": "hypothetical" but is '
                "registered as evidence-bound; the two must not disagree",
            )
        )
    return findings


def _check_fields(
    name: str,
    binding: ScenarioBinding,
    payload: Mapping[str, Any],
    loader: _EvidenceLoader,
) -> list[Finding]:
    severity = ASSUMPTION if binding.hypothetical else CONTRADICTION
    findings: list[Finding] = []
    for field_name in EVIDENCE_FIELDS:
        rule = binding.fields[field_name]
        actual = payload[field_name]
        if isinstance(rule, Declared):
            expected: bool | int = rule.value
            mismatch_severity = CONTRADICTION
        else:
            expected = rule.resolve(loader.load(rule.experiment))
            mismatch_severity = severity
        if type(actual) is not type(expected) or actual != expected:
            findings.append(
                Finding(
                    mismatch_severity,
                    name,
                    f"scenario asserts {field_name}={actual!r} but {rule.source} "
                    f"gives {expected!r}",
                    field_name=field_name,
                    scenario_value=actual,
                    evidence_value=expected,
                    source=rule.source,
                )
            )
    return findings


def _check_terminal_state(
    name: str,
    scenario: Mapping[str, Any],
    evidence: PromotionEvidence,
) -> list[Finding]:
    findings: list[Finding] = []
    expected_state = "promoted" if evidence.host_promotes else "quarantined"
    expected_event = "Promote" if evidence.host_promotes else "Reject"
    declared_state = scenario.get("expect_state")
    if declared_state != expected_state:
        findings.append(
            Finding(
                CONTRADICTION,
                name,
                f"scenario expects final state {declared_state!r} but the host "
                f"promotion policy on this payload yields {expected_state!r}",
            )
        )
    terminal_event = _terminal_event(scenario, name)
    if terminal_event != expected_event:
        findings.append(
            Finding(
                CONTRADICTION,
                name,
                f"scenario ends with {terminal_event!r} but the host promotion "
                f"policy on this payload yields {expected_event!r}",
            )
        )
    if scenario.get("machine") != "RecursivePromotion":
        findings.append(
            Finding(
                CONTRADICTION,
                name,
                "scenario does not drive the RecursivePromotion machine",
            )
        )
    return findings


def verify(
    *,
    scenario_directory: Path = SCENARIO_DIRECTORY,
    experiment_directory: Path = EXPERIMENT_DIRECTORY,
    bindings: Mapping[str, ScenarioBinding] = SCENARIO_BINDINGS,
) -> VerificationReport:
    """Cross-check every governance scenario against the evidence it cites."""

    if not scenario_directory.is_dir():
        raise EvidenceConsistencyError(
            f"scenario directory {scenario_directory} does not exist"
        )
    loader = _EvidenceLoader(experiment_directory)
    on_disk = sorted(path.name for path in scenario_directory.glob("*.json"))
    findings: list[Finding] = []
    checked: list[str] = []
    measured_refusals: list[str] = []

    for name in sorted(set(on_disk) | set(bindings)):
        binding = bindings.get(name)
        path = scenario_directory / name
        if binding is None:
            findings.append(
                Finding(
                    CONTRADICTION,
                    name,
                    "governance scenario has no registered evidence binding in "
                    "verify_capsulang_evidence.SCENARIO_BINDINGS; every scenario "
                    "must state which experiment reports justify its payload",
                )
            )
            continue
        if not path.is_file():
            findings.append(
                Finding(
                    CONTRADICTION,
                    name,
                    "registered governance scenario is missing from "
                    f"{scenario_directory}",
                )
            )
            continue
        checked.append(name)
        scenario = _read_scenario(path)
        payload = _evidence_events(scenario, name)
        evidence = _promotion_evidence(payload, name)
        findings.extend(_check_declaration(scenario, name, binding))
        findings.extend(_check_fields(name, binding, payload, loader))
        findings.extend(_check_terminal_state(name, scenario, evidence))
        if binding.fully_measured and not evidence.host_promotes:
            measured_refusals.append(name)

    if not measured_refusals:
        findings.append(
            Finding(
                CONTRADICTION,
                "capsulang/scenarios",
                "no scenario refuses promotion on fully measured evidence; the "
                "governor suite would only ever demonstrate granting a promotion",
            )
        )

    return VerificationReport(
        findings=tuple(findings),
        scenarios_checked=tuple(checked),
        measured_refusals=tuple(measured_refusals),
        experiments_verified=loader.verified,
    )


def _render(report: VerificationReport, *, strict: bool) -> str:
    lines = [
        f"scenarios checked: {len(report.scenarios_checked)} "
        f"({', '.join(report.scenarios_checked) or 'none'})",
        f"experiment reports verified: "
        f"{', '.join(report.experiments_verified) or 'none'}",
        f"measured-evidence refusals: "
        f"{', '.join(report.measured_refusals) or 'none'}",
    ]
    for finding in report.findings:
        lines.append(finding.describe())
    lines.append(
        f"contradictions={len(report.contradictions)} "
        f"assumptions={len(report.assumptions)} strict={strict} "
        f"ok={report.ok(strict=strict)}"
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--strict",
        action="store_true",
        help="fail on declared assumptions as well as contradictions",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="emit the report as JSON",
    )
    arguments = parser.parse_args(argv)
    try:
        report = verify()
    except EvidenceConsistencyError as error:
        print(f"[fatal] {error}", file=sys.stderr)
        return 2
    if arguments.as_json:
        print(json.dumps(report.to_dict(strict=arguments.strict), sort_keys=True))
    else:
        print(_render(report, strict=arguments.strict))
    return 0 if report.ok(strict=arguments.strict) else 1


if __name__ == "__main__":
    raise SystemExit(main())
