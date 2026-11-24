"""Transparent prioritization over publication and release dates."""

import re
from datetime import datetime, timedelta

from radar.models import Evidence, Preferences


def terms(value: str) -> list[str]:
    return [word.strip().casefold() for word in value.split(",") if word.strip()]


def fingerprint(value: str) -> set[str]:
    return set(re.findall(r"[\w.]+", value.casefold()))


def similar(left: Evidence, right: Evidence) -> bool:
    if left.url == right.url:
        return True
    a, b = fingerprint(left.title), fingerprint(right.title)
    return bool(a and b and len(a & b) / len(a | b) >= 0.75)


def rank(
    articles: list[Evidence],
    prefs: Preferences,
    now: datetime,
    covered: list[Evidence] | None = None,
) -> list[Evidence]:
    window = timedelta(hours=prefs.hours)
    focus = set(prefs.topics)
    keywords = terms(prefs.keywords)
    excluded = terms(prefs.excluded)
    practical = {
        "Learning": ("example", "tutorial", "guide"),
        "Research": ("paper", "experiment", "benchmark"),
        "Consulting": ("migration", "integration", "case study"),
        "Portfolio": ("example", "dataset", "demo"),
        "Production": ("performance", "support", "fix", "security"),
    }
    cues = {word for goal in prefs.goals for word in practical.get(goal, ())}
    candidates = []
    for item in articles:
        date = item.coverage_date
        if not date or not now - window <= date <= now:
            continue
        if prefs.sources and item.source not in prefs.sources:
            continue
        tags = set(item.topics)
        if focus and not tags & focus:
            continue
        search = " ".join([item.title, item.excerpt, *item.topics]).casefold()
        if any(term in search for term in excluded) or any(
            similar(item, past) for past in covered or []
        ):
            continue
        score = (
            3 * len(tags & focus) / max(len(tags), 1)
            + 2 * min(2, sum(term in search for term in keywords))
            + 2 * (1 - (now - date) / window)
            + item.quality
            + min(1, sum(cue in search for cue in cues) / 3)
        )
        candidates.append((score, date, str(item.url), item))
    results = []
    for _, _, _, item in sorted(candidates, key=lambda row: row[:3], reverse=True):
        if not any(similar(item, other) for other in results):
            results.append(item)
    return results
