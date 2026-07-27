"""A live-model proposer for candidate programs, with the public/private split.

E70 ran the governed search with a generic AST mutator and no model anywhere.
That was the right first step -- it established that the instrument works end to
end, with a null control at exactly 0.0 and an unselected control at -1.30 -- but
every claim this project makes about self-improvement needs a model in the
proposer slot.

The trust boundary is the point of this module, not the API call.

**What the model may see:** the task prompt (which is public and shipped to any
solver), the current program, and a coarse public feedback line.

**What it must never see:** the hidden cases, the oracle, the reference
solution, or the held-out split.  A proposer that sees the grading set is not
proposing, it is being told the answer, and any improvement it produces measures
nothing.  ``build_prompt`` takes only public inputs by construction, so the
boundary is enforced by the signature rather than by discipline.

Every call returns a receipt in the project's established shape -- prompt and
response digests, token counts, latency -- so a run can be audited afterwards
and so :mod:`recursive_lab.candidate_diversity` can detect the E58 failure, where
six model calls returned one identical program and the experiment reported
``adoption_gate.passed: True`` on a search that never searched.

The client is injected, so the whole module is testable without a network call
and without spending anything.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Protocol


class ProposerError(RuntimeError):
    """Raised when a model response cannot be turned into a candidate."""


@dataclass(frozen=True)
class ProposalReceipt:
    """Auditable record of one model call."""

    proposer: str
    model: str
    prompt_digest: str
    response_digest: str
    candidate_digest: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_seconds: float
    parse_ok: bool
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposer": self.proposer,
            "model": self.model,
            "prompt_digest": self.prompt_digest,
            "response_digest": self.response_digest,
            "candidate_digest": self.candidate_digest,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "latency_seconds": self.latency_seconds,
            "parse_ok": self.parse_ok,
            "error": self.error,
        }


@dataclass
class ProposalResult:
    candidate: str | None
    receipt: ProposalReceipt


class ChatClient(Protocol):
    """Minimal surface, so a mock needs no SDK."""

    def complete(
        self, *, model: str, system: str, user: str, temperature: float, max_tokens: int
    ) -> tuple[str, int, int]:
        """Return (text, prompt_tokens, completion_tokens)."""


SYSTEM_INSTRUCTION = (
    "You repair small Python functions. Return ONLY a Python module defining "
    "solve(n), inside a single ```python fenced block, with no explanation. "
    "Use only integer arithmetic, comparisons, loops, conditionals, local "
    "variables and range(). No imports, no I/O, no other function definitions. "
    "Never discuss or attempt to inspect tests, evaluators, or grading."
)

_FENCE = re.compile(r"```(?:python)?\s*(.*?)```", re.DOTALL)


def build_prompt(task_prompt: str, current_program: str, public_feedback: str) -> str:
    """Assemble the user message from public inputs only.

    The signature is the boundary: there is no parameter through which hidden
    cases, the oracle or the reference solution could reach the model.
    """
    return json.dumps(
        {
            "task": task_prompt,
            "current_program": current_program,
            "public_feedback": public_feedback,
            "instruction": (
                "Return a corrected version of current_program that satisfies "
                "the task contract for every input, including edge cases."
            ),
        },
        sort_keys=True,
        indent=2,
    )


def extract_program(text: str) -> str | None:
    """Pull a program out of a model response, or return None.

    Handles an UNTERMINATED fence, which is the common case when a response is
    cut off at ``max_tokens``.  The closed-fence regex cannot match then, and an
    earlier version fell back to the raw text with the opening ```` ```python ````
    still attached, so every truncated reply became a guaranteed SyntaxError and
    looked like the model failing rather than the parser failing.  That silently
    scored 0/0 valid candidates on a whole task.
    """
    match = _FENCE.search(text)
    if match:
        body = match.group(1)
    else:
        body = text
        fence = body.find("```")
        if fence != -1:
            # Drop everything up to and including the opening fence line.
            newline = body.find("\n", fence)
            body = body[newline + 1 :] if newline != -1 else ""
    body = body.strip()
    if "def solve" not in body:
        return None
    return body + "\n"


