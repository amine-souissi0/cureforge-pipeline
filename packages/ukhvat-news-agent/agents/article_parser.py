"""
Article parser agent.
Uses Groq/LLaMA to extract structured data from a longevity article.
"""

from loguru import logger
from core.llm import LLMClient
from core.models import TelegramPost, ParsedArticle, Department

SYSTEM_PROMPT = """You are an expert scientific analyst specialising in longevity research and biogerontology.
Read a summary/article from a longevity science news channel and extract structured information.

Return ONLY a valid JSON object with exactly these keys (no markdown, no explanation):
{
  "title": "short descriptive title",
  "summary": "2-3 sentence plain-English summary",
  "topics": ["topic", "tags"],
  "relevant_departments": ["one or more of: developers, sales, other"],
  "research_tasks": ["specific technical tasks for developers, e.g. Investigate FOXO3 pathway inhibitors"],
  "technical_keywords": ["genes", "compounds", "methods mentioned"],
  "funding_opportunities": ["specific grants or investment calls mentioned"],
  "target_organizations": ["specific VCs, foundations, agencies to approach"],
  "is_investment_relevant": true,
  "other_notes": "anything for PR, legal, partnerships, etc."
}

Rules:
- research_tasks must be concrete and actionable
- Always include at least one department
- is_investment_relevant: true if article mentions funding, grants, clinical trials, or commercial applications
- Return ONLY the JSON object"""


class ArticleParserAgent:

    def __init__(self):
        self.llm = LLMClient()

    def parse(self, post: TelegramPost) -> ParsedArticle:
        logger.info(f"Parsing post {post.post_id}: {post.url}")

        user_msg = f"""Article URL: {post.url}
Posted: {post.posted_at.strftime('%Y-%m-%d %H:%M UTC')}

Article text:
{post.text}

Extract structured information now."""

        try:
            data = self.llm.call_json(SYSTEM_PROMPT, user_msg, max_tokens=1200)
        except ValueError:
            logger.warning(f"Parser fallback for post {post.post_id}")
            data = {
                "title": f"Post {post.post_id}",
                "summary": post.text[:300],
                "topics": [],
                "relevant_departments": ["developers"],
                "research_tasks": [f"Review article: {post.url}"],
                "technical_keywords": [],
                "funding_opportunities": [],
                "target_organizations": [],
                "is_investment_relevant": False,
                "other_notes": "",
            }

        # Normalise departments to enum
        depts = []
        for d in data.get("relevant_departments", ["developers"]):
            try:
                depts.append(Department(d.lower().strip()))
            except ValueError:
                depts.append(Department.OTHER)

        return ParsedArticle(
            post_id=post.post_id,
            title=data.get("title", ""),
            summary=data.get("summary", ""),
            topics=data.get("topics", []),
            relevant_departments=depts,
            research_tasks=data.get("research_tasks", []),
            technical_keywords=data.get("technical_keywords", []),
            funding_opportunities=data.get("funding_opportunities", []),
            target_organizations=data.get("target_organizations", []),
            is_investment_relevant=bool(data.get("is_investment_relevant", False)),
            other_notes=data.get("other_notes", ""),
            source_url=post.url,
        )
