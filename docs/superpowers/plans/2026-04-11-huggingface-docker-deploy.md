# Hugging Face Spaces (Docker) Deploy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy `stock_analyzer_1` as a private Hugging Face Space using the Docker SDK, deployed by manual `git push` to a second git remote, with the Playwright scraper fallback working inside the container.

**Architecture:** Single-stage Dockerfile on `python:3.12-slim-bookworm`, with `uv` pinned to 0.7.13 (matching local), Chromium installed to a shared path via `playwright install --with-deps`, Streamlit serving on port 7860 as non-root user `app` (UID 1000). HF Space configured via YAML frontmatter in the existing `README.md`. Secrets (`OPENAI_API_KEY`) set in the Space's secret store. First deploy is a manual `git push hf web_scraping_metrics:main`.

**Tech Stack:** Docker, `uv`, Streamlit, Playwright (sync_api + Chromium), Hugging Face Spaces Docker SDK.

**Spec:** [docs/superpowers/specs/2026-04-11-huggingface-docker-deploy-design.md](../specs/2026-04-11-huggingface-docker-deploy-design.md)

---

## File Structure

**Files to CREATE:**
- `Dockerfile` (repo root) — build recipe
- `.dockerignore` (repo root) — exclude local state, secrets, caches from build context

**Files to MODIFY:**
- `README.md` (repo root) — prepend Hugging Face Space YAML frontmatter

**Files NOT changed:**
- `streamlit_app.py` — no code change; `load_dotenv()` is a no-op in the container and falls through to `os.environ`
- `pyproject.toml` / `uv.lock` — no dependency change
- `app/**` — no code change
- `.gitignore` — already excludes `.env` and local tool configs

---

## Task 1: Add `.dockerignore`

**Files:**
- Create: `.dockerignore`

Without this file, `docker build` copies the entire repo (including the ~500 MB `.venv/`) into the build context. The build would still technically succeed, but the image would be enormous and secrets in `.env` would land in the image.

- [ ] **Step 1: Create `.dockerignore` with the exact content below**

```
# Source control
.git/
.gitignore
.gitattributes

# Environment / secrets — defense in depth even though .env is gitignored
.env
.env.*

# Virtual environments
.venv/

# Local tool state and caches
.claude/
.cursor/
.playwright-mcp/
.pytest_cache/
.ruff_cache/
.superpowers/

# Python bytecode
__pycache__/
**/__pycache__/
*.pyc
*.pyo

# OS junk
.DS_Store
**/.DS_Store

# Tests, docs, scratch — not needed at runtime
tests/
docs/
a1

# IDE
.idea/
.vscode/
```

- [ ] **Step 2: Verify `.env` is excluded**

Run:
```bash
grep -E '^\.env(\..*)?$' .dockerignore
```
Expected output (two lines):
```
.env
.env.*
```

- [ ] **Step 3: Commit**

```bash
git add .dockerignore
git commit -m "chore: add .dockerignore for Docker build context"
```

---

## Task 2: Add the `Dockerfile`

**Files:**
- Create: `Dockerfile`

The Dockerfile uses `python:3.12-slim-bookworm`, copies the `uv` binary from Astral's image pinned to 0.7.13 (matching the local version), installs Chromium + its system libs to a shared path, then switches to non-root user `app` (UID 1000, Hugging Face convention) before copying source and launching Streamlit on port 7860.

- [ ] **Step 1: Create `Dockerfile` with the exact content below**

```dockerfile
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
```

- [ ] **Step 2: Verify file is syntactically sensible**

Run:
```bash
head -1 Dockerfile && tail -8 Dockerfile
```
Expected: first line is `# syntax=docker/dockerfile:1.7`, last block is the `CMD` array ending with `--browser.gatherUsageStats=false"]`.

- [ ] **Step 3: Commit**

```bash
git add Dockerfile
git commit -m "feat(deploy): add Dockerfile for Hugging Face Spaces"
```

---

## Task 3: Prepend Hugging Face frontmatter to `README.md`

**Files:**
- Modify: `README.md` (prepend 10 lines at the top; existing content preserved verbatim)

