from itertools import groupby
from statistics import mean

from app.models.schemas import CategoryScore, StockMetrics, StockRanking

CATEGORIES = [
    "valuation",
    "growth",
    "profitability",
    "capital_efficiency",
    "health",
    "cash_quality",
    "valuation_trend",
    "dividend",
]

DEFAULT_WEIGHTS: dict[str, float] = {
    "valuation":          0.18,
    "growth":             0.18,
    "profitability":      0.14,
    "capital_efficiency": 0.12,
    "health":             0.12,
    "cash_quality":       0.12,
    "valuation_trend":    0.08,
    "dividend":           0.06,
}

# Sub-metrics for each composite category: list of (StockMetrics field, direction).
# Direction: "lower" means lower raw value = better score.
# `cash_quality` and `valuation_trend` are derived metrics handled separately.
_CATEGORY_SUBMETRICS: dict[str, list[tuple[str, str]]] = {
    "valuation":          [("forward_pe", "lower"), ("peg_ratio", "lower"), ("ev_to_ebitda", "lower")],
    "growth":             [("revenue_growth_yoy", "higher"), ("earnings_growth_yoy", "higher")],
    "profitability":      [("operating_margin", "higher"), ("profit_margin", "higher")],
    "capital_efficiency": [("roe", "higher"), ("roa", "higher")],
    "health":             [("debt_to_equity", "lower"), ("current_ratio", "higher")],
    "dividend":           [("forward_dividend_yield", "higher")],
}


def _format_value(field: str, raw: float | None) -> str:
    """Format a single sub-metric raw value for display."""
    if raw is None:
        return "—"
    # Ratios and multiples — plain decimal
    if field in (
        "forward_pe", "trailing_pe", "ev_to_ebitda", "ev_to_revenue",
        "price_to_sales", "price_to_book", "peg_ratio", "current_ratio", "beta",
    ):
        return f"{raw:.2f}"
    # Percentage-form decimals (stored as 0.1422 meaning 14.22%)
    if field in (
        "debt_to_equity", "operating_margin", "profit_margin", "roe", "roa",
        "revenue_growth_yoy", "earnings_growth_yoy",
        "forward_dividend_yield", "payout_ratio",
    ):
        return f"{raw * 100:.1f}%"
    return f"{raw}"


def score_category_single(
    stocks: list[StockMetrics],
    field: str,
    direction: str,
) -> dict[str, CategoryScore]:
    """Score each stock 1-5 by relative ranking on a single field.

    Returns a dict ticker -> CategoryScore.
    - Missing values receive neutral score 3 and display "—".
    - Equal raw values share the same score (tied ranks).
    - `direction == "higher"` means higher raw value is better.
    """
    values: list[tuple[str, float]] = []
    missing: list[str] = []
    for stock in stocks:
        raw = getattr(stock, field)
        if raw is None:
            missing.append(stock.ticker)
        else:
            values.append((stock.ticker, float(raw)))

    result: dict[str, CategoryScore] = {}

    if not values:
        for stock in stocks:
            result[stock.ticker] = CategoryScore(
                category=field, score=3, raw_value=None, display="—",
            )
        return result

    if len(values) == 1:
        only_ticker, only_raw = values[0]
        result[only_ticker] = CategoryScore(
            category=field, score=5, raw_value=only_raw,
            display=_format_value(field, only_raw),
        )
    else:
        reverse = direction == "higher"
        sorted_values = sorted(values, key=lambda x: x[1], reverse=reverse)
        groups: list[tuple[float, list[str]]] = []
        for raw_val, group_iter in groupby(sorted_values, key=lambda x: x[1]):
            groups.append((raw_val, [t for t, _ in group_iter]))
        num_groups = len(groups)
        for group_idx, (raw_val, tickers) in enumerate(groups):
            score = 5 if num_groups == 1 else round(5 - (4 * group_idx / (num_groups - 1)))
            for ticker in tickers:
                result[ticker] = CategoryScore(
                    category=field, score=score, raw_value=raw_val,
                    display=_format_value(field, raw_val),
                )

    for ticker in missing:
        result[ticker] = CategoryScore(
            category=field, score=3, raw_value=None, display="—",
        )

    return result


def _score_composite(
    category: str,
    stocks: list[StockMetrics],
    sub_metrics: list[tuple[str, str]],
) -> dict[str, CategoryScore]:
    """Composite category score = rounded mean of per-sub-metric scores.

    For each stock we compute each sub-metric's score via
    score_category_single, then average the resulting integer scores and
    round. Display string lists the sub-metric formatted raw values.
    """
    per_sub: list[dict[str, CategoryScore]] = [
        score_category_single(stocks, field, direction)
        for field, direction in sub_metrics
    ]

    result: dict[str, CategoryScore] = {}
    for stock in stocks:
        sub_scores = [d[stock.ticker].score for d in per_sub]
        composite = round(mean(sub_scores))
        parts: list[str] = []
        for (field, _), per_sub_dict in zip(sub_metrics, per_sub):
            cs = per_sub_dict[stock.ticker]
            parts.append(_format_value(field, cs.raw_value))
        result[stock.ticker] = CategoryScore(
            category=category,
            score=composite,
            raw_value=None,
            display=", ".join(parts),
        )
    return result


