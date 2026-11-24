"""Streamlit entry point. All private state is confined to this session."""

import sqlite3
from datetime import UTC, datetime
from zoneinfo import available_timezones

import streamlit as st
from pydantic import ValidationError

from radar.briefing import demo, generate
from radar.config import Settings, local_key, settings
from radar.models import GOALS, TOPICS, Briefing, Evidence, Preferences
from radar.providers import DEFAULT_MODELS, ProviderError, complete
from radar.ranking import rank
from radar.render import display_date, export_links, markdown, safe_text, source_link
from radar.sources import SOURCES, discover
from radar.storage import Store


@st.cache_data(ttl=600, max_entries=24, show_spinner=False)
def public_discovery(selected: tuple[str, ...]):
    return discover(list(selected))


def credential(config: Settings, provider: str) -> str | None:
    if provider == "Ollama":
        return None
    if st.session_state.get(f"local_{provider}"):
        return local_key(config, provider)
    return st.session_state.get(f"key_{provider}", "").strip() or None


def clear_credentials() -> None:
    for provider in DEFAULT_MODELS:
        st.session_state.pop(f"key_{provider}", None)
        st.session_state.pop(f"local_{provider}", None)


def preferences_ui(prefs: Preferences, store: Store | None, key: str | None) -> None:
    zones = sorted(available_timezones() | {prefs.timezone})
    with st.form("preferences"):
        topics = st.multiselect("Topics", TOPICS, default=prefs.topics)
        goals = st.multiselect("Goals", GOALS, default=prefs.goals)
        experience = st.selectbox(
            "Experience",
            ("Beginner", "Intermediate", "Advanced"),
            index=("Beginner", "Intermediate", "Advanced").index(prefs.experience),
        )
        keywords = st.text_input("Boost keywords (comma-separated)", prefs.keywords, max_chars=300)
        excluded = st.text_input("Exclude terms (comma-separated)", prefs.excluded, max_chars=300)
        sources = st.multiselect(
            "Preferred sources (empty includes all)",
            [s.name for s in SOURCES],
            default=prefs.sources,
        )
        hours = st.selectbox(
            "Coverage",
            (24, 72, 168),
            index=(24, 72, 168).index(prefs.hours),
            format_func={24: "24 hours", 72: "72 hours", 168: "Seven days"}.get,
        )
        length = st.selectbox(
            "Briefing length",
            ("Concise", "Standard", "Detailed"),
            index=("Concise", "Standard", "Detailed").index(prefs.length),
        )
        count = st.slider("Maximum briefing items", 1, 8, prefs.count)
        timezone = st.selectbox("Timezone", zones, index=zones.index(prefs.timezone))
        selected = st.form_submit_button("Save preferences")
    if selected:
        values = Preferences(
            topics=topics,
            goals=goals,
            experience=experience,
            keywords=keywords,
            excluded=excluded,
            sources=sources,
            hours=hours,
            length=length,
            count=count,
            timezone=timezone,
        )
        if key and key in values.model_dump_json():
            st.error("Remove the API key from your preferences.")
            return
        if store:
            store.save_preferences(values)
        st.session_state.prefs = values
        st.rerun()


def toggle_bookmark(article: Evidence, current: bool, store: Store | None) -> None:
    if store:
        store.bookmark(article, not current)
    elif current:
        st.session_state.bookmarked.pop(str(article.url), None)
    else:
        st.session_state.bookmarked[str(article.url)] = article


def show_article(
    article: Evidence,
    prefs: Preferences,
    bookmarks: dict[str, Evidence],
    store: Store | None,
    scope: str,
) -> None:
    url = str(article.url)
    saved = url in bookmarks
    with st.container(border=True):
        st.markdown(f"**{safe_text(article.title)}**")
        st.markdown(source_link(article))
        st.caption(
            f"Publication {display_date(article.published, prefs.timezone)} · "
            f"Release {display_date(article.event_date, prefs.timezone)} · "
            f"Updated {display_date(article.updated, prefs.timezone)} · "
            f"Retrieved {display_date(article.retrieved, prefs.timezone)}"
        )
        st.text(article.excerpt or "No excerpt supplied by the source.")
        st.button(
            "Remove bookmark" if saved else "Bookmark",
            key=f"{scope}:{url}",
            on_click=toggle_bookmark,
            args=(article, saved, store),
        )


def show_report(report: Briefing) -> None:
    st.markdown(markdown(report))
    st.iframe(export_links(report), height=92, alt="Briefing exports")


