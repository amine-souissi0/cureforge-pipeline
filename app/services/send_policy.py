from enum import Enum
from typing import Dict

# Templates that may auto-send without founder approval
_AUTO_SEND_TEMPLATES = {"acknowledgment"}


class SendMode(str, Enum):
    AUTO = "auto"
    DRAFT = "draft"


_candidate_overrides: Dict[str, SendMode] = {}


def set_candidate_mode(candidate_id: str, mode: SendMode) -> None:
    """Override the send mode for a specific candidate."""
    _candidate_overrides[candidate_id] = mode


def get_send_mode(candidate_id: str, template_id: str) -> SendMode:
    """
    Determine whether to auto-send or draft for approval.

    Per-candidate override wins. Otherwise, only simple acknowledgments
    auto-send; everything else is drafted for founder review.
    """
    if candidate_id in _candidate_overrides:
        return _candidate_overrides[candidate_id]

    if template_id in _AUTO_SEND_TEMPLATES:
        return SendMode.AUTO

    return SendMode.DRAFT
