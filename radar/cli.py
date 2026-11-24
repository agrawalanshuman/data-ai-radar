"""Offline demo, no-key discovery and personal CLI generation."""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from radar.briefing import demo, generate
from radar.config import local_key, settings
from radar.providers import DEFAULT_MODELS, ProviderError
from radar.ranking import rank
from radar.render import feed_markdown, markdown
from radar.sources import discover
from radar.storage import Store


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(prog="data-ai-radar")
    cli.add_argument("action", choices=["demo", "feed", "generate"])
    cli.add_argument("--format", choices=["markdown", "json"], default="markdown")
    cli.add_argument("--output", type=Path)
    cli.add_argument("--provider", choices=DEFAULT_MODELS)
    cli.add_argument("--model")
    cli.add_argument("--dotenv", type=Path, help="Explicit personal credential file")
    cli.add_argument(
        "--once-per-day", metavar="JOB", help="Claim one attempt per local calendar day"
    )
    return cli


def run(args: argparse.Namespace) -> str:
    if args.action == "demo":
        report = demo()
        return report.model_dump_json(indent=2) if args.format == "json" else markdown(report)
    config = settings()
    if not config.local:
        raise ValueError("This CLI workflow requires personal local mode.")
    if args.action == "generate" and not args.provider:
        raise ValueError("Choose a provider with --provider.")
    if args.once_per_day and args.action != "generate":
        raise ValueError("--once-per-day requires generate.")
    store = Store(config.database)
    prefs = store.preferences()
    now = datetime.now(UTC)
    provider = args.provider
    key = local_key(config, provider, args.dotenv) if provider else None
    if provider and provider != "Ollama" and not key:
        raise ProviderError(
            "Supply an explicit local credential file with your selected provider key."
        )
    if provider == "Ollama" and not args.model:
        raise ProviderError("Pass --model with an already-installed Ollama model.")
    result = discover(prefs.sources)
    if result.failed:
        print("Feeds unavailable: " + ", ".join(result.failed), file=sys.stderr)
    if result.date_unavailable:
        print(
            "Release date lookup unavailable: " + ", ".join(result.date_unavailable),
            file=sys.stderr,
        )
    if result.complete_failure:
        raise ValueError("All selected feeds failed.")
    covered = store.covered() if provider else []
    articles = rank(result.articles, prefs, now, covered)
    if not articles:
        print("No dated, eligible stories in the selected window.", file=sys.stderr)
    if args.action == "feed":
        if args.format == "json":
            return json.dumps([item.model_dump(mode="json") for item in articles[:30]], indent=2)
        return feed_markdown(articles[:30], prefs.timezone)
    if not articles:
        return ""
    if args.once_per_day:
        date = now.astimezone(ZoneInfo(prefs.timezone)).date()
        if not store.claim(f"{args.once_per_day}:{date}"):
            print("This job has already claimed an attempt today.", file=sys.stderr)
            return ""
    report = generate(
        prefs,
        articles,
        provider,
        args.model or DEFAULT_MODELS[provider],
        key,
        ollama_url=config.ollama_url,
    )
    store.save_report(report)
    return report.model_dump_json(indent=2) if args.format == "json" else markdown(report)


def main() -> int:
    args = parser().parse_args()
    try:
        result = run(args)
        if result:
            if args.output:
                args.output.write_text(result + "\n", encoding="utf-8")
            else:
                print(result)
    except (ValueError, ProviderError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
