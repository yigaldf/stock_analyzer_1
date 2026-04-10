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
        model=OpenAIChat(id="gpt-4o-mini"),
        instructions=(
            "You are a financial research assistant. Given a stock, "
            "return up to 10 publicly traded US competitors as JSON in the "
            'form {"tickers": ["TICKER1", "TICKER2", ...]}. '
            "Only return real tickers on major US exchanges. "
            "Return ONLY the JSON object, no prose."
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
        f"Find up to 10 publicly traded US competitors for {ticker} "
        f"({name}, sector: {sector}). "
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
