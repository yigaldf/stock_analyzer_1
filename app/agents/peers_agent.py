from __future__ import annotations

import json
import re


def _run_agent(prompt: str) -> str:
    """Run the Agno agent and return its raw text response.

    Isolated so tests can patch it without initializing Agno.
    """
    # Lazy import so tests don't need Agno configured
    from agno.agent import Agent
    from agno.models.openai import OpenAIChat

    agent = Agent(
        model=OpenAIChat(id="gpt-4o"),
        instructions=(
            "You are an equity research analyst. Given a stock, return its "
            "direct product-market competitors — companies that sell similar "
            "products to similar customers in the same sub-industry. Prefer "
            "close peers over broad sector matches. For apparel/athleisure, "
            "include direct apparel brands (Nike, Adidas, Under Armour, On "
            "Holding, Deckers, VF Corp, PVH, Gap, etc.) rather than unrelated "
            "cyclicals. "
            "Return exactly the JSON object "
            '{"tickers": ["TICKER1", "TICKER2", ...]} with up to 10 tickers, '
            "each a real symbol on NYSE/NASDAQ/AMEX (US listings or US-listed "
            "ADRs for foreign peers). Return ONLY the JSON, no prose, no "
            "markdown fences."
        ),
    )
    response = agent.run(prompt)
    return str(response.content) if hasattr(response, "content") else str(response)


_JSON_BLOCK_RE = re.compile(r"\{[^{}]*\"tickers\"[^{}]*\}", re.DOTALL)


def _extract_tickers(raw: str) -> list[str]:
    # Try direct parse first
    try:
        parsed = json.loads(raw)
        tickers = parsed.get("tickers", [])
        if isinstance(tickers, list):
            return [str(t).upper() for t in tickers]
    except (json.JSONDecodeError, AttributeError):
        pass

    # Fall back to regex-extract the first {...} block containing "tickers"
    match = _JSON_BLOCK_RE.search(raw)
    if match:
        try:
            parsed = json.loads(match.group(0))
            tickers = parsed.get("tickers", [])
            if isinstance(tickers, list):
                return [str(t).upper() for t in tickers]
        except json.JSONDecodeError:
            return []

    return []


def suggest_peers(ticker: str, name: str, sector: str) -> list[str]:
    """Ask the AI agent for up to 10 competitor tickers. Empty list on any failure."""
    prompt = (
        f"Stock: {ticker} — {name} (sector: {sector}).\n"
        "Task: list up to 10 direct product-market competitors. "
        "Think about who this company's customers would shop as alternatives "
        "and who shows up alongside it in investor peer-comparison tables. "
        "Include close rivals even if their market cap is smaller. "
        'Respond ONLY with JSON: {"tickers": ["TICKER1", "TICKER2", ...]}'
    )
    try:
        raw = _run_agent(prompt)
    except Exception:
        return []

    tickers = _extract_tickers(raw)
    # Remove the source ticker if the agent included it
    tickers = [t for t in tickers if t != ticker.upper()]
    return tickers[:10]
