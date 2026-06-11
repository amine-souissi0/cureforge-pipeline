"""HTTP helpers with simple retries for external APIs."""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)


def post_json(
    url: str,
    payload: dict[str, Any],
    *,
    timeout: float = 15.0,
    max_retries: int = 2,
    backoff_seconds: float = 0.5,
) -> requests.Response:
    """
    POST JSON to url; retry on connection errors, timeouts, and 5xx responses.

    Raises requests.HTTPError on 4xx or terminal failure after retries.
    """
    for attempt in range(max_retries + 1):
        try:
            resp = requests.post(url, json=payload, timeout=timeout)
        except (requests.Timeout, requests.ConnectionError) as exc:
            if attempt < max_retries:
                logger.warning("POST %s transport error (%s), retrying", url, exc)
                time.sleep(backoff_seconds * (attempt + 1))
                continue
            raise

        if resp.status_code >= 500 and attempt < max_retries:
            logger.warning(
                "POST %s returned %s (attempt %s), retrying",
                url,
                resp.status_code,
                attempt + 1,
            )
            time.sleep(backoff_seconds * (attempt + 1))
            continue

        resp.raise_for_status()
        return resp

    raise RuntimeError("post_json: unreachable")  # pragma: no cover
