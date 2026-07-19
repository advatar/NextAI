"""Legacy entrypoint: run the object-level DGM-style solution loop.

    python run.py --rounds 15 --env optimize_function

Writes the archive and trajectories under runs/<timestamp>/ so rl/dataset.py
can inspect the evaluated candidates. This command optimizes a task answer, not
the improver; use ``poc.py`` for the governed strategy-lab plumbing.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dgm_loop import run_loop
from environments import REGISTRY


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default="optimize_function", choices=sorted(REGISTRY))
    ap.add_argument("--rounds", type=int, default=15)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default="runs/latest")
    args = ap.parse_args()

    env = REGISTRY[args.env]()
    archive, trajectories = run_loop(env, rounds=args.rounds, seed=args.seed)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    archive.dump_jsonl(out / "archive.jsonl")
    with (out / "trajectories.jsonl").open("w") as f:
        for t in trajectories:
            f.write(json.dumps(t.__dict__) + "\n")

    best = archive.best()
    print(f"\nBest normalized reward: {best.reward:.3f} (node #{best.node_id})")
    print(f"Archive size: {len(archive.nodes)} nodes")
    print(f"Wrote {out/'archive.jsonl'} and {out/'trajectories.jsonl'}")
    print("\nBest solution:\n" + best.source)


if __name__ == "__main__":
    main()
