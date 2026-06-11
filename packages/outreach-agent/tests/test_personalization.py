"""
Tests for agents/personalization.py

OpenAI API calls are mocked so no credits are consumed.
"""
from unittest.mock import MagicMock, patch

import pytest

from agents.personalization import DEFAULT_TEMPLATE, default_subject, personalize


def _make_openai_response(content: str):
    """Build a minimal mock that mimics openai ChatCompletion response structure."""
    choice = MagicMock()
    choice.message.content = content
    response = MagicMock()
    response.choices = [choice]
    return response


class TestPersonalize:
    def test_template_variables_are_filled(self, sample_investor):
        """Rendered HTML must contain the investor's name, firm, and the GPT hook."""
        hook = "Your portfolio perfectly complements our longevity platform."
        mock_response = _make_openai_response(hook)

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        with patch("agents.personalization._get_client", return_value=(mock_client, "gpt-4o")):
            result = personalize(sample_investor)

        assert sample_investor["name"] in result
        assert sample_investor["firm"] in result
        assert hook in result

    def test_custom_template_is_used(self, sample_investor):
        """personalize() should use the template string provided, not the default."""
        custom_template = "<p>Hello {{ name }}, hook: {{ personalized_hook }}</p>"
        hook = "Custom hook text."
        mock_response = _make_openai_response(hook)

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        with patch("agents.personalization._get_client", return_value=(mock_client, "gpt-4o")):
            result = personalize(sample_investor, template=custom_template)

        assert f"Hello {sample_investor['name']}" in result
        assert hook in result
        # Default template text should NOT appear
        assert "LongevityInTime" not in result

    def test_openai_called_with_investor_context(self, sample_investor):
        """The prompt sent to OpenAI must include investor details."""
        mock_response = _make_openai_response("some hook")

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        with patch("agents.personalization._get_client", return_value=(mock_client, "gpt-4o")):
            personalize(sample_investor)

        call_kwargs = mock_client.chat.completions.create.call_args
        messages = call_kwargs[1]["messages"] if call_kwargs[1] else call_kwargs[0][1]
        user_message = next(m for m in messages if m["role"] == "user")
        assert sample_investor["firm"] in user_message["content"]
        assert sample_investor["focus_area"] in user_message["content"]

    def test_strips_whitespace_from_hook(self, sample_investor):
        """Extra whitespace in the GPT response should be stripped."""
        mock_response = _make_openai_response("   Trimmed hook.   ")

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        with patch("agents.personalization._get_client", return_value=(mock_client, "gpt-4o")):
            result = personalize(sample_investor)

        assert "Trimmed hook." in result
        assert "   Trimmed hook.   " not in result


class TestDefaultSubject:
    def test_includes_firm_name(self, sample_investor):
        subject = default_subject(sample_investor)
        assert sample_investor["firm"] in subject

    def test_fallback_when_firm_missing(self):
        subject = default_subject({"name": "Bob", "email": "b@x.com"})
        assert "Your Fund" in subject
