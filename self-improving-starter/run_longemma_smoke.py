"""E13 adapter smoke: deterministic backend now, local Gemma gate recorded."""

from __future__ import annotations

import hashlib
import json
import urllib.request
from dataclasses import asdict
from pathlib import Path

from compare_selection import _atomic_json
from recursive_lab.alphaevolve import EvolutionBudget, evolve_programs, text_fingerprint
from recursive_lab.longemma_adapter import LongemmaProposer
from recursive_lab.quality_diversity import CandidateEvaluation


class MockResponse:
    text = '{"program":"def solve():\\n    return 1\\n"}'
    model = "gemma-adapter-mock"
    backend_name = "deterministic-mock"

    class usage:
        prompt_tokens = 10
        completion_tokens = 8
        total_tokens = 18


class MockBackend:
    name = "deterministic-mock"

    def generate(self, *args, **kwargs):
        return MockResponse()


def main():
    proposer = LongemmaProposer(MockBackend(), "Return a complete solve program.")

    def evaluate(program):
        return CandidateEvaluation(
            1.0 if "return 1" in program else 0.0,
            (1.0 if "return 1" in program else 0.0,),
            {"correct": 1.0 if "return 1" in program else 0.0},
        )

    result = evolve_programs(
        initial="def solve():\n    return 0\n",
        proposers=(proposer,),
        evaluate=evaluate,
        fingerprint=text_fingerprint,
        budget=EvolutionBudget(4, 1),
        seed=13,
        bins=(2,),
    )
    local_model_available = False
    try:
        with urllib.request.urlopen(
            "http://127.0.0.1:12345/v1/models", timeout=2
        ) as response:
            local_model_available = response.status == 200
    except Exception:
        pass
    report = {
        "schema_version": 1,
        "experiment_id": "E13-longemma-adapter-smoke",
        "claim_boundary": "adapter and accounting smoke; no local-model capability claim",
        "adapter": "Longemma GenerationBackend-compatible",
        "mock_backend_passed": result.best.evaluation.objective == 1
        and len(proposer.receipts) == 4,
        "model_calls": result.model_calls,
        "candidate_evaluations": result.candidate_evaluations,
        "task_evaluations": result.task_evaluations,
        "receipt_count": len(proposer.receipts),
        "local_gemma_endpoint": "http://127.0.0.1:12345/v1/models",
        "local_gemma_available": local_model_available,
        "receipts": [asdict(r) for r in proposer.receipts],
    }
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    _atomic_json(Path("experiments/E13-longemma-adapter-smoke.json"), report)
    print(
        f"mock adapter: {'PASS' if report['mock_backend_passed'] else 'FAIL'}; local Gemma: {'AVAILABLE' if local_model_available else 'OFFLINE'}"
    )


if __name__ == "__main__":
    main()
