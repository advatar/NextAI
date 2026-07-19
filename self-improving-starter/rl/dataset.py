"""Build a verl GRPO prompt dataset from environments and/or scaffold trajectories.

Two modes:
  * --from-envs        one prompt per registered environment (pure RL from the
                       task prompt; the policy learns to solve from scratch).
  * --archive PATH     report how many archive nodes would qualify for a future
                       SFT export. This historical skeleton does not yet emit
                       completions/trajectories and must not be described as a
                       verified training-data pipeline.

verl expects a parquet with at least a `prompt` column (chat format) and a
`data_source` column the reward fn can read. We also stash `extra_info.env` so
rl/reward.py knows which environment to score against.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from environments import REGISTRY


def _rows_from_envs():
    rows = []
    for name, cls in sorted(REGISTRY.items()):
        env = cls()
        rows.append(
            {
                "data_source": name,
                "prompt": [
                    {"role": "system", "content": "Return only the Python module source."},
                    {"role": "user", "content": env.task_prompt},
                ],
                "reward_model": {"style": "rule", "ground_truth": ""},  # RLVR: reward is code-execution, not a label
                "extra_info": {"env": name},
            }
        )
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--archive",
        default=None,
        help="optional DGM archive.jsonl; reports stats only (does not export completions)",
    )
    ap.add_argument("--out", default="data/train.parquet")
    args = ap.parse_args()

    try:
        import pandas as pd
    except ImportError:
        raise SystemExit("pip install pandas pyarrow to write the parquet dataset")

    rows = _rows_from_envs()

    if args.archive:
        winners = [
            json.loads(line)
            for line in Path(args.archive).read_text().splitlines()
            if json.loads(line)["correct"] and json.loads(line)["reward"] > 0
        ]
        print(f"archive: {len(winners)} verified winners available as SFT seeds "
              f"(feed via a separate SFT pass before GRPO if desired)")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(out)
    print(f"wrote {len(rows)} prompts -> {out}")


if __name__ == "__main__":
    main()
