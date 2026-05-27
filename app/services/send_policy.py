from enum import Enum
from typing import Dict

# Per §5.3: only low-stakes templates auto-send by default.
# Higher-stakes (task assignment, feedback, warm-hold, offer) are draft-for-approval by default;
# auto-send only if founder enables it via set_candidate_mode(id, SendMode.AUTO).
_AUTO_SEND_TEMPLATES = {"acknowledgment", "answer-common-question"}


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
