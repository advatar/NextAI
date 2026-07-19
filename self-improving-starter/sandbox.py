"""Small local runner for trusted fixtures -- **not** a security sandbox.

The runner gives each invocation a fresh working directory, a sanitized
environment, bounded captured output, and a hard wall-clock timeout.  On POSIX
the child also gets its own process group so ordinary descendants are cleaned
up with it.

Those properties are useful failure containment for tests and toy experiments,
but they are not an isolation boundary for hostile code.  Model-written or
otherwise untrusted programs must additionally run in a container/VM under a
restricted user with network, syscall, filesystem, and resource controls.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO


_DEFAULT_OUTPUT_LIMIT = 64 * 1024
_READ_CHUNK_SIZE = 16 * 1024


@dataclass
class RunResult:
    ok: bool  # process exited 0 within the timeout
    stdout: str
    stderr: str
    returncode: int
    timed_out: bool
    duration_s: float = 0.0
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    stdout_bytes: int = 0
    stderr_bytes: int = 0
    termination_signal: int | None = None


@dataclass
class _BoundedCapture:
    """Bytes retained from a pipe plus the total bytes observed."""

    limit: int
    data: bytearray
    total: int = 0

    def add(self, chunk: bytes) -> None:
        self.total += len(chunk)
        remaining = self.limit - len(self.data)
        if remaining > 0:
            self.data.extend(chunk[:remaining])

    @property
    def truncated(self) -> bool:
        return self.total > len(self.data)


def _drain_pipe(pipe: BinaryIO, capture: _BoundedCapture) -> None:
    """Continuously drain a pipe while retaining at most ``capture.limit``."""

    try:
        while True:
            chunk = pipe.read(_READ_CHUNK_SIZE)
            if not chunk:
                return
            capture.add(chunk)
    except (OSError, ValueError):
        # The owner may close the stream during last-resort cleanup.
        return


def _clean_environment(temp_dir: str) -> dict[str, str]:
    """Return a deterministic environment containing no inherited secrets."""

    env = {
        "HOME": temp_dir,
        "LANG": "C.UTF-8",
        "PATH": os.defpath,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONNOUSERSITE": "1",
        "PYTHONSAFEPATH": "1",
        "PYTHONUNBUFFERED": "1",
        "TMPDIR": temp_dir,
    }
    # CPython on Windows needs these to locate system components.
    if os.name == "nt":  # pragma: no cover - exercised on Windows only
        for name in ("SystemRoot", "WINDIR"):
            if name in os.environ:
                env[name] = os.environ[name]
    return env


def _kill_process_group(proc: subprocess.Popen[bytes]) -> None:
    """Best-effort cleanup of the child and its ordinary descendants."""

    if os.name == "posix":
        try:
            os.killpg(proc.pid, signal.SIGKILL)
            return
        except ProcessLookupError:
            return
        except OSError:
            # Fall through to killing the leader when group cleanup is not
            # available (for example, if session creation unexpectedly failed).
            pass
    if proc.poll() is None:
        try:
            proc.kill()
        except ProcessLookupError:
            pass


def _render_output(data: bytearray, *, limit: int, marker: bytes = b"") -> str:
    """Decode bounded output, reserving tail space for a runner marker."""

    raw = bytes(data[:limit])
    if marker and limit:
        marker = marker[:limit]
        raw = raw[: max(0, limit - len(marker))] + marker
    return raw.decode("utf-8", errors="replace")


def run_python(
    source: str,
    *,
    timeout_s: float = 20.0,
    argv: list[str] | None = None,
    max_output_bytes: int = _DEFAULT_OUTPUT_LIMIT,
) -> RunResult:
    """Run a Python fixture with local failure containment.

    This helper is intentionally limited to trusted fixtures.  It is not a
    security sandbox and must not be the sole boundary around hostile code.
    Captured stdout and stderr are each limited to ``max_output_bytes``.
    """

    if timeout_s <= 0:
        raise ValueError("timeout_s must be positive")
    if max_output_bytes < 0:
        raise ValueError("max_output_bytes must be non-negative")

    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="local-python-run-") as temp_dir:
        script = Path(temp_dir) / "candidate.py"
        script.write_text(source, encoding="utf-8")
        # macOS commonly exposes /var as a symlink to /private/var.  Use the
        # canonical directory in the child environment so HOME/TMPDIR agree
        # with os.getcwd() and do not leak a parent path by accident.
        child_temp_dir = str(Path(temp_dir).resolve())

        popen_kwargs: dict[str, object] = {}
        if os.name == "posix":
            popen_kwargs["start_new_session"] = True
        elif os.name == "nt":  # pragma: no cover - exercised on Windows only
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

        try:
            proc = subprocess.Popen(
                [sys.executable, str(script), *(argv or [])],
                cwd=temp_dir,
                env=_clean_environment(child_temp_dir),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=False,
                bufsize=0,
                **popen_kwargs,
            )
        except OSError as exc:
            duration = time.perf_counter() - started
            message = f"[runner error: {type(exc).__name__}: {exc}]".encode()
            stderr = _render_output(bytearray(message), limit=max_output_bytes)
            return RunResult(
                False,
                "",
                stderr,
                -1,
                False,
                duration_s=duration,
                stderr_bytes=len(message),
                stderr_truncated=len(message) > max_output_bytes,
            )

        assert proc.stdout is not None
        assert proc.stderr is not None
        stdout_capture = _BoundedCapture(max_output_bytes, bytearray())
        stderr_capture = _BoundedCapture(max_output_bytes, bytearray())
        readers = [
            threading.Thread(
                target=_drain_pipe,
                args=(proc.stdout, stdout_capture),
                name="fixture-stdout-reader",
                daemon=True,
            ),
            threading.Thread(
                target=_drain_pipe,
                args=(proc.stderr, stderr_capture),
                name="fixture-stderr-reader",
                daemon=True,
            ),
        ]
        for reader in readers:
            reader.start()

        timed_out = False
        try:
            proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            # Popen runs in binary mode, so no TimeoutExpired bytes/str values
            # are concatenated here.  The dedicated readers own all output.
            timed_out = True
            _kill_process_group(proc)
            proc.wait()
        finally:
            # A successful leader may leave a child holding a capture pipe open.
            # Clean up the session before joining readers so that cannot hang us.
            _kill_process_group(proc)

        for reader in readers:
            reader.join(timeout=1.0)
        for pipe in (proc.stdout, proc.stderr):
            try:
                pipe.close()
            except OSError:
                pass
        for reader in readers:
            reader.join(timeout=0.1)

        duration = time.perf_counter() - started
        returncode = proc.returncode if proc.returncode is not None else -1
        termination_signal = -returncode if returncode < 0 and os.name == "posix" else None
        stderr_marker = b"\n[timeout]" if timed_out else b""
        return RunResult(
            ok=not timed_out and returncode == 0,
            stdout=_render_output(stdout_capture.data, limit=max_output_bytes),
            stderr=_render_output(
                stderr_capture.data,
                limit=max_output_bytes,
                marker=stderr_marker,
            ),
            returncode=returncode,
            timed_out=timed_out,
            duration_s=duration,
            stdout_truncated=stdout_capture.truncated,
            stderr_truncated=stderr_capture.truncated,
            stdout_bytes=stdout_capture.total,
            stderr_bytes=stderr_capture.total,
            termination_signal=termination_signal,
        )
