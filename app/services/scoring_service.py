from app.models.schemas import CategoryScore, StockMetrics, StockRanking

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
        # Stocks with equal raw values receive the same score (average of their positions).
        # Group by raw value first
        from itertools import groupby
        groups: list[tuple[float, list[str]]] = []
        for raw_val, group_iter in groupby(sorted_values, key=lambda x: x[1]):
            groups.append((raw_val, [t for t, _ in group_iter]))

        num_groups = len(groups)
        for group_idx, (raw_val, tickers) in enumerate(groups):
            if num_groups == 1:
                score = 5
            else:
                score_float = 5 - (4 * group_idx / (num_groups - 1))
                score = round(score_float)
            for ticker in tickers:
                result[ticker] = CategoryScore(
                    category=category,
                    score=score,
                    raw_value=raw_val,
                    display=_format_display(category, raw_val),
                )

    for ticker in missing:
        result[ticker] = CategoryScore(
            category=category,
            score=3,
            raw_value=None,
            display="— no data",
        )

    return result


def compute_weighted_scores(
    stocks: list[StockMetrics],
    weights: dict[str, float],
) -> list[StockRanking]:
    """Full pipeline: score all categories → apply weights → sort → assign ranks.

    Weights are normalized internally so they always sum to 1.0.
    """
    # Normalize weights
    total = sum(weights.get(cat, 0.0) for cat in CATEGORIES)
    if total <= 0:
        raise ValueError("At least one category weight must be positive.")
    norm = {cat: weights.get(cat, 0.0) / total for cat in CATEGORIES}

    # Score each category
    per_category: dict[str, dict[str, CategoryScore]] = {}
    for cat in CATEGORIES:
        per_category[cat] = score_category(cat, stocks)

    # Assemble per-stock rankings
    rankings: list[StockRanking] = []
    for stock in stocks:
        category_scores = [per_category[cat][stock.ticker] for cat in CATEGORIES]
        weighted = sum(
            cs.score * norm[cs.category] for cs in category_scores
        )
        rankings.append(
            StockRanking(
                ticker=stock.ticker,
                category_scores=category_scores,
                weighted_score=round(weighted, 4),
                rank=0,  # filled in below
            )
        )

    # Sort: weighted_score desc, then ticker asc (alphabetical tie-break)
    rankings.sort(key=lambda r: (-r.weighted_score, r.ticker))
    for idx, r in enumerate(rankings, start=1):
        r.rank = idx

    return rankings