def main() -> None:
    st.set_page_config(page_title="Data + AI Radar", layout="wide", page_icon="📡")
    st.title("Data + AI Radar")
    st.write(
        "Follow new releases across data, analytics, and AI. Start with the offline demo or fetch live sources."
    )
    try:
        config = settings()
    except ValueError:
        st.error("The operator's deployment configuration is invalid.")
        return
    store = Store(config.database) if config.local else None
    if "prefs" not in st.session_state:
        st.session_state.prefs = store.preferences() if store else Preferences()
        st.session_state.bookmarked = {}
        st.session_state.reports = []
    prefs = st.session_state.prefs
    with st.sidebar:
        st.header("Provider setup")
        options = ["No AI", "OpenAI", "Anthropic", "Gemini"]
        if config.ollama_url:
            options.append("Ollama")
        provider = st.selectbox("Provider", options, key="provider")
        model = ""
        key = None
        credential_error = False
        if provider != "No AI":
            model = st.text_input(
                "Model ID", DEFAULT_MODELS[provider], key=f"model_{provider}", max_chars=120
            ).strip()
            if provider == "Ollama":
                st.caption("Enter a model already installed on the local Ollama server.")
            else:
                st.text_input("Your API key", type="password", key=f"key_{provider}", max_chars=512)
                if config.local and config.dotenv:
                    st.checkbox("Use my configured local credential file", key=f"local_{provider}")
                st.caption(
                    "Requests use your provider account. Connection testing may incur a small charge."
                )
                if not config.local:
                    st.caption(
                        "Keys pass through this host’s backend. Use a local installation to control that boundary."
                    )
            try:
                key = credential(config, provider)
            except ValueError as err:
                credential_error = True
                st.error(str(err))
            if st.button("Test connection", disabled=credential_error):
                try:
                    with st.spinner("Testing the selected provider…"):
                        complete(
                            provider,
                            model,
                            key,
                            "Connection test.",
                            "Reply with OK.",
                            ollama_url=config.ollama_url,
                            test=True,
                        )
                    st.success("The selected model responded.")
                except ProviderError as err:
                    st.error(str(err))
        st.button("Clear credentials", on_click=clear_credentials)
        st.caption(
            "Local storage is active."
            if config.local
            else "Session state is temporary. Export reports before leaving."
        )

    feed, briefing, library, settings_tab = st.tabs(
        ["News feed", "Briefing", "Library", "Preferences"]
    )
    bookmarks = store.bookmarks() if store else st.session_state.bookmarked
    reports = store.reports() if store else st.session_state.reports
    covered = [item.evidence for report in reports if report.mode == "ai" for item in report.items]

    with feed:
        st.header("News feed")
        st.caption(
            "Live source excerpts. Ranking uses topic fit, freshness, keywords, and practical cues."
        )
        if st.button("Fetch live news", type="primary"):
            st.session_state.fetch_news = True
        articles = []
        if st.session_state.get("fetch_news"):
            with st.spinner("Checking release feeds…"):
                discovery = public_discovery(tuple(sorted(prefs.sources)))
            if discovery.complete_failure:
                st.error("Every selected feed failed. Try again when the sources are reachable.")
            else:
                if discovery.failed:
                    st.warning("Unavailable feeds · " + ", ".join(discovery.failed))
                if discovery.date_unavailable:
                    st.warning(
                        "Release dates unavailable · " + ", ".join(discovery.date_unavailable)
                    )
                articles = rank(discovery.articles, prefs, datetime.now(UTC))
                if not articles:
                    st.info(
                        "The feeds responded. No dated items match this window and your preferences."
                    )
                for item in articles[:20]:
                    show_article(item, prefs, bookmarks, store, "feed")
        else:
            st.info("Fetch news to see recent source excerpts for your preferences.")

    with briefing:
        st.header("Briefing")
        demo_col, ai_col = st.columns(2)
        if demo_col.button("Load offline demo"):
            st.session_state.current = demo(prefs.timezone)
        eligible = [
            article
            for article in rank(articles, prefs, datetime.now(UTC), covered)
            if article.excerpt
        ]
        if ai_col.button(
            "Generate AI briefing", disabled=provider == "No AI" or not eligible or credential_error
        ):
            try:
                with st.spinner("Generating a briefing from the selected evidence…"):
                    report = generate(
                        prefs, eligible, provider, model, key, ollama_url=config.ollama_url
                    )
                if store:
                    store.save_report(report)
                else:
                    st.session_state.reports = [report, *reports[:19]]
                st.session_state.current = report
                st.rerun()
            except ProviderError as err:
                st.error(str(err))
        if not eligible:
            st.caption(
                "AI generation requires dated live stories with excerpts that you haven’t covered."
            )
        if st.session_state.get("current"):
            show_report(st.session_state.current)
        else:
            st.info(
                "Load a fictional sample to explore a full briefing without a key or network access."
            )

    with library:
        st.header("Bookmarks")
        if not bookmarks:
            st.info("Bookmark a news item to find it here.")
        for item in bookmarks.values():
            show_article(item, prefs, bookmarks, store, "library")
        st.header("Briefing history")
        if reports:
            selected = st.selectbox(
                "Saved briefing",
                range(len(reports)),
                format_func=lambda i: (
                    f"{i + 1}. {display_date(reports[i].generated, prefs.timezone)} · {reports[i].provider}"
                ),
            )
            show_report(reports[selected])
        else:
            st.info("Generated AI briefings appear here.")

    with settings_tab:
        st.header("Preferences")
        preferences_ui(prefs, store, key)


if __name__ == "__main__":
    try:
        main()
    except (OSError, sqlite3.Error, ValidationError):
        st.error("Radar could not read its local data or configuration.")
