FROM python:3.12-slim
WORKDIR /app
ENV UV_PROJECT_ENVIRONMENT=/opt/radar-venv \
    PATH="/opt/radar-venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY radar/ radar/
RUN --mount=type=secret,id=radar_ca \
    if [ -f /run/secrets/radar_ca ]; then \
        export PIP_CERT=/run/secrets/radar_ca SSL_CERT_FILE=/run/secrets/radar_ca; \
    fi \
    && python -m pip install --no-cache-dir uv==0.13.9 \
    && uv sync --locked --no-dev --no-editable \
    && groupadd --system radar && useradd --system --gid radar --create-home radar \
    && mkdir -p /data && chown radar:radar /data
COPY .streamlit/ .streamlit/
RUN chmod -R a+rX /app
USER radar
ENV RADAR_DB=/data/history.sqlite3
EXPOSE 8501
CMD ["streamlit", "run", "radar/app.py", "--server.address", "0.0.0.0", "--server.headless", "true"]
