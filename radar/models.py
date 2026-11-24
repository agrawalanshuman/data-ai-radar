"""Validated settings, evidence and export formats."""

from datetime import UTC, datetime
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    StringConstraints,
    field_validator,
)

TOPICS = (
    "SQL/BI",
    "Data platforms",
    "Statistics",
    "Forecasting",
    "Machine learning",
    "LLMs",
    "RAG",
    "Agents",
    "Evaluation",
    "MLOps",
)
GOALS = ("Learning", "Research", "Consulting", "Portfolio", "Production")
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=700)]
Availability = Literal["available", "preview", "research", "announced", "unknown"]
Recommendation = Literal["Try now", "Learn next", "Watch"]


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Preferences(Record):
    topics: list[str] = Field(default_factory=lambda: list(TOPICS), max_length=10)
    goals: list[str] = Field(default_factory=lambda: ["Learning"], max_length=5)
    experience: Literal["Beginner", "Intermediate", "Advanced"] = "Intermediate"
    keywords: str = Field(default="", max_length=300)
    excluded: str = Field(default="", max_length=300)
    sources: list[str] = Field(default_factory=list, max_length=20)
    hours: Literal[24, 72, 168] = 72
    length: Literal["Concise", "Standard", "Detailed"] = "Standard"
    count: int = Field(default=5, ge=1, le=8)
    timezone: str = "UTC"

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError):
            raise ValueError("Choose a valid IANA timezone") from None
        return value


class Evidence(Record):
    source: str
    title: str
    url: HttpUrl
    excerpt: str
    topics: list[str]
    published: AwareDatetime | None = None
    updated: AwareDatetime | None = None
    retrieved: AwareDatetime
    event_date: AwareDatetime | None = None
    quality: float = Field(default=1, ge=0, le=1)

    @property
    def coverage_date(self) -> datetime | None:
        return self.event_date or self.published


class Analysis(Record):
    evidence_id: Annotated[int, Field(ge=1, le=8, strict=True)]
    what_changed: ShortText
    why_it_matters: ShortText
    application: ShortText
    availability: Availability
    recommendation: Recommendation
    limitations: ShortText


class ModelBrief(Record):
    items: list[Analysis] = Field(min_length=1, max_length=8)
    exercise: ShortText
    takeaway: ShortText


class BriefingItem(Record):
    evidence: Evidence
    category: str
    analysis: Analysis


class Briefing(Record):
    mode: Literal["demo", "ai"]
    generated: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))
    timezone: str = "UTC"
    items: list[BriefingItem] = Field(min_length=1, max_length=8)
    exercise: ShortText
    takeaway: ShortText
    provider: str | None = None
    model: str | None = None
    usage: dict[str, int] = Field(default_factory=dict)
