from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum


class Department(str, Enum):
    DEVELOPERS = "developers"
    SALES = "sales"
    OTHER = "other"


class TelegramPost(BaseModel):
    post_id: int
    text: str
    url: str
    posted_at: datetime
    channel: str


class ParsedArticle(BaseModel):
    post_id: int
    title: str
    summary: str
    topics: list[str] = Field(default_factory=list)
    relevant_departments: list[Department] = Field(default_factory=list)

    # Developer fields
    research_tasks: list[str] = Field(default_factory=list)
    technical_keywords: list[str] = Field(default_factory=list)

    # Sales/investor fields
    funding_opportunities: list[str] = Field(default_factory=list)
    target_organizations: list[str] = Field(default_factory=list)
    is_investment_relevant: bool = False

    other_notes: str = ""
    source_url: str = ""


class ClickUpTask(BaseModel):
    name: str
    description: str
    department: Department
    priority: int = 3  # 1=urgent 2=high 3=normal 4=low
    tags: list[str] = Field(default_factory=list)
    source_post_url: str = ""


class OutreachLetter(BaseModel):
    recipient_org: str
    subject: str
    body: str
    source_post_url: str = ""


class AgentResult(BaseModel):
    post_id: int
    tasks_created: list[str] = Field(default_factory=list)
    letters_drafted: list[OutreachLetter] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    processed_at: datetime = Field(default_factory=datetime.utcnow)
