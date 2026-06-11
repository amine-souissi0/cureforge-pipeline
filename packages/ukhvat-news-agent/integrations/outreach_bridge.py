"""
Bridge drafted investor/grant letters into Communication-AI-Agent.

Set COMMUNICATION_AGENT_PATH if the Communication-AI-Agent folder is not a
sibling of this project.
"""

import os
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from loguru import logger


def _communication_agent_path() -> Path:
    default_path = Path(__file__).resolve().parents[2] / "Communication-AI-Agent"
    return Path(os.getenv("COMMUNICATION_AGENT_PATH", default_path)).resolve()


def queue_letters(letters) -> tuple[int, int]:
    comm_path = _communication_agent_path()
    if not comm_path.exists():
        logger.warning(f"Communication-AI-Agent not found at {comm_path}; bridge skipped")
        return 0, len(letters)

    payload = []
    for letter in letters:
        payload.append(
            {
                "recipient_org": letter.recipient_org,
                "subject": letter.subject,
                "body": letter.body,
                "source_post_url": letter.source_post_url,
            }
        )

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(payload, f)
        input_path = Path(f.name)

    try:
        result = subprocess.run(
            [sys.executable, "-m", "scripts.queue_drafted_outreach", "--input", str(input_path)],
            cwd=str(comm_path),
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            logger.error(f"Outreach bridge failed: {result.stderr or result.stdout}")
            return 0, len(letters)

        output = result.stdout.strip()
        queued = _parse_count(output, "queued")
        skipped = _parse_count(output, "skipped")
        logger.info(f"Outreach bridge {output}")
        return queued, skipped
    finally:
        input_path.unlink(missing_ok=True)


def _parse_count(output: str, key: str) -> int:
    for token in output.replace("\n", " ").split():
        if token.startswith(f"{key}="):
            try:
                return int(token.split("=", 1)[1])
            except ValueError:
                return 0
    return 0
