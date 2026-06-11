"""
Developer task agent.
Turns parsed research content into richly-described ClickUp tasks.
"""

import json
from loguru import logger
from core.llm import LLMClient
from core.models import ParsedArticle, ClickUpTask, Department

SYSTEM_PROMPT = """You are a technical project manager at a longevity biotech startup.
Given a parsed scientific article, generate developer tasks for a ClickUp board.

Return ONLY a JSON array (no markdown):
[
  {
    "name": "action-oriented title, max 80 chars",
    "description": "3-5 sentences: what to investigate/build and why it matters for defeating aging",
    "priority": 3,
    "tags": ["relevant", "tags"]
  }
]

Priority: 1=urgent, 2=high, 3=normal, 4=low
Generate 1-4 tasks maximum. Make them specific and actionable."""


class DeveloperTaskAgent:

    def __init__(self):
        self.llm = LLMClient()

    def generate_tasks(self, article: ParsedArticle) -> list[ClickUpTask]:
        if not article.research_tasks and not article.technical_keywords:
            logger.info(f"Post {article.post_id}: no dev content, skipping")
            return []

        logger.info(f"Dev agent → post {article.post_id}")

        user_msg = f"""Article: {article.title}
Summary: {article.summary}
Topics: {', '.join(article.topics)}
Research tasks identified: {json.dumps(article.research_tasks)}
Technical keywords: {', '.join(article.technical_keywords)}
Source: {article.source_url}

Generate developer ClickUp tasks now."""

        try:
            task_list = self.llm.call_json(SYSTEM_PROMPT, user_msg, max_tokens=1200)
        except ValueError as e:
            logger.error(f"Dev agent failed for post {article.post_id}: {e}")
            return []

        if not isinstance(task_list, list):
            task_list = [task_list]

        tasks = []
        for t in task_list:
            tasks.append(ClickUpTask(
                name=t.get("name", "Dev research task"),
                description=t.get("description", ""),
                department=Department.DEVELOPERS,
                priority=int(t.get("priority", 3)),
                tags=t.get("tags", []),
                source_post_url=article.source_url,
            ))

        logger.info(f"Dev agent → {len(tasks)} tasks for post {article.post_id}")
        return tasks
