"""Exporters also used to render the briefing in the UI."""

import html
import re
from base64 import b64encode
from datetime import datetime
from urllib.parse import quote
from zoneinfo import ZoneInfo

from radar.models import Briefing, Evidence


def safe_text(text: str) -> str:
    # Encode punctuation significant to Markdown and strip newlines in untrusted fields.
    return re.sub(r"[\\`*_{}\[\]()#!|~]", r"\\\g<0>", html.escape(" ".join(text.split())))


def display_date(date: datetime | None, timezone: str) -> str:
    return date.astimezone(ZoneInfo(timezone)).strftime("%Y-%m-%d %H:%M %Z") if date else "Unknown"


def source_link(item: Evidence) -> str:
    url = quote(str(item.url), safe=":/%?=&+#@!$,*;[]")
    return f"[{safe_text(item.source)}]({url})"


def markdown(report: Briefing) -> str:
    title = "Offline demo briefing — fictional sample" if report.mode == "demo" else "AI briefing"
    lines = [f"# {title}", "", f"Generated {display_date(report.generated, report.timezone)}", ""]
    if report.provider and report.model:
        lines.extend(
            [f"Provider and model · {safe_text(report.provider)} / {safe_text(report.model)}", ""]
        )
    for item in report.items:
        article, analysis = item.evidence, item.analysis
        lines.extend(
            [
                f"## {safe_text(article.title)}",
                "",
                f"{safe_text(item.category)} · {analysis.availability.capitalize()} · **{analysis.recommendation}**",
                "",
                f"Publication · {display_date(article.published, report.timezone)}  ",
                f"Release or event · {display_date(article.event_date, report.timezone)}  ",
                f"Primary source · {source_link(article)}",
                "",
            ]
        )
        for heading, value in (
            ("What changed", analysis.what_changed),
            ("Why it matters", analysis.why_it_matters),
            ("Practical application", analysis.application),
            ("Limitations", analysis.limitations),
        ):
            lines.extend([f"**{heading}**", "", safe_text(value), ""])
    lines.extend(
        [
            "## 20–30 minute exercise",
            "",
            safe_text(report.exercise),
            "",
            "## Professional takeaway",
            "",
            safe_text(report.takeaway),
            "",
        ]
    )
    if report.usage:
        usage = ", ".join(f"{name} {count:,}" for name, count in report.usage.items())
        lines.extend([f"Provider-reported tokens · {usage}", ""])
    return "\n".join(lines)


def feed_markdown(articles: list[Evidence], timezone: str) -> str:
    lines = ["# Live feed — source excerpts", ""]
    for item in articles:
        lines.extend(
            [
                f"## {safe_text(item.title)}",
                "",
                f"{source_link(item)} · {display_date(item.coverage_date, timezone)}",
                "",
                safe_text(item.excerpt),
                "",
            ]
        )
    return "\n".join(lines)


def export_links(report: Briefing) -> str:
    """Deliver exports in the active session without a shared server media URL."""
    links = []
    for extension, mime, payload, label in (
        ("md", "text/markdown", markdown(report), "Download Markdown"),
        ("json", "application/json", report.model_dump_json(indent=2), "Download JSON"),
    ):
        encoded = b64encode(payload.encode("utf-8")).decode("ascii")
        links.append(
            f'<a href="data:{mime};base64,{encoded}" download="radar-briefing.{extension}">{label}</a>'
        )
    return (
        '<meta charset="utf-8"><style>'
        "body{margin:0;font:15px system-ui}nav{display:flex;flex-wrap:wrap;gap:8px}"
        "a{border:1px solid #537974;border-radius:8px;color:#145e62;padding:8px 10px;"
        "text-decoration:none}a:hover,a:focus-visible{background:#ebf1ee;text-decoration:underline}"
        '</style><nav aria-label="Briefing exports">' + "".join(links) + "</nav>"
    )
