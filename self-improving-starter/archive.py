"""Darwin-Gödel-Machine-style archive of self-improving agents.

Per arXiv:2505.22954, the DGM keeps a growing *tree* of agents rather than a
single hill-climbing champion. Each node holds a candidate solution and its
verified score. New nodes are produced by mutating a selected parent and are
added if they beat the parent OR add novelty — so weaker "stepping-stone"
ancestors are retained, because they sometimes seed the breakthroughs.

Parent selection is probabilistic: proportional to a node's performance and
inversely proportional to how many proposals have already been attempted from
it. Rejected and failed attempts therefore still consume exploration pressure.
That biases sampling toward strong performers while preserving exploration.
"""

from __future__ import annotations

import json
import hashlib
import math
import os
import re
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path


_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")


def _source_digest(source: str) -> str:
    if type(source) is not str:
        raise ValueError("node source must be text")
    try:
        encoded = source.encode("utf-8")
    except UnicodeError as error:
        raise ValueError("node source must be valid UTF-8 text") from error
    return hashlib.sha256(encoded).hexdigest()


def _validate_json_value(value, *, path: str = "meta", depth: int = 0) -> None:
    """Require metadata to round-trip through strict, finite JSON unchanged."""

    if depth > 32:
        raise ValueError(f"{path} exceeds the maximum nesting depth")
    if value is None or type(value) in {bool, int, str}:
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError(f"{path} contains a non-finite number")
        return
    if type(value) is list:
        for index, item in enumerate(value):
            _validate_json_value(item, path=f"{path}[{index}]", depth=depth + 1)
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise ValueError(f"{path} keys must be strings")
            _validate_json_value(item, path=f"{path}.{key}", depth=depth + 1)
        return
    raise ValueError(f"{path} contains unsupported type {type(value).__name__}")


def _strict_json_object(line: str, *, line_number: int) -> dict:
    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"archive line {line_number} has duplicate key {key!r}")
            result[key] = value
        return result

    def reject_constant(value):
        raise ValueError(
            f"archive line {line_number} contains non-finite constant {value}"
        )

    try:
        value = json.loads(
            line,
            object_pairs_hook=object_pairs,
            parse_constant=reject_constant,
        )
    except (json.JSONDecodeError, RecursionError, TypeError) as error:
        raise ValueError(f"archive line {line_number} is invalid JSON") from error
    if not isinstance(value, dict):
        raise ValueError(f"archive line {line_number} must be a JSON object")
    return value


@dataclass
class Node:
    node_id: int
    parent_id: int | None
    source: str
    reward: float
    correct: bool
    detail: str
    children: int = 0                 # accepted immediate children
    attempts: int = 0                 # every attempted child consumes exploration budget
    source_hash: str = ""
    meta: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.validate(allow_missing_hash=True)
        self.source_hash = _source_digest(self.source)

    def validate(self, *, allow_missing_hash: bool = False) -> None:
        """Fail closed if this mutable runtime record no longer satisfies schema."""

        if type(self.node_id) is not int or self.node_id < 0:
            raise ValueError("node_id must be a non-negative integer")
        if self.parent_id is not None and (
            type(self.parent_id) is not int or self.parent_id < 0
        ):
            raise ValueError("parent_id must be null or a non-negative integer")
        expected = _source_digest(self.source)
        if type(self.reward) not in {int, float}:
            raise ValueError("node reward must be a finite real number")
        try:
            finite_reward = math.isfinite(float(self.reward))
        except (OverflowError, TypeError, ValueError):
            finite_reward = False
        if not finite_reward:
            raise ValueError("node reward must be a finite real number")
        if type(self.correct) is not bool:
            raise ValueError("node correct must be a bool")
        if type(self.detail) is not str:
            raise ValueError("node detail must be text")
        for field_name in ("children", "attempts"):
            value = getattr(self, field_name)
            if type(value) is not int or value < 0:
                raise ValueError(f"node {field_name} must be a non-negative integer")
        if type(self.source_hash) is not str:
            raise ValueError("node source_hash must be text")
        if self.source_hash:
            if _SHA256_RE.fullmatch(self.source_hash) is None:
                raise ValueError("node source_hash must be a lowercase SHA-256 digest")
            if self.source_hash != expected:
                raise ValueError("node source_hash does not match source")
        elif not allow_missing_hash:
            raise ValueError("node source_hash is missing")
        if type(self.meta) is not dict:
            raise ValueError("node meta must be a JSON object")
        _validate_json_value(self.meta)


