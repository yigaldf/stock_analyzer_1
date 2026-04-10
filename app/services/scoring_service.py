from app.models.schemas import CategoryScore, StockMetrics

CATEGORIES = ["valuation", "growth", "profitability", "roic", "health", "dividend"]

DEFAULT_WEIGHTS: dict[str, float] = {
    "valuation": 0.20,
    "growth": 0.20,
    "profitability": 0.20,
    "roic": 0.15,
    "health": 0.15,
    "dividend": 0.10,
}

# Primary metric used to score each category, with direction
# direction = "lower" means lower raw value = better score
_CATEGORY_CONFIG: dict[str, dict] = {
    "valuation": {"field": "forward_pe", "direction": "lower", "label": "fwd P/E"},
    "growth": {"field": "revenue_growth", "direction": "higher", "label": "rev growth"},
    "profitability": {"field": "operating_margin", "direction": "higher", "label": "op margin"},
    "roic": {"field": "roe", "direction": "higher", "label": "ROE"},
    "health": {"field": "debt_to_equity", "direction": "lower", "label": "D/E"},
    "dividend": {"field": "dividend_yield", "direction": "higher", "label": "div yield"},
}


def _format_display(category: str, raw: float | None) -> str:
    if raw is None:
        return "— no data"
    label = _CATEGORY_CONFIG[category]["label"]
    if category in ("valuation",):
        return f"{raw:.1f}x {label}"
    if category in ("growth", "profitability", "dividend"):
        return f"{raw * 100:.1f}% {label}"
    if category == "roic":
        return f"{raw * 100:.1f}% {label}"
    if category == "health":
        return f"{raw:.2f} {label}"
    return f"{raw} {label}"


def score_category(
    category: str,
    stocks_metrics: list[StockMetrics],
) -> dict[str, CategoryScore]:
    """Score each stock 1-5 for one category via relative ranking within the peer group."""
    config = _CATEGORY_CONFIG[category]
    field = config["field"]
    direction = config["direction"]

    values: list[tuple[str, float]] = []
    missing: list[str] = []
    for stock in stocks_metrics:
        raw = getattr(stock, field)
        if raw is None:
            missing.append(stock.ticker)
        else:
            values.append((stock.ticker, float(raw)))

    result: dict[str, CategoryScore] = {}

    if len(values) == 0:
        # Everyone is missing — everyone is neutral
        for stock in stocks_metrics:
            result[stock.ticker] = CategoryScore(
                category=category,
                score=3,
                raw_value=None,
                display="— no data",
            )
        return result

    if len(values) == 1:
        only_ticker, only_raw = values[0]
        result[only_ticker] = CategoryScore(
            category=category,
            score=5,
            raw_value=only_raw,
            display=_format_display(category, only_raw),
        )
    else:
        reverse = direction == "higher"
        sorted_values = sorted(values, key=lambda x: x[1], reverse=reverse)
        n = len(sorted_values)
        # Best gets 5, worst gets 1, linear interpolation (integer scores 1-5)
        for idx, (ticker, raw) in enumerate(sorted_values):
            if n == 1:
                score = 5
            else:
                # position 0 (best) → 5, position n-1 (worst) → 1
                score_float = 5 - (4 * idx / (n - 1))
                score = round(score_float)
            result[ticker] = CategoryScore(
                category=category,
                score=score,
                raw_value=raw,
                display=_format_display(category, raw),
            )

    for ticker in missing:
        result[ticker] = CategoryScore(
            category=category,
            score=3,
            raw_value=None,
            display="— no data",
        )

    return result
