"""E58: real local-Gemma proposals with safe evaluation and governed promotion."""
from __future__ import annotations

from dataclasses import asdict
import ast
import hashlib
import json
from pathlib import Path
import random
import sys
from types import SimpleNamespace

from compare_selection import _atomic_json
from recursive_lab.alphaevolve import ProgramRecord, PromptSample
from recursive_lab.capsulang_governor import CapsulangGovernor, PromotionEvidence
from recursive_lab.longemma_adapter import LongemmaProposer
from recursive_lab.quality_diversity import CandidateEvaluation
from recursive_lab.safe_numeric_program import (
    NumericProgramError,
    evaluate_solve,
    parse_solve_expression,
)

ROOT = Path(__file__).parent
LONGEMMA_SRC = ROOT.parent.parent / "Longemma" / "src"
sys.path.insert(0, str(LONGEMMA_SRC))

MODEL = (
    "/Users/johansellstrom/dev/advatar/Broom/diskspace-gemma/"
    "models/gemma-4-e2b-it-4bit-mlx"
)
CAPSULE = ROOT / "capsulang" / "e53_recursive_governor.caps"
SEMANTIC_HASH = "4438a99af2d0539be06a5128d214741a36d1dd8920205b4787062bfaba65cab3"
PUBLIC_CASES = (-4, -1, 0, 1, 3)
HELDOUT_CASES = (-101, -11, -2, 2, 7, 19, 100)
PROPOSALS = 6


def target(n: int) -> int:
    return n**3 + 2 * n + 5 if n >= 0 else n * n - 3 * n + 11


def evaluate(source: str, cases: tuple[int, ...]) -> tuple[bool, float, str | None]:
    try:
        expression = parse_solve_expression(source)
        correct = sum(evaluate_solve(expression, n) == target(n) for n in cases)
    except NumericProgramError as error:
        return False, 0.0, str(error)
    return True, correct / len(cases), None


def old_expression_only_validator_accepts(source: str) -> bool:
    """Replay the initial E58 rule that rejected Gemma's safe if/else form."""
    try:
        module = ast.parse(source, mode="exec")
    except (SyntaxError, ValueError, RecursionError):
        return False
    functions = [node for node in module.body if isinstance(node, ast.FunctionDef)]
    return (
        len(module.body) == 1
        and len(functions) == 1
        and len(functions[0].body) == 1
        and isinstance(functions[0].body[0], ast.Return)
    )


def record(source: str, score: float, generation: int, parent_id: str | None):
    return ProgramRecord(
        program_id=hashlib.sha256(source.encode()).hexdigest(),
        candidate=source,
        evaluation=CandidateEvaluation(score, (score,), {"public_score": score}),
        generation=generation,
        parent_id=parent_id,
        inspiration_ids=(),
        proposer="local-gemma-4-e2b",
    )