def _score_cash_quality(
    stocks: list[StockMetrics],
) -> dict[str, CategoryScore]:
    """Cash Quality = FCF yield (levered_free_cash_flow / market_cap).

    Higher yield = better. Peers missing either input (or with zero
    market cap) receive neutral 3.
    """
    yields: list[tuple[str, float | None]] = []
    for s in stocks:
        if (
            s.levered_free_cash_flow is None
            or s.market_cap is None
            or s.market_cap == 0
        ):
            yields.append((s.ticker, None))
        else:
            yields.append((s.ticker, s.levered_free_cash_flow / s.market_cap))

    valid = [(t, y) for t, y in yields if y is not None]
    missing = [t for t, y in yields if y is None]
    result: dict[str, CategoryScore] = {}

    if not valid:
        for s in stocks:
            result[s.ticker] = CategoryScore(
                category="cash_quality", score=3, raw_value=None, display="—",
            )
        return result

    sorted_y = sorted(valid, key=lambda x: x[1], reverse=True)
    groups: list[tuple[float, list[str]]] = []
    for raw, gi in groupby(sorted_y, key=lambda x: x[1]):
        groups.append((raw, [t for t, _ in gi]))
    num_groups = len(groups)
    for idx, (raw, tickers) in enumerate(groups):
        score = 5 if num_groups == 1 else round(5 - (4 * idx / (num_groups - 1)))
        for t in tickers:
            result[t] = CategoryScore(
                category="cash_quality", score=score, raw_value=raw,
                display=f"FCF yield {raw * 100:.1f}%",
            )
    for t in missing:
        result[t] = CategoryScore(
            category="cash_quality", score=3, raw_value=None, display="—",
        )
    return result


def _score_valuation_trend(
    stocks: list[StockMetrics],
) -> dict[str, CategoryScore]:
    """Valuation Trend = current forward_pe / mean historical forward_pe.

    The "Current" entry in valuation_history is excluded from the mean so
    the ratio compares now against own recent history. Lower ratio =
    cheaper-than-own-history = better.
    """
    ratios: list[tuple[str, float | None]] = []
    for s in stocks:
        if not s.valuation_history or s.forward_pe is None:
            ratios.append((s.ticker, None))
            continue
        historical = [
            q.forward_pe for q in s.valuation_history
            if q.period != "Current" and q.forward_pe is not None
        ]
        if not historical:
            ratios.append((s.ticker, None))
            continue
        hist_mean = mean(historical)
        if hist_mean == 0:
            ratios.append((s.ticker, None))
            continue
        ratios.append((s.ticker, s.forward_pe / hist_mean))

    valid = [(t, r) for t, r in ratios if r is not None]
    missing = [t for t, r in ratios if r is None]
    result: dict[str, CategoryScore] = {}

    if not valid:
        for s in stocks:
            result[s.ticker] = CategoryScore(
                category="valuation_trend", score=3, raw_value=None, display="—",
            )
        return result

    sorted_r = sorted(valid, key=lambda x: x[1])
    groups: list[tuple[float, list[str]]] = []
    for raw, gi in groupby(sorted_r, key=lambda x: x[1]):
        groups.append((raw, [t for t, _ in gi]))
    num_groups = len(groups)
    for idx, (raw, tickers) in enumerate(groups):
        score = 5 if num_groups == 1 else round(5 - (4 * idx / (num_groups - 1)))
        for t in tickers:
            result[t] = CategoryScore(
                category="valuation_trend", score=score, raw_value=raw,
                display=f"Fwd P/E {raw:.2f}x own avg",
            )
    for t in missing:
        result[t] = CategoryScore(
            category="valuation_trend", score=3, raw_value=None, display="—",
        )
    return result


def score_category(
    category: str,
    stocks: list[StockMetrics],
) -> dict[str, CategoryScore]:
    """Public dispatch: one CategoryScore per ticker for the named category."""
    if category == "cash_quality":
        return _score_cash_quality(stocks)
    if category == "valuation_trend":
        return _score_valuation_trend(stocks)
    if category not in _CATEGORY_SUBMETRICS:
        raise ValueError(f"Unknown category: {category}")
    return _score_composite(category, stocks, _CATEGORY_SUBMETRICS[category])


def compute_weighted_scores(
    stocks: list[StockMetrics],
    weights: dict[str, float],
) -> list[StockRanking]:
    """Score every category, apply weights, sort, assign ranks.

    Weights are normalized internally so they always sum to 1.0.
    Categories absent from `weights` get an implicit 0.0.
    """
    total = sum(weights.get(cat, 0.0) for cat in CATEGORIES)
    if total <= 0:
        raise ValueError("At least one category weight must be positive.")
    norm = {cat: weights.get(cat, 0.0) / total for cat in CATEGORIES}

    per_category: dict[str, dict[str, CategoryScore]] = {}
    for cat in CATEGORIES:
        per_category[cat] = score_category(cat, stocks)

    rankings: list[StockRanking] = []
    for stock in stocks:
        category_scores = [per_category[cat][stock.ticker] for cat in CATEGORIES]
        weighted = sum(cs.score * norm[cs.category] for cs in category_scores)
        rankings.append(
            StockRanking(
                ticker=stock.ticker,
                category_scores=category_scores,
                weighted_score=round(weighted, 4),
                rank=0,
            )
        )

    rankings.sort(key=lambda r: (-r.weighted_score, r.ticker))
    for idx, r in enumerate(rankings, start=1):
        r.rank = idx

    return rankings
