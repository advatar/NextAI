"""Thin adapter from Longemma GenerationBackend responses to AlphaEvolve."""

from __future__ import annotations

import hashlib
import json
import random
import time
from dataclasses import dataclass
from typing import Any, Callable

from .alphaevolve import PromptSample


@dataclass(frozen=True, slots=True)
class GenerationReceipt:
    proposer: str
    model: str
    backend: str
    backend_version: str
    seed: int
    prompt_digest: str
    response_digest: str
    candidate_digest: str | None
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_seconds: float
    parse_ok: bool
    error: str | None = None


def render_prompt(task: str, sample: PromptSample[str]) -> str:
    inspirations = "\n\n".join(
        f"INSPIRATION {i}:\n{item.candidate}"
        for i, item in enumerate(sample.inspirations)
    )
    return (
        'You are an evolutionary coding proposer. Return JSON exactly as {"program": "..."}.\n'
        f"TASK:\n{task}\n\nPARENT:\n{sample.parent.candidate}\n\n{inspirations}\n\n"
        f"PUBLIC_FEEDBACK:\n{json.dumps(sample.feedback, sort_keys=True)}\n"
        "Preserve the contract, improve the complete program, and return no prose outside JSON."
    )


def parse_complete_program(text: str) -> str:
    value = text.strip()
    if value.startswith("```"):
        lines = value.splitlines()
        value = "\n".join(
            lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
        ).strip()
    try:
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            if "program" not in parsed:
                raise ValueError("JSON response is missing program")
            value = parsed["program"]
    except json.JSONDecodeError:
        pass
    if not isinstance(value, str) or not value.strip():
        raise ValueError("response did not contain a complete program")
    return value.strip() + "\n"


class LongemmaProposer:
    def __init__(
        self,
        backend: Any,
        task: str,
        *,
        name: str | None = None,
        message_factory: Callable[[str, str], Any] | None = None,
    ):
        self.backend = backend
        self.task = task
        self.name = name or getattr(backend, "name", "longemma")
        self.message_factory = message_factory or (
            lambda role, content: type(
                "Message", (), {"role": role, "content": content}
            )()
        )
        self.receipts: list[GenerationReceipt] = []

    def propose(self, sample: PromptSample[str], rng: random.Random) -> str:
        seed = rng.randrange(2**63)
        prompt = render_prompt(self.task, sample)
        started = time.monotonic()
        try:
            response = self.backend.generate(
                [self.message_factory(role="user", content=prompt)],
                temperature=0.7,
                top_p=0.95,
                seed=seed,
                max_tokens=4096,
            )
            text = str(response.text)
            candidate = parse_complete_program(text)
            error = None
            ok = True
        except Exception as exc:
            text = locals().get("text", "")
            candidate = None
            error = f"{type(exc).__name__}: {exc}"
            ok = False
        usage = getattr(response, "usage", None) if "response" in locals() else None
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0))
        completion_tokens = int(getattr(usage, "completion_tokens", 0))
        total_tokens = int(
            getattr(usage, "total_tokens", prompt_tokens + completion_tokens)
        )
        model = (
            str(getattr(response, "model", self.name))
            if "response" in locals()
            else self.name
        )
        backend_name = (
            str(getattr(response, "backend_name", self.name))
            if "response" in locals()
            else self.name
        )
        backend_version = str(
            getattr(
                response,
                "backend_version",
                getattr(self.backend, "version", "unreported"),
            )
            if "response" in locals()
            else getattr(self.backend, "version", "unreported")
        )
        self.receipts.append(
            GenerationReceipt(
                proposer=self.name,
                model=model,
                backend=backend_name,
                backend_version=backend_version,
                seed=seed,
                prompt_digest=hashlib.sha256(prompt.encode()).hexdigest(),
                response_digest=hashlib.sha256(text.encode()).hexdigest(),
                candidate_digest=(
                    hashlib.sha256(candidate.encode()).hexdigest()
                    if candidate is not None
                    else None
                ),
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                latency_seconds=time.monotonic() - started,
                parse_ok=ok,
                error=error,
            )
        )
        if not ok:
            raise ValueError(error or "generation failed")
        return candidate


__all__ = [
    "GenerationReceipt",
    "LongemmaProposer",
    "parse_complete_program",
    "render_prompt",
]