Hugging Face Spaces reads a YAML frontmatter block at the top of `README.md` to configure the Space (title, Docker SDK, app port). GitHub's renderer hides YAML frontmatter, so prepending has no visual effect on the GitHub view. The current first line is `# 📈 Stock Analyzer` — there is no existing frontmatter to merge with.

- [ ] **Step 1: Confirm README currently has no frontmatter**

Run:
```bash
head -3 README.md
```
Expected: first line is `# 📈 Stock Analyzer`, not `---`. (If it's `---`, stop and inspect — another tool added frontmatter since the plan was written; merge the HF keys into the existing block rather than prepending a second one.)

- [ ] **Step 2: Prepend the frontmatter block**

Use the Edit tool to change:

Old:
```markdown
# 📈 Stock Analyzer
```

New:
```markdown
---
title: Stock Analyzer
emoji: 📈
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
---

# 📈 Stock Analyzer
```

- [ ] **Step 3: Verify frontmatter is valid YAML and the body is intact**

Run:
```bash
head -12 README.md
```
Expected: frontmatter block followed by a blank line and `# 📈 Stock Analyzer`.

Run:
```bash
python3 -c "import sys; s=open('README.md').read(); assert s.startswith('---\n'), 'missing opening'; end=s.index('\n---\n',4); import yaml; print(yaml.safe_load(s[4:end]))" 2>&1 || echo "yaml not installed, skipping lint"
```
Expected: a dict with keys `title`, `emoji`, `colorFrom`, `colorTo`, `sdk`, `app_port`, `pinned`. If PyYAML isn't available, skip — the HF build will catch any syntax error.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: add Hugging Face Space frontmatter to README"
```

---

## Task 4: Local Docker build smoke test

**Files:** none (verification only, no commit)

This task verifies the Dockerfile builds before we depend on HF's remote builder. If Docker isn't installed locally, skip this task and Task 5 — the HF build in Task 7 will be the first real build, and we'll just have to read the HF build logs carefully.

- [ ] **Step 1: Check if Docker is available**

Run:
```bash
docker --version
```
Expected: a version string like `Docker version 24.x`. If the command fails ("command not found" or "Cannot connect to the Docker daemon"), skip the rest of this task and Task 5, and note it in Task 7.

- [ ] **Step 2: Build the image**

Run (from repo root):
```bash
docker build -t stock-analyzer:local .
```
Expected: build completes with `Successfully tagged stock-analyzer:local`. First build takes roughly 3–5 minutes (downloading base image, uv sync, Chromium + apt deps).

If the build fails at the `playwright install --with-deps chromium` step with an apt error, the most likely cause is a transient Debian mirror issue — re-run the command. If it persists, capture the full error and stop.

- [ ] **Step 3: Confirm image size is within the expected range**

Run:
```bash
docker images stock-analyzer:local --format '{{.Size}}'
```
Expected: roughly `1.1GB` – `1.4GB`. If it's larger than 2GB, the most likely cause is `.dockerignore` missing an entry — run `docker build` again with `--progress=plain` and inspect the `=> [internal] load build context` step size.

---

## Task 5: Local Docker run smoke test

**Files:** none (verification only, no commit)

Boot the container locally and hit Streamlit's health endpoint to confirm the app starts. Skip if Task 4 was skipped.

- [ ] **Step 1: Load `OPENAI_API_KEY` from local `.env`**

Run:
```bash
export $(grep -E '^OPENAI_API_KEY=' .env | xargs)
echo "OPENAI_API_KEY=${OPENAI_API_KEY:0:10}..."
```
Expected: prints `OPENAI_API_KEY=sk-...` with the first 10 characters of your real key. If it prints `OPENAI_API_KEY=...` (empty value), the regex didn't match — check `.env` has a line starting with `OPENAI_API_KEY=`.

- [ ] **Step 2: Start the container in the background**

Run:
```bash
docker run --rm -d \
  -p 7860:7860 \
  -e OPENAI_API_KEY \
  --name stock-analyzer-test \
  stock-analyzer:local
```
Expected: prints a 64-char container ID. If the port is already in use, stop whatever is bound to 7860 and retry.

- [ ] **Step 3: Wait for Streamlit to boot and hit the health endpoint**

Run:
```bash
sleep 6 && curl -fsS http://localhost:7860/_stcore/health
```
Expected output: `ok` (a literal three-character string).

If you get a connection-refused error, Streamlit is still booting — wait another 5 seconds and retry. If you get a 404, check that `--server.port=7860` is in the Dockerfile CMD (Streamlit's health path depends on being on the configured port).

- [ ] **Step 4: Stop the container**

Run:
```bash
docker stop stock-analyzer-test
```
Expected: prints `stock-analyzer-test`.

---

## Task 6: Hugging Face Space one-time setup (manual user actions)

**Files:** none in this repo — all changes happen on huggingface.co and in the local git config.

This task cannot be automated by the agent. Each step must be performed by the user. The agent's job is to verify the external state after each step by running a local git command.

- [ ] **Step 1: Create the private Space**

Manual action by user:
1. Go to https://huggingface.co/new-space
2. Owner: your HF username
3. Space name: `stock-analyzer`
4. License: leave blank or choose
5. SDK: **Docker**, "Blank" template
6. Space hardware: **CPU basic (free)**
7. Visibility: **Private**
8. Click "Create Space"

Expected: you land on `https://huggingface.co/spaces/<your-username>/stock-analyzer` with an empty Space.

- [ ] **Step 2: Generate a write-scoped HF access token**

Manual action by user:
1. Go to https://huggingface.co/settings/tokens
2. Click "New token"
3. Name: `stock-analyzer-deploy`
4. Type: **Write**
5. Click "Generate" and copy the token (it will not be shown again)

Store the token somewhere safe for Step 3 — do not paste it into any file in this repo.

- [ ] **Step 3: Add the `hf` git remote using a credential helper**

Run (replacing `<your-username>` with your HF username; do NOT inline the token in the URL):

```bash
git remote add hf https://huggingface.co/spaces/<your-username>/stock-analyzer
```

Then cache the credential once by doing a throwaway fetch — git will prompt for the token:
```bash
git -c credential.helper='cache --timeout=3600' fetch hf 2>&1 | head -20
```
When prompted: username = your HF username, password = the write token from Step 2.

Expected: `fetch hf` either prints a new remote tracking the Space's `main` branch, or errors with something benign like `couldn't find remote ref` (the Space has no commits yet) — both outcomes confirm the remote and credentials are usable.

- [ ] **Step 4: Verify the remote is configured**

Run:
```bash
git remote -v | grep huggingface
```
Expected output (two lines):
```
hf	https://huggingface.co/spaces/<your-username>/stock-analyzer (fetch)
hf	https://huggingface.co/spaces/<your-username>/stock-analyzer (push)
```

- [ ] **Step 5: Add `OPENAI_API_KEY` as a Space secret**

Manual action by user:
1. Go to `https://huggingface.co/spaces/<your-username>/stock-analyzer/settings`
2. Scroll to "Variables and secrets"
3. Click "New secret" (NOT "New variable" — variables are visible to anyone with read access)
4. Name: `OPENAI_API_KEY`
5. Value: paste your real OpenAI key
6. Click "Save"

Expected: the secret appears in the list with a masked value. No code change is needed — HF injects it as an environment variable at container start, and `streamlit_app.py`'s `load_dotenv()` will no-op and fall through to `os.environ`.

---

## Task 7: First deploy push

**Files:** none (git operation only, no commit)

The current branch is `web_scraping_metrics`. Hugging Face Spaces always serve the Space's `main` branch, so we push the local branch *to* the remote's `main`:

```
git push hf web_scraping_metrics:main
```

If you would rather deploy from `main` proper, merge `web_scraping_metrics` into local `main` first and then `git push hf main:main`. Either is fine — this plan uses the direct push for speed.

- [ ] **Step 1: Confirm the local branch and its state**

Run:
```bash
git status --short && git log --oneline -3
```
Expected: working tree clean, HEAD is on `web_scraping_metrics`, and the three most recent commits include `docs: add Hugging Face Space frontmatter` (Task 3), `feat(deploy): add Dockerfile` (Task 2), and `chore: add .dockerignore` (Task 1) in some order.

- [ ] **Step 2: Push to the Space's main branch**

Run:
```bash
git push hf web_scraping_metrics:main
```
Expected output: normal `git push` output ending with `* [new branch]      web_scraping_metrics -> main`. If you're prompted for credentials, the cache from Task 6 Step 3 may have expired — re-enter your HF username and write token.

- [ ] **Step 3: Watch the HF build logs**

Manual action by user:
1. Go to `https://huggingface.co/spaces/<your-username>/stock-analyzer`
2. Click the "Logs" tab (or "Building" banner)
3. Watch the Docker build output

Expected: build progresses through the same layers you saw locally in Task 4 — base image pull, `uv sync`, `playwright install --with-deps chromium`, final app source copy. First build takes roughly 4–6 minutes on HF's builders. Successful build ends with the Space banner switching from "Building" to "Running".

If the build fails, open the failing layer, copy the error, and stop — do not proceed to Task 8.

---

## Task 8: Post-deploy verification

**Files:** none (verification only, no commit)

Walk the app's 4-step wizard in the browser to confirm all five success criteria from the spec are met.

- [ ] **Step 1: Load the Space URL**

Manual action by user:
1. Open `https://<your-username>-stock-analyzer.hf.space` (note: hyphen-separated, not path-separated — this is the rendered app URL, distinct from the `huggingface.co/spaces/...` management URL)
2. Because the Space is private, you must be signed in to huggingface.co in the same browser session

Expected: the Streamlit wizard loads and Step 1 ("Select stock") is visible with the title "📈 Stock Analyzer".

- [ ] **Step 2: Complete Step 1 of the wizard**

In the app: enter a real ticker symbol (e.g. `AAPL`) and click through to Step 2.

Expected: Step 2 ("Peers") loads without errors.

- [ ] **Step 3: Trigger peer discovery to prove `OPENAI_API_KEY` is wired**

In the app: click whichever button triggers Agno peer discovery on Step 2 (e.g. "Suggest peers").

Expected: after a few seconds, a list of suggested peer tickers appears. If you instead see an OpenAI auth error, the secret is not set correctly — return to Task 6 Step 5.

- [ ] **Step 4: Run Step 3 metrics scraping and check the source badge**

In the app: pick at least one ticker and click through to Step 3 ("Metrics").

Expected: metrics load for the ticker and the per-ticker source badge shows either `httpx` or `playwright` (both are valid — the tiered fetcher pivot in the memory deliberately allows either). If the badge shows `playwright`, that proves Chromium is usable inside the container, which is the whole point of the Dockerfile work. If the badge shows `httpx` for every ticker, try a ticker known to trip Yahoo's GDPR flow (international tickers often do) to exercise the fallback.

- [ ] **Step 5: Verify local dev still works (no regression)**

Run:
```bash
uv run streamlit run streamlit_app.py
```
Expected: Streamlit starts locally on `http://localhost:8501` exactly as before the deploy work. Ctrl-C to stop after confirming the wizard loads.

- [ ] **Step 6: Record success**

No commit. If all five success criteria from the spec are met, the deploy is done. If any failed, open a follow-up note in the spec's "Risks and mitigations" table.

---

## Self-Review Notes

**Spec coverage:** Every section of the spec maps to a task — `.dockerignore` → Task 1; Dockerfile → Task 2; README frontmatter → Task 3; Secrets setup → Task 6 Step 5; Deploy workflow → Tasks 6 and 7; Success criteria → Task 8 Steps 1–5 (one-to-one with the spec's numbered criteria).

**Placeholder scan:** No `TBD`, `TODO`, or vague "add error handling" steps. The `<your-username>` placeholders in Tasks 6–8 are legitimate user-specific values the agent cannot know in advance.

**Type consistency:** No types or function signatures to cross-check — this is an infra plan.

**Potential follow-ups (explicitly out of scope for this plan):** pinning the Playwright Python package version in `pyproject.toml`, switching the scraper to `async_playwright`, adding a GitHub Action to auto-sync on push to `main`, moving to a paid HF tier to avoid cold starts.
