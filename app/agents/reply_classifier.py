import json
import anthropic
from typing import Optional
from app.schemas import ReplyClassifierOutput, AuditLog

class ReplyClassifierAgent:
    MODEL = "claude-3-5-haiku-20241022"
    MAX_TOKENS = 500
    TEMPERATURE = 0.0

    @staticmethod
    async def classify_email(email_body: str, candidate_context: str, retries: int = 1) -> ReplyClassifierOutput:
        client = anthropic.AsyncAnthropic(api_key="mock_api_key") # Typically from AWS Secrets Manager
        
        prompt = f"""
        Classify the intent of the following email from a candidate.
        Candidate Context: {candidate_context}
        Email Body: {email_body}
        
        Respond ONLY with a valid JSON matching this schema:
        {{
            "intent": "string (INTERESTED, NOT_INTERESTED, QUESTION, OTHER)",
            "confidence": "float (0.0 to 1.0)",
            "reasoning": "string"
        }}
        """

        for attempt in range(retries + 1):
            try:
                response = await client.messages.create(
                    model=ReplyClassifierAgent.MODEL,
                    max_tokens=ReplyClassifierAgent.MAX_TOKENS,
                    temperature=ReplyClassifierAgent.TEMPERATURE,
                    messages=[{"role": "user", "content": prompt}]
                )
                
                content = response.content[0].text
                tokens_in = response.usage.input_tokens
                tokens_out = response.usage.output_tokens
                
                await AuditLog.append("claude_api_call", {
                    "model": ReplyClassifierAgent.MODEL,
                    "tokens_in": tokens_in,
                    "tokens_out": tokens_out,
                    "cost_estimate": (tokens_in * 0.25 / 1000000) + (tokens_out * 1.25 / 1000000)
                })

                # Schema validation
                parsed = json.loads(content)
                output = ReplyClassifierOutput(**parsed)
                
                if output.confidence < 0.75 or output.intent == "OTHER":
                    await AuditLog.append("human_routing_triggered", {"reason": "Low confidence or OTHER intent", "output": parsed})
                
                return output

            except (json.JSONDecodeError, ValueError) as e:
                await AuditLog.append("schema_validation_failure", {"attempt": attempt, "error": str(e)})
                if attempt == retries:
                    await AuditLog.append("human_routing_triggered", {"reason": "Schema failure exhaust"})
                    # Fallback
                    return ReplyClassifierOutput(intent="OTHER", confidence=0.0, reasoning="Failed to parse Claude output")
            except Exception as e:
                await AuditLog.append("claude_api_error", {"error": str(e)})
                return ReplyClassifierOutput(intent="OTHER", confidence=0.0, reasoning="API error")
        
        return ReplyClassifierOutput(intent="OTHER", confidence=0.0, reasoning="Unexpected end of retries")