class Archive:
    def __init__(self) -> None:
        self.nodes: list[Node] = []

    def seed(self, source: str, reward: float, correct: bool, detail: str) -> Node:
        node = Node(node_id=0, parent_id=None, source=source, reward=reward,
                    correct=correct, detail=detail)
        self.nodes = [node]
        return node

    def add(self, parent: Node, source: str, reward: float, correct: bool, detail: str) -> Node:
        self.validate(require_nonempty=True)
        self._require_member(parent)
        if self.contains_source(source):
            raise ValueError("archive already contains this source")
        node = Node(node_id=len(self.nodes), parent_id=parent.node_id, source=source,
                    reward=reward, correct=correct, detail=detail)
        parent.children += 1
        self.nodes.append(node)
        return node

    def record_attempt(self, parent: Node) -> None:
        """Charge exploration pressure for every proposal, accepted or rejected."""
        self.validate(require_nonempty=True)
        self._require_member(parent)
        parent.attempts += 1

    def contains_source(self, source: str) -> bool:
        self.validate()
        if type(source) is not str:
            raise ValueError("candidate source must be text")
        digest = _source_digest(source)
        return any(node.source_hash == digest for node in self.nodes)

    def best(self) -> Node:
        self.validate(require_nonempty=True)
        return max(self.nodes, key=lambda n: n.reward)

    def select_parent(self, rng) -> Node:
        """Sample a parent ∝ perf / (1 + attempts).

        `perf` is shifted so even non-improving-but-correct nodes retain a small
        selection probability (open-ended exploration keeps stepping stones).
        """
        self.validate(require_nonempty=True)
        log_weights = []
        for n in self.nodes:
            perf = max(n.reward, 0.0) + 0.05          # floor keeps ancestors alive
            # Work in log space so untrusted-but-valid large counters cannot
            # overflow during integer-to-float division.
            log_weights.append(math.log(perf) - math.log(n.attempts + 1))
        largest = max(log_weights)
        scaled = [math.exp(weight - largest) for weight in log_weights]
        total = math.fsum(scaled)
        try:
            draw = rng.random()
        except Exception as error:
            raise ValueError("rng must provide random()") from error
        if type(draw) not in {int, float}:
            raise ValueError("rng.random() must return a finite real in [0, 1)")
        try:
            draw = float(draw)
        except (OverflowError, TypeError, ValueError) as error:
            raise ValueError(
                "rng.random() must return a finite real in [0, 1)"
            ) from error
        if not math.isfinite(draw) or not 0.0 <= draw < 1.0:
            raise ValueError("rng.random() must return a finite real in [0, 1)")
        r = draw * total
        upto = 0.0
        for n, w in zip(self.nodes, scaled):
            upto += w
            if upto >= r:
                return n
        return self.nodes[-1]

    def dump_jsonl(self, path: str | Path) -> None:
        self.validate(require_nonempty=True)
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                for n in self.nodes:
                    f.write(
                        json.dumps(asdict(n), allow_nan=False, sort_keys=True) + "\n"
                    )
                f.flush()
                os.fsync(f.fileno())
            os.replace(temporary_name, path)
        except BaseException:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            raise

    @classmethod
    def load_jsonl(cls, path: str | Path) -> "Archive":
        archive = cls()
        lines = Path(path).read_text(encoding="utf-8").splitlines()
        if not lines:
            raise ValueError("archive must contain a seed node")
        nodes = []
        for line_number, line in enumerate(lines, start=1):
            if not line.strip():
                raise ValueError(f"archive line {line_number} is empty")
            row = _strict_json_object(line, line_number=line_number)
            # Archives written before attempt accounting are still loadable.  An
            # accepted child is the minimum attempt count we can reconstruct.
            if "attempts" not in row:
                row["attempts"] = row.get("children", 0)
            try:
                nodes.append(Node(**row))
            except (TypeError, ValueError) as error:
                raise ValueError(f"archive line {line_number} is invalid: {error}") from error
        archive.nodes = nodes
        archive.validate(require_nonempty=True)
        return archive

    def _require_member(self, node: Node) -> None:
        if not isinstance(node, Node):
            raise ValueError("parent must be a Node")
        if node.node_id >= len(self.nodes) or self.nodes[node.node_id] is not node:
            raise ValueError("parent node does not belong to this archive")

    def validate(self, *, require_nonempty: bool = False) -> None:
        """Validate runtime and serialized lineage invariants."""

        if type(self.nodes) is not list:
            raise ValueError("archive nodes must be a list")
        if require_nonempty and not self.nodes:
            raise ValueError("archive must contain a seed node")
        if not self.nodes:
            return

        seen_hashes: set[str] = set()
        derived_children = [0] * len(self.nodes)
        for expected_id, node in enumerate(self.nodes):
            if not isinstance(node, Node):
                raise ValueError(f"archive entry {expected_id} is not a Node")
            node.validate()
            if node.node_id != expected_id:
                raise ValueError("archive node ids must be ordered and contiguous")
            if expected_id == 0:
                if node.parent_id is not None:
                    raise ValueError("archive seed node cannot have a parent")
            else:
                if node.parent_id is None or node.parent_id >= node.node_id:
                    raise ValueError("archive contains invalid lineage")
                derived_children[node.parent_id] += 1
            if node.source_hash in seen_hashes:
                raise ValueError("archive contains duplicate source content")
            seen_hashes.add(node.source_hash)
        for node, expected_children in zip(self.nodes, derived_children):
            if node.children != expected_children:
                raise ValueError("archive child counts do not match lineage")
