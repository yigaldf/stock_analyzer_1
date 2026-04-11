import pytest

from app.services.yahoo_scraper import _to_float, _to_magnitude, _to_percent


def test_to_float_simple():
    assert _to_float("12.37") == 12.37


def test_to_float_with_thousands_separator():
    assert _to_float("1,234.56") == 1234.56


def test_to_float_negative():
    assert _to_float("-7.5") == -7.5


def test_to_float_dash_returns_none():
    assert _to_float("--") is None


def test_to_float_empty_returns_none():
    assert _to_float("") is None


def test_to_float_none_returns_none():
    assert _to_float(None) is None


def test_to_float_whitespace_returns_none():
    assert _to_float("   ") is None


def test_to_percent_positive():
    assert _to_percent("14.22%") == 0.1422


def test_to_percent_negative():
    assert _to_percent("-21.60%") == pytest.approx(-0.216)


def test_to_percent_with_thousands():
    assert _to_percent("1,234.50%") == 12.345


def test_to_percent_dash_returns_none():
    assert _to_percent("--") is None


def test_to_percent_empty_returns_none():
    assert _to_percent("") is None


def test_to_percent_none_returns_none():
    assert _to_percent(None) is None


def test_to_percent_no_percent_sign_still_parses():
    # Yahoo occasionally renders raw numbers in a column we expected as %.
    # Treat the bare number as already-percent-form: "14.22" -> 0.1422.
    assert _to_percent("14.22") == 0.1422


def test_to_magnitude_billions():
    assert _to_magnitude("1.81B") == 1_810_000_000.0


def test_to_magnitude_millions():
    assert _to_magnitude("824.08M") == 824_080_000.0


def test_to_magnitude_thousands():
    assert _to_magnitude("350K") == 350_000.0


def test_to_magnitude_plain_number():
    assert _to_magnitude("123") == 123.0


def test_to_magnitude_with_separator():
    assert _to_magnitude("1,234M") == 1_234_000_000.0


def test_to_magnitude_negative():
    assert _to_magnitude("-2.5B") == -2_500_000_000.0


def test_to_magnitude_dash_returns_none():
    assert _to_magnitude("--") is None


def test_to_magnitude_none_returns_none():
    assert _to_magnitude(None) is None


def test_to_magnitude_garbage_returns_none():
    assert _to_magnitude("foo") is None
