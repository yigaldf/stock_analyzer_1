# syntax=docker/dockerfile:1.7
FROM python:3.12-slim-bookworm

# Pinned uv binary from Astral's official image.
# Bump this version in lockstep with local `uv --version` to keep parity.
COPY --from=ghcr.io/astral-sh/uv:0.7.13 /uv /uvx /bin/

ENV DEBIAN_FRONTEND=noninteractive \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/playwright

WORKDIR /app

# --- Layer 1: Python dependencies (cached when pyproject/uv.lock unchanged) ---
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# --- Layer 2: Chromium + its apt system libraries (runs as root) ---
# Install to the shared PLAYWRIGHT_BROWSERS_PATH and make world-readable so
# the non-root `app` user can launch Chromium at runtime.
RUN uv run playwright install --with-deps chromium && \
    chmod -R a+rX /opt/playwright

# --- Layer 3: Non-root user (Hugging Face Spaces runs containers as UID 1000) ---
RUN useradd -m -u 1000 app && chown -R app:app /app
USER app

# --- Layer 4: App source (most-changing layer last for caching) ---
COPY --chown=app:app streamlit_app.py README.md ./
COPY --chown=app:app app/ ./app/

# Install the local project itself now that source is present.
RUN uv sync --frozen --no-dev

EXPOSE 7860

CMD ["uv", "run", "streamlit", "run", "streamlit_app.py", \
     "--server.port=7860", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--server.enableCORS=false", \
     "--server.enableXsrfProtection=false", \
     "--browser.gatherUsageStats=false"]
