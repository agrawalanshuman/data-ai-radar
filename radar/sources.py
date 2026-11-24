"""Curated release feeds and original research. Entry links are display-only."""

import html
import json
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from time import struct_time
from urllib.parse import unquote, urlsplit

import feedparser
import httpx

from radar.models import Evidence
from radar.network import NetworkFailure, read_response


@dataclass(frozen=True)
class Source:
    name: str
    repository: str | None
    topics: tuple[str, ...]

    @property
    def url(self) -> str:
        if self.repository:
            return f"https://github.com/{self.repository}/releases.atom"
        return "https://export.arxiv.org/api/query"


SOURCES = (
    Source("DuckDB", "duckdb/duckdb", ("SQL/BI", "Data platforms")),
    Source("dbt Core", "dbt-labs/dbt", ("SQL/BI", "Data platforms")),
    Source("statsmodels", "statsmodels/statsmodels", ("Statistics", "Forecasting")),
    Source("scikit-learn", "scikit-learn/scikit-learn", ("Machine learning", "Evaluation")),
    Source("PyTorch", "pytorch/pytorch", ("Machine learning", "MLOps")),
    Source("Ollama", "ollama/ollama", ("LLMs", "Agents")),
    Source("Transformers", "huggingface/transformers", ("LLMs", "RAG", "Agents")),
    Source("MLflow", "mlflow/mlflow", ("MLOps", "Evaluation", "Agents")),
    Source("arXiv AI and ML", None, ("Machine learning", "LLMs", "Statistics", "Evaluation")),
)


class PlainText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def plain_text(value: str, limit: int) -> str:
    parser = PlainText()
    parser.feed(value[:16_000])
    parser.close()
    return re.sub(r"\s+", " ", " ".join(parser.parts)).strip()[:limit]


def as_date(value: struct_time | None) -> datetime | None:
    return datetime(*value[:6], tzinfo=UTC) if value else None


def parse_feed(source: Source, body: bytes, now: datetime) -> list[Evidence]:
    parsed = feedparser.parse(body, resolve_relative_uris=False)
    if parsed.version not in {"atom10", "atom03", "rss20", "rss10", "rss091u", "rss092"}:
        raise ValueError("Unrecognized feed.")
    results = []
    for entry in parsed.entries[:30]:
        link = urlsplit(entry.get("link", ""))
        if source.repository:
            prefix = f"/{source.repository}/releases/tag/"
            if (
                link.netloc != "github.com"
                or link.scheme != "https"
                or not link.path.startswith(prefix)
            ):
                continue
            url = f"https://github.com{link.path}"
        else:
            paper = re.fullmatch(r"/abs/(\d{4}\.\d{4,5})(?:v\d+)?", link.path)
            if (
                link.netloc not in {"arxiv.org", "export.arxiv.org"}
                or link.scheme not in {"http", "https"}
                or not paper
            ):
                continue
            url = f"https://arxiv.org/abs/{paper[1]}"
        title = plain_text(entry.get("title", ""), 200)
        if not title:
            continue
        published = as_date(entry.get("published_parsed"))
        # GitHub often supplies only Atom updated. It is never a release date.
        results.append(
            Evidence(
                source=source.name,
                title=title
                if title.casefold().startswith(source.name.casefold())
                else f"{source.name} {title}",
                url=url,
                excerpt=plain_text(entry.get("summary", ""), 1800),
                topics=list(source.topics),
                published=published,
                updated=as_date(entry.get("updated_parsed")),
                retrieved=now,
                quality=1 if source.repository else 0.85,
            )
        )
    return results


def enrich_release_dates(client: httpx.Client, source: Source, entries: list[Evidence]) -> None:
    """Use the official GitHub release API when Atom omits publication dates."""
    payload = read_response(
        client,
        "GET",
        f"https://api.github.com/repos/{source.repository}/releases",
        params={"per_page": 30},
        limit=600_000,
        seconds=5,
        headers={"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"},
    )
    releases = json.loads(payload)
    if not isinstance(releases, list):
        raise ValueError("Unrecognized release response.")
    dates = {
        release["tag_name"]: release["published_at"]
        for release in releases
        if isinstance(release, dict) and release.get("tag_name") and release.get("published_at")
    }
    for entry in entries:
        tag = unquote(entry.url.path.split("/releases/tag/", 1)[1])
        if tag in dates:
            entry.event_date = release_date(dates[tag])


def release_date(value: str) -> datetime | None:
    try:
        date = datetime.fromisoformat(value)
        return date if date.tzinfo else None
    except (ValueError, TypeError):
        return None


def release_page_dates(body: bytes, source: Source) -> dict[str, datetime]:
    """Read the release timestamp, ignoring asset, commit and edited dates."""
    sections = re.split(
        r'<section\b[^>]*\bdata-release-anchor="', body.decode("utf-8", errors="replace")
    )
    link_pattern = rf'href="(/{re.escape(source.repository)}/releases/tag/[^"]+)"'
    dates = {}
    for section in sections[1:]:
        header = section.split("</section>", 1)[0]
        link = re.search(link_pattern, header)
        timestamp = re.search(r'released this\s*<relative-time\b[^>]*datetime="([^"]+)"', header)
        if link and timestamp and (date := release_date(timestamp[1])):
            dates[unquote(html.unescape(link[1]))] = date
    return dates


def dates_from_release_page(client: httpx.Client, source: Source, articles: list[Evidence]) -> bool:
    body = read_response(
        client,
        "GET",
        f"https://github.com/{source.repository}/releases",
        limit=4_000_000,
        seconds=6,
    )
    dates = release_page_dates(body, source)
    for article in articles:
        if article.event_date is None:
            article.event_date = dates.get(unquote(article.url.path))
    return bool(dates)


@dataclass
class Discovery:
    articles: list[Evidence]
    failed: list[str]
    date_unavailable: list[str]
    attempted: int

    @property
    def complete_failure(self) -> bool:
        return self.attempted > 0 and len(self.failed) == self.attempted


def discover(selected: list[str]) -> Discovery:
    sources = [source for source in SOURCES if not selected or source.name in selected]
    now = datetime.now(UTC)

    def fetch(source: Source) -> tuple[list[Evidence], bool, bool]:
        try:
            with httpx.Client(trust_env=True) as client:
                params = (
                    None
                    if source.repository
                    else {
                        "search_query": "cat:cs.AI OR cat:cs.LG",
                        "max_results": 30,
                        "sortBy": "submittedDate",
                        "sortOrder": "descending",
                    }
                )
                body = read_response(
                    client,
                    "GET",
                    source.url,
                    params=params,
                    limit=4_000_000,
                    seconds=6,
                    retries=1 if source.repository else 0,
                )
                articles = parse_feed(source, body, now)
                if (
                    not source.repository
                    or not articles
                    or all(item.published for item in articles)
                ):
                    return articles, False, False
                try:
                    enrich_release_dates(client, source, articles)
                except (NetworkFailure, ValueError, TypeError, OverflowError):
                    try:
                        found = dates_from_release_page(client, source, articles)
                    except NetworkFailure:
                        found = False
                    return articles, False, not found
                return articles, False, False
        except (NetworkFailure, ValueError, OverflowError):
            return [], True, False

    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(fetch, sources))
    return Discovery(
        [item for articles, _, _ in results for item in articles],
        [source.name for source, (_, failed, _) in zip(sources, results, strict=True) if failed],
        [source.name for source, (_, _, missing) in zip(sources, results, strict=True) if missing],
        len(sources),
    )
