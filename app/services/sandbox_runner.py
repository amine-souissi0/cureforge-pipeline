"""
Sandbox runner — executes untrusted candidate code in an ephemeral Docker
container with full isolation per §8.1 / §3.2 of the build spec:

  • --network none          no outbound or inbound network
  • --memory 128m           hard memory cap (OOM-killed, not swapped)
  • --cpus 0.5              half a CPU core max
  • --read-only             root filesystem read-only
  • --tmpfs /tmp            writable scratch space, no-exec
  • --cap-drop ALL          all Linux capabilities dropped
  • --no-new-privileges     cannot escalate via setuid/setgid
  • --user nobody           non-root execution
  • wall-clock timeout      container killed after TIMEOUT_SECONDS

Falls back to a restricted subprocess runner if the Docker socket is
unavailable (local dev without Docker Desktop, CI, etc.) — logs a warning.
"""

import logging
import os
import re
import resource
import subprocess
import sys
import textwrap
import time
from dataclasses import dataclass, field
from typing import List, Tuple

log = logging.getLogger(__name__)

TIMEOUT_SECONDS = 10
MEMORY_LIMIT_MB = 128
CPU_QUOTA = 0.5           # fraction of one CPU core
SANDBOX_IMAGE = os.environ.get("SANDBOX_IMAGE", "python:3.11-slim")

# Belt-and-suspenders pre-scan: reject obviously dangerous code before
# even handing it to Docker. Does not replace container isolation.
_DANGEROUS_PATTERNS: List[Tuple[str, str]] = [
    (r"\bimport\s+requests\b",    "network: requests"),
    (r"\bfrom\s+requests\b",      "network: requests"),
    (r"\bimport\s+urllib\b",      "network: urllib"),
    (r"\bfrom\s+urllib\b",        "network: urllib"),
    (r"\bimport\s+socket\b",      "network: socket"),
    (r"\bimport\s+http\b",        "network: http"),
    (r"\bfrom\s+http\b",          "network: http"),
    (r"\bimport\s+ftplib\b",      "network: ftplib"),
    (r"\bimport\s+smtplib\b",     "network: smtplib"),
    (r"\bimport\s+subprocess\b",  "process: subprocess"),
    (r"\bfrom\s+subprocess\b",    "process: subprocess"),
    (r"\bos\.system\s*\(",        "process: os.system"),
    (r"\bos\.popen\s*\(",         "process: os.popen"),
    (r"\bos\.exec[vple]",         "process: os.exec*"),
    (r"\bos\.spawn",              "process: os.spawn*"),
    (r"__import__\s*\(",          "dynamic: __import__"),
]


@dataclass
class TestResult:
    test_id: str
    passed: bool
    stdout: str
    stderr: str
    execution_ms: float
    error: str = ""


@dataclass
class SandboxResult:
    ran: bool
    test_results: List[TestResult] = field(default_factory=list)
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    sandbox_error: str = ""

    @property
    def pass_rate(self) -> float:
        if self.total_tests == 0:
            return 0.0
        return self.passed_tests / self.total_tests


def scan_dangerous_patterns(source_code: str) -> List[str]:
    violations = []
    for pattern, label in _DANGEROUS_PATTERNS:
        if re.search(pattern, source_code):
            violations.append(label)
    return violations


class SandboxRunner:
    """
    Run candidate source code against held-out tests.
    Uses Docker when the socket is available; falls back to subprocess.
    """

    @staticmethod
    def run(
        source_code: str,
        held_out_tests: List[dict],
        timeout: int = TIMEOUT_SECONDS,
        memory_limit_mb: int = MEMORY_LIMIT_MB,
    ) -> SandboxResult:
        if not source_code.strip():
            return SandboxResult(ran=False, sandbox_error="Empty source code.")

        violations = scan_dangerous_patterns(source_code)
        if violations:
            return SandboxResult(
                ran=False,
                sandbox_error=f"Dangerous patterns detected: {', '.join(violations)}",
            )

        runner = _docker_runner if _docker_available() else _subprocess_runner

        test_results: List[TestResult] = []
        for test in held_out_tests:
            result = runner(
                source_code=source_code,
                test_id=test.get("test_id", "unknown"),
                test_input=str(test.get("input", "")),
                expected_output=str(test.get("expected_output", "")),
                timeout=timeout,
                memory_limit_mb=memory_limit_mb,
            )
            test_results.append(result)

        passed = sum(1 for r in test_results if r.passed)
        return SandboxResult(
            ran=True,
            test_results=test_results,
            total_tests=len(test_results),
            passed_tests=passed,
            failed_tests=len(test_results) - passed,
        )


# ---------------------------------------------------------------------------
# Docker runner (primary)
# ---------------------------------------------------------------------------

