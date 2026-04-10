# Stock Analyzer

## Tech Stack
- Python 3.12+
- FastAPI (REST API)
- Agno AI (AI agent framework)
- uv (package manager)

## Commands
- Install: `uv sync`
- Run app: `uv run streamlit run streamlit_app.py`
- Run tests: `uv run pytest`
- Lint: `uv run ruff check .`
- Format: `uv run ruff format .`

## Project Structure
- `streamlit_app.py` — Streamlit entry point
- `app/ui/` — Streamlit UI (screens, state, nav)
- `app/ui/screens/` — One file per wizard step
- `app/services/` — Pure-Python business logic (stock data, scoring)
- `app/agents/` — Agno agents (peer discovery, recommendation)
- `app/models/` — Pydantic schemas
- `tests/` — pytest unit tests (no live API/LLM calls)

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
