from __future__ import annotations

from app.models.schemas import StockRanking


def _run_agent(prompt: str) -> str:
    """Run the Agno agent and return its raw text response.

    Isolated so tests can patch it without initializing Agno.
    """
    from agno.agent import Agent
    from agno.models.openai import OpenAIChat

    agent = Agent(
        model=OpenAIChat(id="gpt-4o-mini"),
        instructions=(
            "You are a concise investment analyst. Given a peer ranking and the "
            "user's category weights, write a 2-3 sentence recommendation "
            "explaining why the top stock stands out. Reference specific metric "
            "values from the category scores. The categories are: "
            "Valuation (composite of forward P/E, PEG, EV/EBITDA), "
            "Growth (revenue and earnings YoY), "
            "Profitability (operating and profit margin), "
            "Capital Efficiency (ROE and ROA), "
            "Financial Health (debt/equity and current ratio), "
            "Cash Quality (free cash flow yield = levered FCF / market cap), "
            "Valuation Trend (current forward P/E vs the stock's own 5-quarter "
            "historical average — a reading below 1.0 means cheaper than own "
            "history), and Dividend (forward yield). "
            "Do NOT give financial advice disclaimers."
        ),
    )
    response = agent.run(prompt)
    return str(response.content) if hasattr(response, "content") else str(response)


def _fallback_summary(rankings: list[StockRanking]) -> str:
    top = rankings[0]
    return (
        f"Top pick: {top.ticker} with weighted score {top.weighted_score:.2f}. "
        f"(AI recommendation unavailable.)"
    )


def _format_prompt(rankings: list[StockRanking], weights: dict[str, float]) -> str:
    top = rankings[0]
    runners = rankings[1:3]
    lines = [
        "User weights: " + ", ".join(
            f"{k}={v*100:.0f}%" for k, v in weights.items()
        ),
        "",
        f"Top pick: {top.ticker} (weighted score {top.weighted_score:.2f})",
    ]
    for cs in top.category_scores:
        lines.append(f"  - {cs.category}: {cs.score}/5 ({cs.display})")
    if runners:
        lines.append("")
        lines.append("Runners up:")
        for r in runners:
            lines.append(f"  - {r.ticker}: {r.weighted_score:.2f}")
    lines.append("")
    lines.append(
        "Write a 2-3 sentence recommendation explaining why the top pick stands out "
        "given these weights. Reference specific metric values."
    )
    return "\n".join(lines)


def generate_recommendation(
    rankings: list[StockRanking],
    weights: dict[str, float],
) -> str:
    """Generate an AI recommendation for the top pick. Falls back to a deterministic
    summary on any error or if the top pick is empty."""
    if not rankings:
        return "No stocks to rank."

    prompt = _format_prompt(rankings, weights)
    try:
        return _run_agent(prompt).strip()
    except Exception:
        return _fallback_summary(rankings)
