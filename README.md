# Data + AI Radar

Data + AI Radar turns maintainer releases and original research into a personalized technology briefing. Browse recent source excerpts without an account, open an offline sample, or generate a briefing with your own provider credentials. The application runs locally with Streamlit and has a standalone CLI.

## Quick start

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and open a terminal in the checkout. The same commands work on macOS, Linux, and Windows PowerShell. Python 3.12 is the recommended default. uv can install it when needed.

```shell
uv sync --locked --python 3.12
uv run --no-sync data-ai-radar demo --output radar-demo.md
uv run --no-sync streamlit run radar/app.py
```

Open the local address Streamlit prints, normally `http://127.0.0.1:8501`. Go to **Briefing → Load offline demo** to try both exports without network access after installation. The stories are fictional examples. Their links point to the real projects’ release indexes. See [the bundled sample](radar/data/demo.json).

Use **Preferences** to choose topics, goals, experience, coverage window, briefing length, item count, timezone, and preferred sources. Separate keywords and exclusions with commas. **Fetch live news** shows dated stories and excerpts from the selected sources. Bookmark a story to save it in your library. To generate an AI briefing, select a provider, configure an eligible model, and click **Generate AI briefing** after fetching sources.

## Provider setup

| Provider | Example model ID | Interface and model reference |
| --- | --- | --- |
| OpenAI | `gpt-4.1-mini` | [Chat Completions](https://platform.openai.com/docs/api-reference/chat/create) · [Model IDs](https://github.com/openai/openai-python/blob/main/src/openai/types/shared/chat_model.py) |
| Anthropic | `claude-sonnet-4-6` | [Messages](https://docs.anthropic.com/en/api/messages) · [Model IDs](https://github.com/anthropics/anthropic-sdk-python/blob/main/src/anthropic/types/model_param.py) |
| Google Gemini | `gemini-3.5-flash-lite` | [generateContent](https://ai.google.dev/api/generate-content) · [Official SDK examples](https://github.com/googleapis/python-genai) |
| Ollama | Your installed model ID | [Local chat endpoint](https://docs.ollama.com/api/chat) |

Model access and availability depend on your account and can change. Use a chat model compatible with the listed endpoint and JSON output. Enter your own hosted-provider key in the masked field. **Test connection** asks the selected model for a short response and may incur a small charge. **Clear credentials** clears the session’s entered keys and local-file selections. A missing key or rejected request stops generation. Each model request is an explicit user action and receives a 3,500-token output cap for generation or 32 for a connection test. Provider-reported input, output and thinking usage is shown when available. Your provider bills your account at its current rates. Hosting is a separate expense.

For Ollama, start the local server, run `ollama list`, and paste an installed model ID. Radar never pulls a model. Check the model’s memory requirements against your RAM or GPU VRAM. CPU inference works for some models and may be slow. Ollama is available in personal mode and connects to the server running Radar. On a hosted server, localhost refers to that server.

### Optional local credential file

Copy `.env.example` to `.env` and fill in your own provider key. Restrict file permissions to your OS user. For the CLI, pass `--dotenv .env`. To enable the file checkbox in the local UI, set the operator variable before starting Streamlit.

```bash
export RADAR_DOTENV=.env
uv run --no-sync streamlit run radar/app.py
```

```powershell
$env:RADAR_DOTENV = ".env"
uv run --no-sync streamlit run radar/app.py
```

Radar reads the file only when explicitly configured and selected. It never falls back to provider key environment variables.

## Deployment and privacy

- **Personal local mode** is the default. Streamlit binds to loopback. Preferences, bookmarks, and AI briefing history are stored in `~/.data-ai-radar/history.sqlite3`. Override the path with `RADAR_DB`. Treat the database and exports as personal data. AI providers receive the selected preferences and source excerpts during generation.
- **Shared hosted mode** is selected by the operator with `RADAR_MODE=hosted`. The app keeps preferences, credentials, bookmarks, and reports in private session state in server memory. Export a report before leaving. Downloads are generated from the report in the active browser session. A temporary disconnect can preserve the session until Streamlit expires it. Public source results may be cached across sessions for up to ten minutes. Local credential files, SQLite history, and Ollama are disabled in hosted mode.
- The masked field sends credentials to the host backend. The backend sends them only to the selected provider API in an authentication header. Run locally if you want to control this boundary. Keep HTTPS and WebSocket support enabled through a trusted reverse proxy in hosted mode. Keep Streamlit bound to a private interface or loopback behind the proxy, retain its default CORS and XSRF protections, and avoid request-body or header logging. Use infrastructure access controls if you need authenticated hosting. The app supplies no authentication or hosted scheduling.
- The app never accepts custom source URLs from users. It fetches fixed HTTPS endpoints, disallows redirects, and never makes requests to links embedded in release notes or generated text. Operator-configured proxy and DNS infrastructure are trusted. For hosted deployments, restrict egress to the documented feed and provider hosts and block internal and metadata destinations at the infrastructure layer.

For example, a [Caddy](https://caddyserver.com/docs/quick-starts/reverse-proxy) deployment can terminate TLS and proxy Streamlit's WebSockets with the following Caddyfile. Replace the example hostname with your own DNS name and allow inbound ports 80 and 443 for Caddy. Launch the app with `RADAR_MODE=hosted` and keep port 8501 on loopback.

```caddyfile
radar.example.com {
    reverse_proxy 127.0.0.1:8501
}
```

Start Caddy with `caddy run --config Caddyfile` or install it as a service for your platform.

### Docker

```shell
docker compose up --build
```

Compose publishes port 8501 on host loopback and retains local SQLite data in the `radar-data` volume. Run `docker compose down` to stop it. Set `RADAR_MODE=hosted` in the shell before launching Compose to use session-only state. Put an HTTPS reverse proxy in front of the published port for a shared installation.

For a managed network that intercepts HTTPS, supply its trusted CA bundle at build time with `docker build --secret id=radar_ca,src=/path/to/ca-bundle.pem -t data-ai-radar .`. For Compose builds, provide the same `radar_ca` build secret through an operator override. Configure the container's runtime trust separately, for example by mounting the full CA bundle read-only and pointing `SSL_CERT_FILE` to it. Keep TLS verification enabled.

The container uses `http://host.docker.internal:11434` for local Ollama by default. On Docker Desktop, ensure the Ollama service can accept connections from the container. On Linux, Compose maps that name to the host gateway. If Ollama listens only on host loopback, configure it to listen on an interface reachable from the bridge and firewall the port against other access. If you run Ollama as a separate service on the Compose network, set `RADAR_OLLAMA_URL=http://ollama:11434` and manage its model storage yourself.

## Independent CLI and scheduling

```shell
uv run --no-sync data-ai-radar demo --format json --output radar-demo.json
uv run --no-sync data-ai-radar feed
uv run --no-sync data-ai-radar generate --provider OpenAI --model gpt-4.1-mini --dotenv .env --output briefing.md
uv run --no-sync data-ai-radar generate --provider Ollama --model YOUR_INSTALLED_MODEL
```

The CLI reads preferences saved in the local UI or uses defaults. It writes successful AI reports to the same database. Generation is on demand. For a personal schedule, run the CLI once each morning with `--once-per-day morning`. The SQLite claim allows one generation attempt per job name per calendar day in the saved IANA timezone. Keep the database and job name stable across runs. A failed or interrupted model request consumes that day’s scheduled attempt to avoid billing a second call after an uncertain response. A manual run without the flag can retry it. Empty windows and retrieval failures leave the slot available.

**Linux or macOS cron.** Use absolute paths and your scheduler’s timezone. Cron implementations vary in their support for `CRON_TZ`. The sample runs at 08:00 according to the cron daemon. Avoid DST transition hours. A schedule may be skipped during a spring-forward gap or invoked twice during a fall-back overlap. The database claim prevents a second model attempt on that local date.

```cron
0 8 * * * /absolute/radar/.venv/bin/data-ai-radar generate --provider OpenAI --dotenv /absolute/radar/.env --once-per-day morning --output /absolute/radar/briefing.md
```

**Windows Task Scheduler.** Create a daily task at 08:00 in the machine’s local time. Set the program to `C:\path\to\radar\.venv\Scripts\data-ai-radar.exe` and set the arguments to `generate --provider OpenAI --dotenv "C:\path\to\radar\.env" --once-per-day morning --output "C:\path\to\radar\briefing.md"`. Run as the same user who owns the SQLite database and credential file. Select **Do not start a new instance** for overlapping runs. Scheduler time follows Windows DST rules. Use the desired local timezone in Windows and the app if they should agree on the day.

## Source catalog and ranking

GitHub release notes are primary maintainer evidence. The integration uses Atom for excerpts and looks up separately reported release timestamps through the GitHub releases API or the official release page. arXiv returns original abstracts and initial submission timestamps. Use publication or release dates for coverage. Update and retrieval timestamps are tracked separately. Items with unknown dates are excluded from time windows.

| Source | Coverage |
| --- | --- |
| [DuckDB](https://github.com/duckdb/duckdb/releases.atom) | SQL and data platforms |
| [dbt Core](https://github.com/dbt-labs/dbt/releases.atom) | Analytics engineering |
| [statsmodels](https://github.com/statsmodels/statsmodels/releases.atom) | Statistics and forecasting |
| [scikit-learn](https://github.com/scikit-learn/scikit-learn/releases.atom) | Machine learning and evaluation |
| [PyTorch](https://github.com/pytorch/pytorch/releases.atom) | Machine learning and MLOps |
| [Ollama](https://github.com/ollama/ollama/releases.atom) | Local LLMs and agents |
| [Transformers](https://github.com/huggingface/transformers/releases.atom) | LLMs, RAG, and agents |
| [MLflow](https://github.com/mlflow/mlflow/releases.atom) | MLOps and evaluation |
| [arXiv API](https://info.arxiv.org/help/api/user-manual.html) | Recent submissions in `cs.AI` and `cs.LG` |

Ranking boosts topic fit (up to 3 points), matching keywords (up to 4), freshness (up to 2), source quality (up to 1), and practical cues for your goals (up to 1). Excluded keywords filter items out. Canonical links and similar titles collapse repeats. Generation excludes substantially similar stories already covered in the available history. These rules prioritize reading order for this briefing.

Each retrieval checks at most nine sources, keeps at most 30 entries per source, fetches with five workers, and gives each HTTP request a time and size budget. Briefings use up to eight evidence excerpts in one bounded model request with no automatic retry. The model receives untrusted excerpts as data and has no tools. Radar validates the JSON response and maps citation IDs back to retrieved evidence. It discards unsupported IDs, inline links, malformed output and incomplete responses. These checks verify citation membership. They cannot establish that every claim follows from its source. Verify important claims and vendor-reported benchmarks against the primary source. Releases outside the catalog, undated items, and poorly described changes may be missed. Small models and unavailable services can yield errors or fewer items. Some environments need outbound access to `api.github.com`, `export.arxiv.org`, and the chosen provider host.

## Development

```shell
uv sync --locked
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync pytest
```

Tests use fixture feeds and mocked model requests. The source, provider, ranking, validation, persistence, Streamlit, and CLI modules are in [radar](radar/). The project is released under the [MIT License](LICENSE).
