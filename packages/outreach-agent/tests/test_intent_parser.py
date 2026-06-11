"""
Tests for agents/intent_parser.py

Uses parametrized test cases to cover all intent categories.
OpenAI API calls are mocked.
"""
import json
from unittest.mock import MagicMock, patch

import pytest

from agents.intent_parser import parse_intent
from models.database import ReplyStatus


def _make_openai_response(intent: str):
    """Mock a ChatCompletion response returning the given intent JSON."""
    choice = MagicMock()
    choice.message.content = json.dumps({"intent": intent})
    response = MagicMock()
    response.choices = [choice]
    return response


def _patch_openai(mock_response):
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response
    return patch("agents.intent_parser._get_client", return_value=mock_client)


@pytest.mark.parametrize(
    "intent_str, expected_status",
    [
        ("interested", ReplyStatus.interested),
        ("not_interested", ReplyStatus.not_interested),
        ("needs_info", ReplyStatus.needs_info),
        ("other", ReplyStatus.other),
    ],
)
def test_parse_intent_all_categories(intent_str, expected_status):
    """parse_intent must correctly map each GPT response to the right ReplyStatus."""
    mock_response = _make_openai_response(intent_str)
    with _patch_openai(mock_response):
        result = parse_intent("Some email body text.")

    assert result == expected_status


def test_parse_intent_falls_back_to_other_on_invalid_json():
    """Malformed JSON from GPT should gracefully fall back to ReplyStatus.other."""
    choice = MagicMock()
    choice.message.content = "not valid json at all"
    response = MagicMock()
    response.choices = [choice]

    with _patch_openai(response):
        result = parse_intent("Some body.")

    assert result == ReplyStatus.other


def test_parse_intent_falls_back_to_other_on_unknown_value():
    """An unrecognized intent value from GPT should fall back to ReplyStatus.other."""
    mock_response = _make_openai_response("confused")
    with _patch_openai(mock_response):
        result = parse_intent("Hmm, not sure what to say.")

    assert result == ReplyStatus.other


def test_parse_intent_openai_called_with_body():
    """parse_intent must pass the email body to the OpenAI API."""
    body = "Yes, I am very interested! Let's schedule a call."
    mock_response = _make_openai_response("interested")
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response

    with patch("agents.intent_parser._get_client", return_value=mock_client):
        parse_intent(body)

    messages = mock_client.chat.completions.create.call_args[1]["messages"]
    user_message = next(m for m in messages if m["role"] == "user")
    assert body in user_message["content"]


def test_parse_intent_uses_zero_temperature():
    """Intent classification must use temperature=0 for deterministic output."""
    mock_response = _make_openai_response("interested")
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response

    with patch("agents.intent_parser._get_client", return_value=mock_client):
        parse_intent("body")

    assert mock_client.chat.completions.create.call_args[1]["temperature"] == 0.0
