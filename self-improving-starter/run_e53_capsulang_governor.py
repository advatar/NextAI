"""E53: validate Capsulang as a checked outer governor for recursive improvement."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from compare_selection import _atomic_json

ROOT = Path(__file__).parent
CAPSULE = ROOT / "capsulang" / "e53_recursive_governor.caps"
SCENARIOS = {
    "e45_supported_gain": ROOT / "capsulang" / "scenarios" / "e45_promote.json",
    "e51_uninformative_benchmark": ROOT
    / "capsulang"
    / "scenarios"
    / "e51_quarantine.json",
}


def caps_json(*args: str) -> dict:
    completed = subprocess.run(
        ["caps", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = completed.stdout or completed.stderr
    return json.loads(payload)


def caps_json_expected_failure(*args: str) -> dict:
    completed = subprocess.run(
        ["caps", *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode == 0:
        raise AssertionError(f"expected caps command to fail: {args}")
    payload = completed.stdout or completed.stderr
    return json.loads(payload)


def main() -> None:
    checked = caps_json("check", str(CAPSULE), "--json")
    governance = caps_json("improvement-report", str(CAPSULE), "--format", "json")
    graph = caps_json("agent-graph", "--json", str(CAPSULE))
    cost = caps_json("cost", "--json", str(CAPSULE))
    preview = caps_json("release-preview", "--json", str(CAPSULE))
    scenario_results = {
        name: caps_json(
            "test",
            str(CAPSULE),
            "--scenario",
            str(path),
            "--json",
        )
        for name, path in SCENARIOS.items()
    }
    rejected_promotion = caps_json_expected_failure(
        "machine-step",
        str(CAPSULE),
        "RecursivePromotion",
        "Promote",
        "--state",
        "decision",
        "--context",
        json.dumps(
            {
                "benchmark_admitted": False,
                "gain_bps": 302,
                "external_regret_bps": 0,
                "parity_checked": True,
            }
        ),
        "--json",
    )

    expected_states = {
        "e45_supported_gain": "promoted",
        "e51_uninformative_benchmark": "quarantined",
    }
    scenario_evidence = {
        name: next(
            test
            for test in result["tests"]
            if test["name"].startswith("scenario:")
        )
        for name, result in scenario_results.items()
    }
    scenario_parity = all(
        scenario_evidence[name]["final_state"] == expected
        and scenario_evidence[name]["status"] == "passed"
        for name, expected in expected_states.items()
    )
    invalid_promotion_blocked = any(
        diagnostic["code"] == "E_GUARD_REJECTED"
        for diagnostic in rejected_promotion["diagnostics"]
    )
    lifecycle = governance["lifecycle"]
    governance_complete = all(lifecycle.values())
    gating = governance["surface"]["gating"]
    gate_complete = all(gating.values())
    machine = graph["symbols"]["machines"][0]
    host_boundary_explicit = all(
        any(
            diagnostic["code"] == "W_BACKEND_HOST_RUNTIME_REQUIRED"
            for diagnostic in preview["backends"][backend]["diagnostics"]
        )
        for backend in ("xstate", "scxml")
    )
    report = {
        "schema_version": 1,
        "experiment_id": "E53-capsulang-governor",
        "claim_boundary": (
            "local Capsulang feasibility test for a checked outer governance "
            "state machine; Python remains the evidence and effect-execution host"
        ),
        "capsule": str(CAPSULE.relative_to(ROOT)),
        "semantic_hash": preview["semanticHash"],
        "checked": checked["status"] == "checked",
        "governance_status": governance["status"],
        "governance_complete": governance_complete,
        "gate_complete": gate_complete,
        "scenario_parity": scenario_parity,
        "scenarios": {
            name: {
                "expected_state": expected_states[name],
                "final_state": scenario_evidence[name]["final_state"],
                "status": scenario_evidence[name]["status"],
            }
            for name, result in scenario_results.items()
        },
        "invalid_promotion_blocked": invalid_promotion_blocked,
        "machine": {
            "name": machine["name"],
            "states": len(machine["states"]),
            "transitions": sum(state["transitions"] for state in machine["states"]),
            "effect_intents": cost["summary"]["effectIntents"],
            "audit_complexity": cost["summary"]["auditComplexity"],
        },
        "budget": {
            "max_iterations": 100,
            "max_llm_calls": 1000,
            "max_ci_runs": 200,
            "max_wall_clock_ms": 86400000,
            "max_cost_usd": 1,
            "live_deployment_denied": True,
        },
        "host_boundary_explicit": host_boundary_explicit,
        "adoption_gate": {
            "requires_checked_capsule": True,
            "requires_complete_governance_surface": True,
            "requires_scenario_parity": True,
            "requires_explicit_host_boundary": True,
            "passed": (
                checked["status"] == "checked"
                and governance_complete
                and gate_complete
                and scenario_parity
                and invalid_promotion_blocked
                and host_boundary_explicit
            ),
        },
    }
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    _atomic_json(ROOT / "experiments" / "E53-capsulang-governor.json", report)
    print(
        f"checked={report['checked']} governance={governance_complete} "
        f"gate={gate_complete} scenario_parity={scenario_parity} "
        f"invalid_promotion_blocked={invalid_promotion_blocked} "
        f"host_boundary={host_boundary_explicit} "
        f"adoption_gate={report['adoption_gate']['passed']}"
    )


if __name__ == "__main__":
    main()
