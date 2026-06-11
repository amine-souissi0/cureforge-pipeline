"""
Sales / investor agent.
Generates outreach tasks and drafts investor/grant letters using Groq.
"""

import json
from loguru import logger
from core.llm import LLMClient
from core.models import ParsedArticle, ClickUpTask, OutreachLetter, Department

TASK_SYSTEM = """You are a sales operations manager at CureForge AI, a longevity biotech startup.
Generate ClickUp tasks for the sales/investor outreach team.

Return ONLY a JSON array (no markdown):
[
  {
    "name": "action title max 80 chars",
    "description": "who to contact, what opportunity, why it fits CureForge AI",
    "priority": 2,
    "tags": ["grant", "VC", "foundation"]
  }
]
Generate 1-3 tasks maximum."""

LETTER_SYSTEM = """You are a senior grant writer and investor relations specialist for CureForge AI,
a longevity biotech startup with the goal of finding the cure for aging before 2030.

Write a compelling, professional outreach email. It must:
- Open with a specific reference to the recipient organisation's focus area
- Briefly describe the scientific opportunity (2-3 sentences)
- Explain how CureForge AI is positioned to pursue it
- Include a clear ask (meeting, letter of intent, or application)
- Be concise: 200-300 words

Return ONLY a JSON object (no markdown):
{
  "subject": "email subject line",
  "body": "full email body"
}"""


class SalesInvestorAgent:

    def __init__(self):
        self.llm = LLMClient()

    def process(self, article: ParsedArticle) -> tuple[list[ClickUpTask], list[OutreachLetter]]:
        if not article.is_investment_relevant and not article.funding_opportunities:
            logger.info(f"Post {article.post_id}: not investment-relevant, skipping sales agent")
            return [], []

        logger.info(f"Sales agent → post {article.post_id}")

        tasks = self._generate_tasks(article)
        letters = self._draft_letters(article)
        return tasks, letters

    def _generate_tasks(self, article: ParsedArticle) -> list[ClickUpTask]:
        user_msg = f"""Article: {article.title}
Summary: {article.summary}
Funding opportunities: {json.dumps(article.funding_opportunities)}
Target organisations: {json.dumps(article.target_organizations)}
Source: {article.source_url}

Generate sales/investor ClickUp tasks."""

        try:
            task_list = self.llm.call_json(TASK_SYSTEM, user_msg, max_tokens=800)
        except ValueError as e:
            logger.error(f"Sales task generation failed: {e}")
            return []

        if not isinstance(task_list, list):
            task_list = [task_list]

        tasks = []
        for t in task_list:
            tasks.append(ClickUpTask(
                name=t.get("name", "Investor outreach task"),
                description=t.get("description", ""),
                department=Department.SALES,
                priority=int(t.get("priority", 2)),
                tags=t.get("tags", []),
                source_post_url=article.source_url,
            ))
        return tasks

    def _draft_letters(self, article: ParsedArticle) -> list[OutreachLetter]:
        if not article.target_organizations:
            return []

        letters = []
        for org in article.target_organizations[:3]:  # max 3 per article
            user_msg = f"""Organisation: {org}
Scientific context: {article.summary}
Funding opportunities identified: {json.dumps(article.funding_opportunities)}
Source article: {article.source_url}

Draft the outreach email now."""

            try:
                data = self.llm.call_json(LETTER_SYSTEM, user_msg, max_tokens=700)
                letters.append(OutreachLetter(
                    recipient_org=org,
                    subject=data.get("subject", f"Partnership opportunity — {article.title}"),
                    body=data.get("body", ""),
                    source_post_url=article.source_url,
                ))
                logger.info(f"Drafted letter for: {org}")
            except Exception as e:
                logger.error(f"Letter draft failed for {org}: {e}")

        return letters
