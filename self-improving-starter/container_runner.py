"""Disposable Docker runner for untrusted Python candidates.

The immutable governor owns this adapter.  A candidate sees one read-only source
mount and an ephemeral ``/tmp``.  It receives no host environment, credentials,
network, Docker socket, or writable host path.  Resource controls are deliberately
redundant: Docker limits the container and the parent also enforces wall time and
captured-output bounds, then removes the named container on every path.

This is a useful POC boundary, not a proof of perfect isolation.  Production use
should pin an image by digest, review the daemon/runtime configuration, and add a
purpose-built seccomp profile or a stronger VM boundary.
"""

from __future__ import annotations

import math
import os
import re
import signal
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO


_IMAGE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/@:+-]{0,254}\Z")


class ContainerUnavailable(RuntimeError):
    """Raised when the configured immutable candidate runtime is unavailable."""


@dataclass(frozen=True, slots=True)
class ContainerPolicy:
    image: str = "python:3.12-slim"
    timeout_seconds: float = 10.0
    memory_megabytes: int = 128
    cpu_count: float = 1.0
    pids_limit: int = 32
    tmpfs_megabytes: int = 16
    max_output_bytes: int = 64 * 1024

    def __post_init__(self) -> None:
        if not isinstance(self.image, str) or _IMAGE_RE.fullmatch(self.image) is None:
            raise ValueError("image must be a non-empty Docker image reference")
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive and finite")
        if not math.isfinite(self.cpu_count) or self.cpu_count <= 0:
            raise ValueError("cpu_count must be positive and finite")
        for name in ("memory_megabytes", "pids_limit", "tmpfs_megabytes"):
            if type(getattr(self, name)) is not int or getattr(self, name) <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if type(self.max_output_bytes) is not int or self.max_output_bytes < 0:
            raise ValueError("max_output_bytes must be a non-negative integer")


@dataclass(frozen=True, slots=True)
class ContainerRunResult:
    ok: bool
    stdout: str
    stderr: str
    returncode: int
    timed_out: bool
    output_limit_exceeded: bool
    duration_seconds: float
    stdout_bytes: int
    stderr_bytes: int
    image_id: str
    container_name: str
    cleanup_succeeded: bool
    failure_kind: str | None = None


@dataclass
class _Capture:
    limit: int
    retained: bytearray
    total: int = 0

    def add(self, chunk: bytes) -> None:
        self.total += len(chunk)
        room = self.limit - len(self.retained)
        if room > 0:
            self.retained.extend(chunk[:room])