def main() -> None:
    from gemma_agent_lab.backends.base import ChatMessage
    from gemma_agent_lab.backends.openai_compatible import OpenAICompatibleBackend

    backend = OpenAICompatibleBackend(
        SimpleNamespace(
            model=MODEL,
            base_url="http://127.0.0.1:12345/v1",
            api_key_env=None,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
    )
    task = (
        "Define exactly def solve(n) with one return expression. For n >= 0, "
        "return n**3 + 2*n + 5. For n < 0, return n*n - 3*n + 11. "
        "No imports, calls, assignments, annotations, decorators, or additional "
        "statements. The evaluator interprets a restricted AST and never executes "
        "the generated Python."
    )
    proposer = LongemmaProposer(
        backend,
        task,
        name="local-gemma-4-e2b",
        message_factory=ChatMessage,
    )
    governor = CapsulangGovernor(CAPSULE, expected_semantic_hash=SEMANTIC_HASH)
    baseline = "def solve(n):\n    return n\n"
    baseline_public = evaluate(baseline, PUBLIC_CASES)[1]
    baseline_heldout = evaluate(baseline, HELDOUT_CASES)[1]
    direct_parent = record(baseline, baseline_public, 0, None)
    governed_parent = direct_parent
    direct_best = baseline_heldout
    governed_best = baseline_heldout
    archive = [direct_parent]
    rows: list[dict[str, object]] = []
    rng = random.Random(58)

    try:
        for generation in range(1, PROPOSALS + 1):
            sample = PromptSample(
                parent=direct_parent,
                inspirations=tuple(archive[-2:]),
                feedback={
                    "public_score": direct_parent.evaluation.objective,
                    "target_public_score": 1.0,
                },
            )
            try:
                candidate = proposer.propose(sample, rng)
                parse_ok = True
                generation_error = None
            except ValueError as error:
                candidate = ""
                parse_ok = False
                generation_error = str(error)
            valid_public, public_score, validation_error = evaluate(
                candidate, PUBLIC_CASES
            )
            valid_heldout, heldout_score, heldout_error = evaluate(
                candidate, HELDOUT_CASES
            )
            valid = parse_ok and valid_public and valid_heldout
            candidate_record = record(
                candidate,
                public_score,
                generation,
                direct_parent.program_id,
            )
            archive.append(candidate_record)
            direct_promoted = (
                valid
                and public_score == 1.0
                and heldout_score > direct_best
            )
            governed_eligible = (
                valid
                and public_score == 1.0
                and heldout_score > governed_best
            )
            governor_receipt = None
            governed_promoted = False
            if governed_eligible:
                receipt = governor.decide(
                    PromotionEvidence(
                        benchmark_admitted=True,
                        gain_bps=round((heldout_score - governed_best) * 10_000),
                        external_regret_bps=0,
                        parity_checked=True,
                    )
                )
                governor_receipt = receipt.to_dict()
                governed_promoted = receipt.promoted
            if direct_promoted:
                direct_parent = candidate_record
                direct_best = heldout_score
            if governed_promoted:
                governed_parent = candidate_record
                governed_best = heldout_score
            rows.append(
                {
                    "generation": generation,
                    "candidate_digest": candidate_record.program_id,
                    "candidate": candidate,
                    "parse_ok": parse_ok,
                    "safe_ast_valid": valid,
                    "public_score": public_score,
                    "heldout_score": heldout_score,
                    "direct_promoted": direct_promoted,
                    "governed_promoted": governed_promoted,
                    "governor_receipt": governor_receipt,
                    "error": generation_error or validation_error or heldout_error,
                }
            )
            print(
                f"generation={generation} valid={valid} public={public_score:.0%} "
                f"heldout={heldout_score:.0%} promoted={governed_promoted}"
            )
    finally:
        backend.close()

    direct_promotions = sum(bool(row["direct_promoted"]) for row in rows)
    governed_promotions = sum(bool(row["governed_promoted"]) for row in rows)
    promotion_parity = all(
        row["direct_promoted"] == row["governed_promoted"] for row in rows
    )
    model_receipts = [asdict(receipt) for receipt in proposer.receipts]
    report = {
        "schema_version": 1,
        "experiment_id": "E58-gemma-governed-program",
        "claim_boundary": (
            "one local Gemma 4 E2B program task with shared candidate stream, "
            "restricted-AST interpretation, held-out selection, and Capsulang "
            "promotion corroboration; not evidence of general self-improvement"
        ),
        "model": MODEL,
        "proposals": PROPOSALS,
        "public_cases": len(PUBLIC_CASES),
        "heldout_cases": len(HELDOUT_CASES),
        "baseline_heldout_score": baseline_heldout,
        "direct_best_heldout_score": direct_best,
        "governed_best_heldout_score": governed_best,
        "direct_promotions": direct_promotions,
        "governed_promotions": governed_promotions,
        "promotion_parity": promotion_parity,
        "valid_candidates": sum(bool(row["safe_ast_valid"]) for row in rows),
        "evaluator_revision": {
            "initial_expression_only_accepts": sum(
                old_expression_only_validator_accepts(str(row["candidate"]))
                for row in rows
            ),
            "revised_safe_piecewise_accepts": sum(
                bool(row["safe_ast_valid"]) for row in rows
            ),
            "new_authority_granted": False,
            "change": (
                "accept one top-level if/else whose two branches contain only "
                "return expressions; calls and arbitrary statements remain forbidden"
            ),
        },
        "model_calls": len(model_receipts),
        "total_tokens": sum(receipt["total_tokens"] for receipt in model_receipts),
        "rows": rows,
        "model_receipts": model_receipts,
        "adoption_gate": {
            "passed": (
                len(model_receipts) == PROPOSALS
                and promotion_parity
                and governed_promotions >= 1
                and governed_best == 1.0
                and all(
                    row["governor_receipt"] is not None
                    for row in rows
                    if row["governed_promoted"]
                )
            )
        },
    }
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["report_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    _atomic_json(ROOT / "experiments" / "E58-gemma-governed-program.json", report)
    print(
        f"valid={report['valid_candidates']}/{PROPOSALS} "
        f"promotions={governed_promotions} parity={promotion_parity} "
        f"best={governed_best:.0%} adoption_gate={report['adoption_gate']['passed']}"
    )


if __name__ == "__main__":
    main()
