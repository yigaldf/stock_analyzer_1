# Stock Analyzer

## Tech Stack
- Python 3.12+
- FastAPI (REST API)
- Agno AI (AI agent framework)
- uv (package manager)

## Commands
- Install: `uv sync`
- Run dev server: `uv run uvicorn app.main:app --reload`
- Run tests: `uv run pytest`
- Lint: `uv run ruff check .`
- Format: `uv run ruff format .`

## Project Structure
- `app/` — FastAPI application
- `app/main.py` — Entry point
- `app/agents/` — Agno AI agents
- `app/routers/` — API route handlers
- `app/models/` — Pydantic models
- `app/services/` — Business logic

## Code Conventions
- Use type hints everywhere
- Use async/await for API endpoints
- Pydantic models for request/response validation
- Keep agents in separate modules under `app/agents/`
- Use `.env` for API keys (never commit secrets)

## Key Dependencies
- `agno` — AI agent framework
- `fastapi` — Web framework
- `uvicorn` — ASGI server

## Notes
- Stock data API keys go in `.env`
- Agno agents should use tool-calling patterns