def _docker(*args: str, timeout: float = 10.0) -> subprocess.CompletedProcess[bytes]:
    executable = shutil.which("docker")
    if executable is None:
        raise ContainerUnavailable("Docker executable is unavailable")
    try:
        return subprocess.run(
            [executable, *args],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout,
            env={"PATH": os.defpath},
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as error:
        raise ContainerUnavailable(f"Docker is unavailable: {error}") from error


def resolve_image_id(image: str) -> str:
    """Resolve an already-present image without pulling mutable external state."""

    if not isinstance(image, str) or _IMAGE_RE.fullmatch(image) is None:
        raise ValueError("invalid Docker image reference")
    info = _docker("info", "--format", "{{.ServerVersion}}")
    if info.returncode != 0:
        detail = info.stderr.decode("utf-8", errors="replace").strip()
        raise ContainerUnavailable(f"Docker daemon is unavailable: {detail}")
    inspected = _docker("image", "inspect", "--format", "{{.Id}}", image)
    if inspected.returncode != 0:
        raise ContainerUnavailable(
            f"candidate image {image!r} is not present; pull and review it explicitly"
        )
    image_id = inspected.stdout.decode("ascii", errors="strict").strip()
    if not image_id.startswith("sha256:") or len(image_id) != 71:
        raise ContainerUnavailable("Docker returned an invalid image identity")
    return image_id


def container_runtime_available(image: str = "python:3.12-slim") -> bool:
    try:
        resolve_image_id(image)
    except (ContainerUnavailable, ValueError, UnicodeError):
        return False
    return True


def _reader(
    pipe: BinaryIO,
    capture: _Capture,
    exceeded: threading.Event,
) -> None:
    try:
        while True:
            chunk = pipe.read(16 * 1024)
            if not chunk:
                return
            capture.add(chunk)
            if capture.total > capture.limit:
                exceeded.set()
                return
    except (OSError, ValueError):
        return


def _cleanup_container(name: str) -> bool:
    # `docker rm -f` both stops and removes a running container.  It also closes
    # its output pipes, allowing the bounded reader threads to finish.
    result = _docker("rm", "-f", name, timeout=10.0)
    if result.returncode == 0:
        return True
    detail = (result.stderr + result.stdout).decode("utf-8", errors="replace").lower()
    if "no such container" in detail:
        return True
    # With `--rm`, daemon-side removal can race our explicit cleanup.  Resolve
    # the final state instead of treating a harmless "already in progress"
    # response as a containment failure.
    remaining = _docker(
        "ps", "-a", "--quiet", "--filter", f"name=^{name}$", timeout=10.0
    )
    return remaining.returncode == 0 and not remaining.stdout.strip()


def _kill_cli_group(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(proc.pid, signal.SIGKILL)
        else:  # pragma: no cover - Windows runner is not used in CI here.
            proc.kill()
    except (OSError, ProcessLookupError):
        pass


def run_python_container(
    source: str,
    *,
    argv: tuple[str, ...] = (),
    policy: ContainerPolicy | None = None,
) -> ContainerRunResult:
    """Execute untrusted source under the fixed candidate-plane policy."""

    if not isinstance(source, str):
        raise TypeError("source must be text")
    if any(not isinstance(value, str) for value in argv):
        raise TypeError("argv entries must be text")
    policy = policy or ContainerPolicy()
    image_id = resolve_image_id(policy.image)
    docker_executable = shutil.which("docker")
    if docker_executable is None:  # resolve_image_id normally catches this first.
        raise ContainerUnavailable("Docker executable is unavailable")
    name = "recursive-lab-" + uuid.uuid4().hex
    started = time.monotonic()

    with tempfile.TemporaryDirectory(prefix="recursive-lab-candidate-") as directory:
        root = Path(directory)
        candidate = root / "candidate.py"
        candidate.write_text(source, encoding="utf-8")
        candidate.chmod(0o444)
        root.chmod(0o755)

        create_arguments = [
            "create",
            "--pull",
            "never",
            "--name",
            name,
            "--hostname",
            "candidate",
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--pids-limit",
            str(policy.pids_limit),
            "--memory",
            f"{policy.memory_megabytes}m",
            "--memory-swap",
            f"{policy.memory_megabytes}m",
            "--cpus",
            str(policy.cpu_count),
            "--ulimit",
            "nofile=64:64",
            "--ulimit",
            "fsize=1048576:1048576",
            "--tmpfs",
            f"/tmp:rw,noexec,nosuid,nodev,size={policy.tmpfs_megabytes}m,mode=700,uid=65534,gid=65534",
            "--user",
            "65534:65534",
            "--env",
            "HOME=/tmp",
            "--env",
            "PYTHONDONTWRITEBYTECODE=1",
            "--env",
            "PYTHONHASHSEED=0",
            "--env",
            "PYTHONNOUSERSITE=1",
            "--mount",
            f"type=bind,src={root.resolve()},dst=/candidate,readonly",
            "--workdir",
            "/tmp",
            "--entrypoint",
            "python3",
            image_id,
            "/candidate/candidate.py",
            *argv,
        ]

        created = _docker(*create_arguments, timeout=15.0)
        if created.returncode != 0:
            detail = created.stderr.decode("utf-8", errors="replace").strip()
            raise ContainerUnavailable(f"could not create candidate container: {detail}")

        command = [docker_executable, "start", "--attach", name]

        popen_kwargs: dict[str, object] = {"start_new_session": os.name == "posix"}
        try:
            proc = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=False,
                bufsize=0,
                env={"PATH": os.defpath},
                **popen_kwargs,
            )
        except (FileNotFoundError, OSError) as error:
            try:
                _cleanup_container(name)
            except ContainerUnavailable:
                pass
            raise ContainerUnavailable(f"could not start Docker: {error}") from error

        assert proc.stdout is not None and proc.stderr is not None
        exceeded = threading.Event()
        stdout_capture = _Capture(policy.max_output_bytes, bytearray())
        stderr_capture = _Capture(policy.max_output_bytes, bytearray())
        readers = (
            threading.Thread(
                target=_reader,
                args=(proc.stdout, stdout_capture, exceeded),
                name="container-stdout-reader",
                daemon=True,
            ),
            threading.Thread(
                target=_reader,
                args=(proc.stderr, stderr_capture, exceeded),
                name="container-stderr-reader",
                daemon=True,
            ),
        )
        for reader in readers:
            reader.start()

        timed_out = False
        output_limit_exceeded = False
        deadline = started + policy.timeout_seconds
        while proc.poll() is None:
            if exceeded.is_set():
                output_limit_exceeded = True
                break
            if time.monotonic() >= deadline:
                timed_out = True
                break
            time.sleep(0.02)

        # The container was synchronously created before attaching, so cleanup
        # cannot race a delayed daemon-side create request.
        if timed_out or output_limit_exceeded:
            _kill_cli_group(proc)
        try:
            proc.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            _kill_cli_group(proc)
            proc.wait(timeout=2.0)

        try:
            cleanup_succeeded = _cleanup_container(name)
        except ContainerUnavailable:
            # Cleanup failure is a fail-closed result, not an evaluator crash.
            # A caller can trip an operational alert from this field.
            cleanup_succeeded = False

        for reader in readers:
            reader.join(timeout=1.0)
        for pipe in (proc.stdout, proc.stderr):
            try:
                pipe.close()
            except OSError:
                pass

        duration = time.monotonic() - started
        returncode = proc.returncode if proc.returncode is not None else -1
        failure_kind: str | None = None
        if timed_out:
            failure_kind = "timeout"
        elif output_limit_exceeded:
            failure_kind = "output_limit"
        elif not cleanup_succeeded:
            failure_kind = "cleanup_failed"
        elif returncode != 0:
            failure_kind = "candidate_failed"

        return ContainerRunResult(
            ok=(
                returncode == 0
                and not timed_out
                and not output_limit_exceeded
                and cleanup_succeeded
            ),
            stdout=bytes(stdout_capture.retained).decode("utf-8", errors="replace"),
            stderr=bytes(stderr_capture.retained).decode("utf-8", errors="replace"),
            returncode=returncode,
            timed_out=timed_out,
            output_limit_exceeded=output_limit_exceeded,
            duration_seconds=duration,
            stdout_bytes=stdout_capture.total,
            stderr_bytes=stderr_capture.total,
            image_id=image_id,
            container_name=name,
            cleanup_succeeded=cleanup_succeeded,
            failure_kind=failure_kind,
        )


__all__ = [
    "ContainerPolicy",
    "ContainerRunResult",
    "ContainerUnavailable",
    "container_runtime_available",
    "resolve_image_id",
    "run_python_container",
]
