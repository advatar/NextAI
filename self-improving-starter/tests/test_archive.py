from __future__ import annotations

import json
import math
import random
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from archive import Archive, Node  # noqa: E402


class ArchiveTests(unittest.TestCase):
    def _node_fields(self, **overrides):
        fields = {
            "node_id": 0,
            "parent_id": None,
            "source": "root",
            "reward": 0.0,
            "correct": True,
            "detail": "seed",
            "children": 0,
            "attempts": 0,
            "source_hash": "",
            "meta": {},
        }
        fields.update(overrides)
        return fields

    def test_content_dedup_attempt_accounting_and_round_trip(self):
        archive = Archive()
        root = archive.seed("root", 0.0, True, "seed")
        archive.record_attempt(root)
        child = archive.add(root, "child", 1.0, True, "better")

        self.assertTrue(archive.contains_source("root"))
        self.assertTrue(archive.contains_source("child"))
        self.assertFalse(archive.contains_source("other"))
        self.assertEqual(root.attempts, 1)
        self.assertEqual(root.children, 1)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "archive.jsonl"
            archive.dump_jsonl(path)
            loaded = Archive.load_jsonl(path)
        self.assertEqual(loaded.nodes, archive.nodes)
        self.assertEqual(loaded.best().source_hash, child.source_hash)

    def test_load_rejects_source_hash_tampering(self):
        archive = Archive()
        archive.seed("root", 0.0, True, "seed")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "archive.jsonl"
            archive.dump_jsonl(path)
            row = json.loads(path.read_text())
            row["source"] = "tampered"
            path.write_text(json.dumps(row) + "\n")
            with self.assertRaises(ValueError):
                Archive.load_jsonl(path)

    def test_selection_charges_all_attempts(self):
        archive = Archive()
        root = archive.seed("root", 0.0, True, "seed")
        strong = archive.add(root, "strong", 1.0, True, "strong")
        for _ in range(100):
            archive.record_attempt(strong)
        choices = [archive.select_parent(random.Random(seed)).node_id for seed in range(100)]
        self.assertIn(root.node_id, choices)

    def test_node_rejects_malformed_runtime_fields(self):
        invalid_fields = [
            {"node_id": True},
            {"node_id": -1},
            {"parent_id": True},
            {"parent_id": -1},
            {"source": b"root"},
            {"source": "\ud800"},
            {"reward": True},
            {"reward": "1"},
            {"reward": math.nan},
            {"reward": math.inf},
            {"correct": 1},
            {"correct": "yes"},
            {"detail": None},
            {"children": True},
            {"children": -1},
            {"attempts": True},
            {"attempts": -1},
            {"source_hash": 1},
            {"source_hash": "0" * 64},
            {"meta": []},
            {"meta": {"nonfinite": math.nan}},
            {"meta": {1: "non-string key"}},
            {"meta": {"tuple": (1, 2)}},
        ]
        for overrides in invalid_fields:
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                Node(**self._node_fields(**overrides))

    def test_load_rejects_invalid_root_lineage_counts_and_schema(self):
        archive = Archive()
        root = archive.seed("root", 0.0, True, "seed")
        archive.add(root, "child", 1.0, True, "child")

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "archive.jsonl"
            archive.dump_jsonl(path)
            original = [json.loads(line) for line in path.read_text().splitlines()]
            mutations = [
                lambda rows: rows[0].__setitem__("parent_id", 0),
                lambda rows: rows[0].__setitem__("children", 0),
                lambda rows: rows[1].__setitem__("parent_id", None),
                lambda rows: rows[1].__setitem__("correct", "yes"),
                lambda rows: rows[1].__setitem__("attempts", -1),
                lambda rows: rows[1].__setitem__("source_hash", 7),
                lambda rows: rows[1].__setitem__("meta", []),
            ]
            for index, mutate in enumerate(mutations):
                rows = [dict(row) for row in original]
                mutate(rows)
                path.write_text("".join(json.dumps(row) + "\n" for row in rows))
                with self.subTest(index=index), self.assertRaises(ValueError):
                    Archive.load_jsonl(path)

            path.write_text(json.dumps(original[0]) + "\nNaN\n")
            with self.assertRaises(ValueError):
                Archive.load_jsonl(path)

    def test_load_supports_pre_attempt_and_pre_hash_archives(self):
        archive = Archive()
        root = archive.seed("root", 0.0, True, "seed")
        archive.add(root, "child", 1.0, True, "child")

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "archive.jsonl"
            archive.dump_jsonl(path)
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            for row in rows:
                row.pop("attempts")
                row.pop("source_hash")
            path.write_text("".join(json.dumps(row) + "\n" for row in rows))
            loaded = Archive.load_jsonl(path)

        self.assertEqual([node.source for node in loaded.nodes], ["root", "child"])
        self.assertEqual([node.attempts for node in loaded.nodes], [1, 0])
        self.assertTrue(all(node.source_hash for node in loaded.nodes))

    def test_archive_rejects_foreign_parent_duplicate_and_mutated_state(self):
        archive = Archive()
        root = archive.seed("root", 0.0, True, "seed")
        foreign = Node(0, None, "foreign", 0.0, True, "foreign")

        with self.assertRaises(ValueError):
            archive.add(foreign, "child", 1.0, True, "child")
        with self.assertRaises(ValueError):
            archive.add(root, "root", 1.0, True, "duplicate")

        root.reward = math.nan
        with self.assertRaises(ValueError):
            archive.best()
        with self.assertRaises(ValueError):
            archive.select_parent(random.Random(0))

    def test_select_parent_handles_extreme_finite_rewards_and_bad_rng(self):
        archive = Archive()
        root = archive.seed("root", 1e308, True, "seed")
        archive.add(root, "child", 1e308, True, "child")
        root.attempts = 10**1_000
        self.assertIn(archive.select_parent(random.Random(0)), archive.nodes)

        class BadRng:
            def random(self):
                return math.nan

        with self.assertRaises(ValueError):
            archive.select_parent(BadRng())


if __name__ == "__main__":
    unittest.main()
