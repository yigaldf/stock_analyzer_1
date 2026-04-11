from unittest.mock import patch

from app.agents.recommendation_agent import generate_recommendation
from app.models.schemas import CategoryScore, StockRanking


def _ranking(ticker: str, weighted: float, rank: int) -> StockRanking:
    return StockRanking(
        ticker=ticker,
        category_scores=[
            CategoryScore(
                category="valuation", score=5, raw_value=13.0, display="13x fwd P/E"
            ),
            CategoryScore(
                category="growth", score=5, raw_value=0.30, display="30% rev growth"
            ),
            CategoryScore(
                category="profitability",
                score=4,
                raw_value=0.15,
                display="15% op margin",
            ),
            CategoryScore(category="roic", score=5, raw_value=0.30, display="30% ROE"),
            CategoryScore(
                category="health", score=5, raw_value=0.20, display="0.20 D/E"
            ),
            CategoryScore(
                category="dividend", score=1, raw_value=None, display="— no data"
            ),
        ],
        weighted_score=weighted,
        rank=rank,
    )


@patch("app.agents.recommendation_agent._run_agent")
def test_generate_recommendation_returns_agent_text(mock_run):
    mock_run.return_value = "Top pick is ONON due to its strong growth of 30% YoY."
    rankings = [_ranking("ONON", 4.0, 1), _ranking("LULU", 3.8, 2)]
    weights = {
        "valuation": 0.2,
        "growth": 0.2,
        "profitability": 0.2,
        "roic": 0.15,
        "health": 0.15,
        "dividend": 0.10,
    }
    result = generate_recommendation(rankings, weights)
    assert "ONON" in result
    mock_run.assert_called_once()


@patch("app.agents.recommendation_agent._run_agent")
def test_generate_recommendation_fallback_on_exception(mock_run):
    mock_run.side_effect = RuntimeError("no api key")
    rankings = [_ranking("ONON", 4.0, 1), _ranking("LULU", 3.8, 2)]
    weights = {
        "valuation": 0.2,
        "growth": 0.2,
        "profitability": 0.2,
        "roic": 0.15,
        "health": 0.15,
        "dividend": 0.10,
    }
    result = generate_recommendation(rankings, weights)
    assert "ONON" in result
    assert "4.00" in result or "4.0" in result


def test_generate_recommendation_empty_rankings_returns_message():
    result = generate_recommendation([], {})
    assert result == "No stocks to rank."
