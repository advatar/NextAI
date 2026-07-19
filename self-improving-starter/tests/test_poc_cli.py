from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))


class PocCliTests(unittest.TestCase):
    def test_demo_and_anchored_ledger_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "demo"
            demo = subprocess.run(
                [
                    sys.executable,
                    "poc.py",
                    "demo",
                    "--out",
                    str(output),
                    "--rounds",
                    "6",
                    "--seed",
                    "3",
                ],
                cwd=PROJECT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(demo.returncode, 0, demo.stderr)
            self.assertIn("not empirical RSI evidence", demo.stdout)

            summary = json.loads((output / "summary.json").read_text())
            report = json.loads((output / "metaproductivity.json").read_text())
            self.assertEqual(summary["lab"]["accepted_generations"], 3)
            self.assertEqual(summary["lab"]["attempts"], 6)
            self.assertIn("plumbing validation only", summary["claim_boundary"])
            self.assertTrue(report["summary"]["fixture_only"])

            verify = subprocess.run(
                [
                    sys.executable,
                    "poc.py",
                    "verify-ledger",
                    "--ledger",
                    str(output / "lineage.jsonl"),
                    "--anchor",
                    str(output / "ledger.head"),
                ],
                cwd=PROJECT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(verify.returncode, 0, verify.stderr)
            self.assertIn("ledger OK:", verify.stdout)

    def test_demo_refuses_to_overwrite_nonempty_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "demo"
            output.mkdir()
            (output / "owned.txt").write_text("keep")
            result = subprocess.run(
                [sys.executable, "poc.py", "demo", "--out", str(output)],
                cwd=PROJECT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((output / "owned.txt").read_text(), "keep")

    def test_completed_demo_resumes_idempotently_and_rejects_seed_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "demo"
            base_command = [
                sys.executable,
                "poc.py",
                "demo",
                "--out",
                str(output),
                "--rounds",
                "6",
                "--seed",
                "11",
            ]
            first = subprocess.run(
                base_command,
                cwd=PROJECT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            original_ledger = (output / "lineage.jsonl").read_bytes()

            resumed = subprocess.run(
                [*base_command, "--resume"],
                cwd=PROJECT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(resumed.returncode, 0, resumed.stderr)
            self.assertEqual((output / "lineage.jsonl").read_bytes(), original_ledger)

            first_entry = json.loads(original_ledger.splitlines()[0])
            current_head = (output / "ledger.head").read_text()
            (output / "ledger.head").write_text(first_entry["current_hash"] + "\n")
            stale = subprocess.run(
                [*base_command, "--resume"],
                cwd=PROJECT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(stale.returncode, 0)
            self.assertIn("trusted head does not match", stale.stderr)

            recovered = subprocess.run(
                [*base_command, "--resume", "--recover-unanchored-tail"],
                cwd=PROJECT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(recovered.returncode, 0, recovered.stderr)
            self.assertEqual((output / "ledger.head").read_text(), current_head)

            drifted = subprocess.run(
                [
                    sys.executable,
                    "poc.py",
                    "demo",
                    "--out",
                    str(output),
                    "--rounds",
                    "6",
                    "--seed",
                    "12",
                    "--resume",
                ],
                cwd=PROJECT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(drifted.returncode, 0)
            self.assertIn("manifest drift", drifted.stderr)

    def test_resume_treats_rounds_as_total_target_after_search_checkpoint(self):
        from poc import _DEMO_LIMITS, _DeterministicClock
        from recursive_lab.fixtures import (
            FixtureSequenceProposer,
            FixtureStrategyEvaluator,
            baseline_strategy,
        )
        from recursive_lab.governance import AcceptancePolicy
        from recursive_lab.lab import StrategyLab
        from recursive_lab.ledger import GENESIS_HASH

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "interrupted"
            output.mkdir()
            ledger_path = output / "lineage.jsonl"
            anchor_path = output / "ledger.head"
            anchor_path.write_text(GENESIS_HASH + "\n")
            lab = StrategyLab(
                proposer=FixtureSequenceProposer(),
                evaluator=FixtureStrategyEvaluator(),
                policy=AcceptancePolicy(min_gain=0.25),
                limits=_DEMO_LIMITS,
                ledger_path=ledger_path,
                manifest_path=output / "experiment-manifest.json",
                run_seed=29,
                clock=_DeterministicClock(),
                head_observer=lambda head: anchor_path.write_text(head + "\n"),
            )
            lab.initialize(baseline_strategy(), seed=29)
            self.assertEqual(lab.run(2).attempts, 2)

            resumed = subprocess.run(
                [
                    sys.executable,
                    "poc.py",
                    "demo",
                    "--out",
                    str(output),
                    "--rounds",
                    "2",
                    "--seed",
                    "29",
                    "--resume",
                ],
                cwd=PROJECT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(resumed.returncode, 0, resumed.stderr)
            summary = json.loads((output / "summary.json").read_text())
            self.assertEqual(summary["lab"]["attempts"], 2)


if __name__ == "__main__":
    unittest.main()
