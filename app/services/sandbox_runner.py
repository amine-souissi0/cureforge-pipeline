import re
import resource
import subprocess
import sys
import textwrap
import time
from dataclasses import dataclass, field
from typing import List, Tuple

TIMEOUT_SECONDS = 10
MEMORY_LIMIT_MB = 128

# Patterns that indicate dangerous operations — blocked before execution.
# Targets network, subprocess spawning, and dynamic import bypasses.
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
    """
    Pre-execution scan for patterns that indicate dangerous operations.

    Returns a list of violation labels. An empty list means the code is safe
    to execute. Called before subprocess launch — fail closed.
    """
    violations = []
    for pattern, label in _DANGEROUS_PATTERNS:
        if re.search(pattern, source_code):
            violations.append(label)
    return violations


class SandboxRunner:
    """
    Execute candidate source code against held-out tests in an isolated subprocess.

    Each test case is injected as a function call appended to the candidate code.
    The subprocess runs with a wall-clock timeout and memory cap.
    No network, no filesystem writes beyond /tmp.
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

        test_results: List[TestResult] = []

        for test in held_out_tests:
            result = _run_single_test(
                source_code=source_code,
                test_id=test.get("test_id", "unknown"),
                test_input=test.get("input", ""),
                expected_output=test.get("expected_output", ""),
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


def _run_single_test(
    source_code: str,
    test_id: str,
    test_input: str,
    expected_output: str,
    timeout: int,
    memory_limit_mb: int,
) -> TestResult:
    """
    Run one held-out test by appending a print statement to the candidate code
    and checking stdout against expected_output (stripped).
    """
    harness = textwrap.dedent(f"""
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

    start = time.monotonic()
    try:
        proc = subprocess.run(
            [sys.executable, "-c", harness],
            capture_output=True,
            text=True,
            timeout=timeout,
            preexec_fn=_set_limits(memory_limit_mb),
        )
        elapsed_ms = (time.monotonic() - start) * 1000
        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip()
        passed = proc.returncode == 0 and stdout == expected_output.strip()
        error = stderr if proc.returncode != 0 else ""
        return TestResult(
            test_id=test_id,
            passed=passed,
            stdout=stdout,
            stderr=stderr,
            execution_ms=round(elapsed_ms, 2),
            error=error,
        )
    except subprocess.TimeoutExpired:
        elapsed_ms = (time.monotonic() - start) * 1000
        return TestResult(
            test_id=test_id,
            passed=False,
            stdout="",
            stderr="",
            execution_ms=round(elapsed_ms, 2),
            error=f"Timed out after {timeout}s",
        )
    except Exception as e:
        return TestResult(
            test_id=test_id,
            passed=False,
            stdout="",
            stderr="",
            execution_ms=0.0,
            error=f"Runner error: {e}",
        )


def _set_limits(memory_limit_mb: int):
    """Return a preexec_fn that sets memory and CPU limits for the child process."""
    def _limits() -> None:
        memory_bytes = memory_limit_mb * 1024 * 1024
        try:
            resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
        except (ValueError, resource.error):
            pass  # some platforms don't support RLIMIT_AS — fail open
    return _limits