@dataclass
class ModelProgramProposer:
    """Proposes candidate programs from public information only."""

    client: ChatClient
    model: str
    temperature: float = 1.0
    max_tokens: int = 1400
    name: str = "model-program-proposer-v1"
    #: When set, replaces SYSTEM_INSTRUCTION. This is how a Strategy becomes the
    #: mutable artifact: everything else about the call is held fixed, so a
    #: measured difference between two runs is attributable to the instruction.
    system_override: str | None = None
    calls: int = field(default=0, init=False)
    total_tokens: int = field(default=0, init=False)

    def propose(
        self, task_prompt: str, current_program: str, public_feedback: str
    ) -> ProposalResult:
        prompt = build_prompt(task_prompt, current_program, public_feedback)
        prompt_digest = hashlib.sha256(prompt.encode()).hexdigest()
        started = time.perf_counter()
        try:
            text, prompt_tokens, completion_tokens = self.client.complete(
                model=self.model,
                system=self.system_override or SYSTEM_INSTRUCTION,
                user=prompt,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
        except Exception as error:  # noqa: BLE001 - recorded, never swallowed
            latency = time.perf_counter() - started
            self.calls += 1
            return ProposalResult(
                None,
                ProposalReceipt(
                    self.name, self.model, prompt_digest, "", "", 0, 0, 0,
                    latency, False, f"{type(error).__name__}: {error}",
                ),
            )
        latency = time.perf_counter() - started
        self.calls += 1
        self.total_tokens += prompt_tokens + completion_tokens
        candidate = extract_program(text)
        return ProposalResult(
            candidate,
            ProposalReceipt(
                proposer=self.name,
                model=self.model,
                prompt_digest=prompt_digest,
                response_digest=hashlib.sha256(text.encode()).hexdigest(),
                candidate_digest=(
                    hashlib.sha256(candidate.encode()).hexdigest() if candidate else ""
                ),
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
                latency_seconds=latency,
                parse_ok=candidate is not None,
                error=None if candidate else "no solve() definition in response",
            ),
        )


class LocalOpenAICompatibleClient:
    """Talks to a local OpenAI-compatible server using only the standard library.

    Used for the self-hosted MLX Gemma server on ``127.0.0.1:12345``.  Deliberately
    dependency-free: no SDK to install, and nothing leaves the machine, so a
    search can run without sending code to a third party or spending anything
    per call.
    """

    def __init__(
        self, base_url: str = "http://127.0.0.1:12345/v1", timeout: float = 300.0
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def complete(
        self, *, model: str, system: str, user: str, temperature: float, max_tokens: int
    ) -> tuple[str, int, int]:
        import urllib.request

        payload = json.dumps(
            {
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
                # Required by this Gemma build: without it the server returns
                # reasoning-only output and the message carries no "content"
                # field at all. Documented in Longemma's README for the same
                # reason -- Aider needs editable content, not reasoning.
                "chat_template_kwargs": {"enable_thinking": False},
            }
        ).encode()
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            body = json.loads(response.read().decode())
        message = body["choices"][0]["message"]
        # Fall back to reasoning content rather than raising: a reasoning-only
        # reply may still contain a usable program, and a hard failure here
        # would silently look like a proposer that produced nothing.
        text = message.get("content") or message.get("reasoning_content") or ""
        usage = body.get("usage", {})
        return (
            text,
            int(usage.get("prompt_tokens", 0) or 0),
            int(usage.get("completion_tokens", 0) or 0),
        )


class OpenAIChatClient:
    """Thin adapter over the OpenAI SDK; constructed only when actually used."""

    def __init__(self, client: Any = None) -> None:
        if client is None:
            try:
                from openai import OpenAI
            except ImportError as error:
                raise ProposerError(
                    "install the openai package to use the live proposer"
                ) from error
            client = OpenAI()
        self._client = client

    def complete(
        self, *, model: str, system: str, user: str, temperature: float, max_tokens: int
    ) -> tuple[str, int, int]:
        response = self._client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        text = response.choices[0].message.content or ""
        usage = getattr(response, "usage", None)
        return (
            text,
            int(getattr(usage, "prompt_tokens", 0) or 0),
            int(getattr(usage, "completion_tokens", 0) or 0),
        )


__all__ = [
    "ChatClient",
    "ModelProgramProposer",
    "LocalOpenAICompatibleClient",
    "OpenAIChatClient",
    "ProposalReceipt",
    "ProposalResult",
    "ProposerError",
    "SYSTEM_INSTRUCTION",
    "build_prompt",
    "extract_program",
]