def _docker_available() -> bool:
    try:
        import docker
        docker.from_env().ping()
        return True
    except Exception:
        log.warning("Docker socket unavailable — falling back to subprocess sandbox")
        return False


def _docker_runner(
    source_code: str,
    test_id: str,
    test_input: str,
    expected_output: str,
    timeout: int,
    memory_limit_mb: int,
) -> TestResult:
    import docker

    harness = _build_harness(source_code, test_input)
    client = docker.from_env()
    container = None
    start = time.monotonic()

    try:
        container = client.containers.run(
            SANDBOX_IMAGE,
            command=["python3", "-c", harness],
            # ── Isolation constraints (§8.1) ──────────────────────────────
            network_disabled=True,                        # --network none
            mem_limit=f"{memory_limit_mb}m",              # --memory
            memswap_limit=f"{memory_limit_mb}m",          # disable swap
            nano_cpus=int(CPU_QUOTA * 1_000_000_000),     # --cpus
            read_only=True,                               # --read-only
            tmpfs={"/tmp": "size=32m,noexec,nosuid"},     # writable /tmp only
            cap_drop=["ALL"],                             # --cap-drop ALL
            security_opt=["no-new-privileges:true"],      # --no-new-privileges
            user="nobody",                                # non-root
            environment={},                               # no env leak
            # ── Lifecycle ─────────────────────────────────────────────────
            detach=True,
            remove=False,
            stdin_open=False,
            tty=False,
        )

        try:
            result = container.wait(timeout=timeout)
            exit_code = result["StatusCode"]
        except Exception:
            container.kill()
            elapsed_ms = (time.monotonic() - start) * 1000
            return TestResult(
                test_id=test_id, passed=False,
                stdout="", stderr="",
                execution_ms=round(elapsed_ms, 2),
                error=f"Timed out after {timeout}s",
            )

        elapsed_ms = (time.monotonic() - start) * 1000
        stdout = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace").strip()
        stderr = container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace").strip()

        passed = exit_code == 0 and stdout == expected_output.strip()
        return TestResult(
            test_id=test_id,
            passed=passed,
            stdout=stdout,
            stderr=stderr,
            execution_ms=round(elapsed_ms, 2),
            error=stderr if exit_code != 0 else "",
        )

    except Exception as e:
        elapsed_ms = (time.monotonic() - start) * 1000
        log.exception("Docker sandbox error for test %s", test_id)
        return TestResult(
            test_id=test_id, passed=False,
            stdout="", stderr="",
            execution_ms=round(elapsed_ms, 2),
            error=f"Docker error: {e}",
        )
    finally:
        if container:
            try:
                container.remove(force=True)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Subprocess fallback (local dev / no Docker socket)
# ---------------------------------------------------------------------------

def _subprocess_runner(
    source_code: str,
    test_id: str,
    test_input: str,
    expected_output: str,
    timeout: int,
    memory_limit_mb: int,
) -> TestResult:
    log.warning("Running test %s in subprocess fallback — NOT production-safe", test_id)
    harness = _build_harness(source_code, test_input)
    start = time.monotonic()
    try:
        proc = subprocess.run(
            [sys.executable, "-c", harness],
            capture_output=True,
            text=True,
            timeout=timeout,
            preexec_fn=_set_rlimits(memory_limit_mb),
        )
        elapsed_ms = (time.monotonic() - start) * 1000
        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip()
        passed = proc.returncode == 0 and stdout == expected_output.strip()
        return TestResult(
            test_id=test_id,
            passed=passed,
            stdout=stdout,
            stderr=stderr,
            execution_ms=round(elapsed_ms, 2),
            error=stderr if proc.returncode != 0 else "",
        )
    except subprocess.TimeoutExpired:
        elapsed_ms = (time.monotonic() - start) * 1000
        return TestResult(
            test_id=test_id, passed=False,
            stdout="", stderr="",
            execution_ms=round(elapsed_ms, 2),
            error=f"Timed out after {timeout}s",
        )
    except Exception as e:
        return TestResult(
            test_id=test_id, passed=False,
            stdout="", stderr="",
            execution_ms=0.0,
            error=f"Runner error: {e}",
        )


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _build_harness(source_code: str, test_input: str) -> str:
    return textwrap.dedent(f"""
{source_code}

# --- held-out test harness ---
import sys as _sys
try:
    _result = eval({test_input!r})
    print(_result)
except Exception as _e:
    print(f"ERROR: {{_e}}", file=_sys.stderr)
    _sys.exit(1)
""")


def _set_rlimits(memory_limit_mb: int):
    def _apply() -> None:
        mem = memory_limit_mb * 1024 * 1024
        try:
            resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
        except (ValueError, resource.error):
            pass
    return _apply
