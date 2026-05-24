import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from app.agents.reply_classifier import ReplyClassifierAgent
from app.schemas import ReplyClassifierOutput

@pytest.mark.asyncio
async def test_high_confidence_classification():
    with patch("anthropic.AsyncAnthropic") as MockClient:
        mock_instance = MockClient.return_value
        
        mock_response = MagicMock()
        text_block = MagicMock()
        text_block.text = json.dumps({
            "intent": "INTERESTED",
            "confidence": 0.95,
            "reasoning": "Clear interest expressed"
        })
        mock_response.content = [text_block]
        mock_response.usage.input_tokens = 50
        mock_response.usage.output_tokens = 20
        
        mock_instance.messages.create = AsyncMock(return_value=mock_response)

        result = await ReplyClassifierAgent.classify_email("I am interested.", "Cand1")
        assert result.intent == "INTERESTED"
        assert result.confidence == 0.95

@pytest.mark.asyncio
async def test_schema_failure_fallback():
    with patch("anthropic.AsyncAnthropic") as MockClient:
        mock_instance = MockClient.return_value
        
        mock_response = MagicMock()
        text_block = MagicMock()
        text_block.text = "Not a json"
        mock_response.content = [text_block]
        mock_response.usage.input_tokens = 50
        mock_response.usage.output_tokens = 20
        
        mock_instance.messages.create = AsyncMock(return_value=mock_response)

        result = await ReplyClassifierAgent.classify_email("Bad response.", "Cand1", retries=1)
        assert result.intent == "OTHER"
        assert result.confidence == 0.0
        assert result.reasoning == "Failed to parse Claude output"
