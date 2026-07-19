"""LLM mutation operator: propose an improved solution given a parent.

In the Darwin Gödel Machine the foundation model is the *mutation operator* —
it reads the current solution and proposes a self-edit. Here the proposer is a
frontier model (Claude) called through the Anthropic SDK. The model you FINE-TUNE
(the open-weight target in rl/) is separate; the frontier model just drives the
scaffold search cheaply.

Adaptive thinking is on and effort is high because proposing a genuinely better
algorithm is the intelligence-sensitive step. Streaming is used so large / slow
responses don't hit HTTP timeouts.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import anthropic

_SYSTEM = (
    "You are a code-optimization agent competing to produce the fastest correct "
    "solution. You will be given a task and the current best solution from an "
    "archive. Propose a NEW complete solution that is faster while preserving the "
    "exact contract. Return ONLY the Python module source — no prose, no markdown "
    "fences, no explanation."
)


class Proposer:
    def __init__(self, model: str = "claude-opus-4-8", effort: str = "high") -> None:
        # Keep the optional model SDK out of the deterministic evaluator and test
        # path.  Importing this module for `_strip_fences` or dependency injection
        # must not require credentials or third-party packages.
        try:
            import anthropic
        except ImportError as error:
            raise RuntimeError(
                "The live Anthropic proposer is optional. Install requirements.txt "
                "before selecting it; deterministic replay needs no SDK or API key."
            ) from error
        self.client: Any = anthropic.Anthropic()  # reads API key / provider profile
        self.model = model
        self.effort = effort

    def propose(self, task_prompt: str, parent_source: str) -> str:
        user = (
            f"{task_prompt}\n\n"
            f"Current best solution from the archive (improve on it):\n"
            f"```\n{parent_source}\n```\n\n"
            f"Return the full source of your improved `solve(n)` module."
        )
        # Streaming + get_final_message() gives timeout protection without
        # hand-handling individual events.
        with self.client.messages.stream(
            model=self.model,
            max_tokens=8000,
            thinking={"type": "adaptive"},
            output_config={"effort": self.effort},
            system=_SYSTEM,
            messages=[{"role": "user", "content": user}],
        ) as stream:
            message = stream.get_final_message()

        # First text block is the candidate source. Strip a stray fence if the
        # model added one despite instructions.
        text = next((b.text for b in message.content if b.type == "text"), "")
        return _strip_fences(text)


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        lines = t.splitlines()
        lines = lines[1:]                      # drop opening ``` (and any lang tag)
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        t = "\n".join(lines)
    return t.strip() + "\n"
