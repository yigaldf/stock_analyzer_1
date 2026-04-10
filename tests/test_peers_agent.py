from unittest.mock import patch

from app.agents.peers_agent import suggest_peers


@patch("app.agents.peers_agent._run_agent")
def test_suggest_peers_parses_json(mock_run):
    mock_run.return_value = '{"tickers": ["NKE", "ADDYY", "ONON", "UA"]}'
    result = suggest_peers("LULU", "Lululemon", "Consumer Cyclical")
    assert result == ["NKE", "ADDYY", "ONON", "UA"]


@patch("app.agents.peers_agent._run_agent")
def test_suggest_peers_handles_wrapped_json(mock_run):
    # LLMs sometimes wrap JSON in prose
    mock_run.return_value = (
        "Here are the competitors:\n"
        '```json\n{"tickers": ["NKE", "ADDYY"]}\n```\n'
        "Hope this helps!"
    )
    result = suggest_peers("LULU", "Lululemon", "Consumer Cyclical")
    assert "NKE" in result
    assert "ADDYY" in result


@patch("app.agents.peers_agent._run_agent")
def test_suggest_peers_returns_empty_on_garbage(mock_run):
    mock_run.return_value = "I don't know, try Google"
    result = suggest_peers("LULU", "Lululemon", "Consumer Cyclical")
    assert result == []


@patch("app.agents.peers_agent._run_agent")
def test_suggest_peers_returns_empty_on_exception(mock_run):
    mock_run.side_effect = RuntimeError("no api key")
    result = suggest_peers("LULU", "Lululemon", "Consumer Cyclical")
    assert result == []


@patch("app.agents.peers_agent._run_agent")
def test_suggest_peers_caps_at_10(mock_run):
    mock_run.return_value = (
        '{"tickers": ["A","B","C","D","E","F","G","H","I","J","K","L"]}'
    )
    result = suggest_peers("LULU", "Lululemon", "Consumer Cyclical")
    assert len(result) == 10
