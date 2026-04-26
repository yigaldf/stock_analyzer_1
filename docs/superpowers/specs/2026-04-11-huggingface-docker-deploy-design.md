# Hugging Face Spaces (Docker) Deployment — Design

**Date:** 2026-04-11
**Status:** Approved
**Owner:** yigaldf

## Goal

Deploy `stock_analyzer_1` as a **private Hugging Face Space** using the Docker SDK,
deployed by manual `git push` to a second git remote. The Playwright fallback in the
Yahoo scraper must continue to work in the container.

## Non-goals

- CI/CD auto-sync from GitHub to the Space (user chose manual push).
- Auth, rate limiting, or per-user API keys (private Space makes this unnecessary).
- Fixing pre-existing `yfinance` rate-limit behavior (not caused by deploy).
- Switching the scraper from `sync_playwright` to `async_playwright`.
- Removing `OPENAI_API_KEY` from local `.env` (stays as-is for local dev).

## Architecture

Single Docker container serving Streamlit on port **7860** (Hugging Face Spaces'
required port). Hugging Face's reverse proxy terminates TLS and routes
`<user>-stock-analyzer.hf.space` → container port 7860. No database, no persistent
storage — the app is stateless per session.

```
user → https://<user>-stock-analyzer.hf.space (HF proxy, TLS)
           ↓
      container :7860 (Streamlit, --server.address=0.0.0.0)
           ↓
      app/services/yahoo_scraper.py → httpx, fallback to Playwright Chromium (in-container)
      app/agents/* → OpenAI API (outbound, via OPENAI_API_KEY env)
```

## Files added to the repo

### 1. `Dockerfile` (repo root)

Single-stage build. Target size ~1.2 GB (dominated by Chromium + system libs).

Build steps, in order:

1. `FROM python:3.12-slim-bookworm` — matches `.python-version` and is the most
   transparent base for this use case. Microsoft's `playwright/python` image was
   rejected because current tags pin to Python 3.10; Astral's `uv` image was rejected
   as a marginal win over `python:3.12-slim`.
2. Install `uv` via the official standalone installer, pinned to a specific version
   for build reproducibility.
3. `WORKDIR /app`.
4. Copy `pyproject.toml` and `uv.lock` **first**, run `uv sync --frozen --no-dev` to
   maximize Docker layer caching on subsequent rebuilds that change only app code.
5. Run `uv run playwright install --with-deps chromium` as root. This installs both
   the Chromium binary (~170 MB) and the apt system libraries Chromium depends on.
   Must happen before the non-root user switch, because `--with-deps` calls apt.
6. Copy the rest of the app source (`app/`, `streamlit_app.py`, `README.md`, etc.).
   Excluded files are controlled by `.dockerignore` (see §2).
7. Create non-root user `app` with UID 1000 (Hugging Face Spaces runs containers as
   UID 1000 by convention; writing as root can trip HF's filesystem permissions).
   `chown -R app:app /app`, then `USER app`.
8. `EXPOSE 7860`.
9. `CMD ["uv", "run", "streamlit", "run", "streamlit_app.py",
       "--server.port=7860",
       "--server.address=0.0.0.0",
       "--server.headless=true"]`

### 2. `.dockerignore` (repo root)

Critical — without this, the build context includes the ~500 MB `.venv` and the
image bloats correspondingly. Exclude at minimum:

```
.venv/
.git/
.env
.env.*
.claude/
.cursor/
.playwright-mcp/
.pytest_cache/
.ruff_cache/
__pycache__/
**/__pycache__/
*.pyc
tests/
docs/
a1
.DS_Store
```

Note: `tests/` and `docs/` are excluded because they are not needed at runtime and
their absence shrinks the image. `.env` is excluded as defense-in-depth even though
it's already gitignored — a stray local `.env` must never land in a published image.

### 3. `README.md` frontmatter

Hugging Face Spaces requires a YAML frontmatter block at the top of `README.md` to
configure the Space. Prepended to the existing README content:

```yaml
---
title: Stock Analyzer
emoji: 📈
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
---
```

GitHub's markdown renderer hides YAML frontmatter, so this does not affect how the
README displays on GitHub. The existing README body is preserved verbatim below
the frontmatter.

## Secrets

- `OPENAI_API_KEY` is set via the Space's **Settings → Variables and secrets →
  New secret** (NOT as a plain Variable — secrets are encrypted and not visible
  after creation).
- At runtime, HF injects the secret as an environment variable inside the
  container. `streamlit_app.py` calls `load_dotenv()`, which is a no-op in the
  container (no `.env` file present) and falls through to `os.environ`, which
  already has `OPENAI_API_KEY` set. **No code change required.**
- Local development continues to read from `.env`.

## Deploy workflow (manual)

**One-time setup** (performed by the user, not automatable from this repo):

1. Create a **private** Space at huggingface.co/new-space, SDK = Docker,
   name = `stock-analyzer`.
2. Generate a write-scoped HF access token at huggingface.co/settings/tokens.
3. Locally:
   ```
   git remote add hf https://<user>:<hf-token>@huggingface.co/spaces/<user>/stock-analyzer
   ```
   (or use a git credential helper to avoid putting the token in the URL).
4. In the Space's settings, add `OPENAI_API_KEY` as a **Secret**.

**Per deploy**:

```
git push hf main
```

Hugging Face rebuilds the image and restarts the container automatically. Build
logs are visible in the Space's "Logs" tab. First build takes ~3–5 minutes
(Chromium + apt deps); subsequent builds that don't touch `pyproject.toml` are
faster thanks to layer caching.

## Risks and mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| Streamlit reruns launch a fresh Chromium on each scrape | Medium | Existing code already gates scraping behind explicit user actions — verified in `app/services/yahoo_scraper.py`. Watch-item, not a blocker. Revisit if Step 3 feels slow in the deployed Space. |
| HF free-tier Spaces pause after ~48h idle | Low | Cold start is ~30s, acceptable for private use. |
| Playwright `--with-deps` apt failure during build | Low | Build fails loudly; no silent regression. Fix by pinning the Playwright version in `pyproject.toml` if it recurs. |
| Image size exceeds HF free-tier budget (~10 GB) | Very low | Target is ~1.2 GB. Ample headroom. |
| HF token leakage via git remote URL | Medium | Prefer git credential helper over `https://<user>:<token>@...` in the remote URL. Documented in the setup steps. |
| `OPENAI_API_KEY` accidentally committed via `.env` | Low | `.env` is already gitignored and also listed in `.dockerignore`. |

## Success criteria

1. `git push hf main` triggers a successful HF build (visible in Logs tab).
2. The private Space URL loads the Streamlit wizard (Step 1 visible).
3. Step 2 peer discovery completes end-to-end, proving the OpenAI secret is wired.
4. Step 3 metrics scraping succeeds for at least one ticker, and the source badge
   shows either `httpx` or `playwright` — proving the Playwright fallback survived
   containerization.
5. Local `uv run streamlit run streamlit_app.py` still works (no regression).
