FROM python:3.13-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen

FROM python:3.13-slim AS runtime

# System binaries:
#   ffmpeg  — yt-dlp postprocessor (FFmpegExtractAudio/Metadata) + audio re-encode
#   nodejs  — yt-dlp JS challenge solver (js_runtimes: {node: {}} in transcriber.py)
#   uv      — package manager, pinned binary for in-container `uv run` / `uv add`
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        ffmpeg \
        nodejs \
        tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY src/ ./src/

ENV PATH="/app/.venv/bin:$PATH"

CMD ["python", "-m", "src.bot"]
