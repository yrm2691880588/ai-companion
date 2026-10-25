from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app.infra.llm.pricing import (
    BandedPrice,
    TimeBand,
    budget_tokens,
    effective_input_price,
    parse_banded_price,
    should_compress,
    time_band,
    turn_cost,
)

SHANGHAI = ZoneInfo("Asia/Shanghai")

DEEPSEEK_FLASH: BandedPrice = parse_banded_price(
    {
        "hit": {"peak": 0.04, "offpeak": 0.02},
        "miss": {"peak": 2.0, "offpeak": 1.0},
        "out": {"peak": 8.0, "offpeak": 4.0},
    }
)


def at(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=SHANGHAI)


def test_weekday_morning_is_peak() -> None:
    assert time_band(at(2026, 10, 26, 10, 30)) is TimeBand.PEAK


def test_lunch_gap_is_offpeak() -> None:
    assert time_band(at(2026, 10, 26, 13, 0)) is TimeBand.OFFPEAK


def test_evening_is_offpeak() -> None:
    # 产品的主要使用时段在晚上，属空闲价
    assert time_band(at(2026, 10, 26, 21, 0)) is TimeBand.OFFPEAK


def test_weekend_is_offpeak() -> None:
    assert time_band(at(2026, 10, 31, 10, 30)) is TimeBand.OFFPEAK


def test_holiday_is_offpeak() -> None:
    holiday = at(2026, 10, 1, 10).date()
    assert time_band(at(2026, 10, 1, 10), holidays=frozenset({holiday})) is TimeBand.OFFPEAK


def test_effective_price_mixes_hit_and_miss() -> None:
    price = DEEPSEEK_FLASH.peak
    assert effective_input_price(price, 1.0) == price.input_hit
    assert effective_input_price(price, 0.0) == price.input_miss
    assert effective_input_price(price, Decimal("0.85")) == pytest.approx(
        price.input_hit * Decimal("0.85") + price.input_miss * Decimal("0.15")
    )


def test_economy_tier_cost_about_one_cent() -> None:
    # 计划 §5.3：16K 输入 + 500 输出，命中率 0.85，高峰价 ≈ ¥0.009
    cost = turn_cost(
        DEEPSEEK_FLASH.peak,
        input_tokens=16_000,
        output_tokens=500,
        hit_ratio=0.85,
    )
    assert Decimal("0.008") < cost < Decimal("0.011")


def test_offpeak_is_half_price() -> None:
    kwargs = {"input_tokens": 16_000, "output_tokens": 500, "hit_ratio": 0.85}
    peak = turn_cost(DEEPSEEK_FLASH.peak, **kwargs)
    offpeak = turn_cost(DEEPSEEK_FLASH.offpeak, **kwargs)
    assert peak == pytest.approx(offpeak * 2)


def test_budget_is_cost_bound_before_window() -> None:
    # 1M 窗口不是默认塞满：成本上限先卡住
    budget = budget_tokens(
        DEEPSEEK_FLASH.peak,
        cap_cny=0.02,
        hit_ratio=0.85,
        expected_output_tokens=500,
        context_window=1_000_000,
    )
    assert 44_000 <= budget <= 52_000


def test_budget_respects_window_for_cheap_model() -> None:
    budget = budget_tokens(
        DEEPSEEK_FLASH.offpeak,
        cap_cny=1.0,
        hit_ratio=0.85,
        expected_output_tokens=500,
        context_window=131_072,
        max_context_ratio=0.8,
    )
    assert budget == int(131_072 * 0.8)


def test_budget_local_model_only_window_bound() -> None:
    zero = parse_banded_price(
        {
            "hit": {"peak": 0.0, "offpeak": 0.0},
            "miss": {"peak": 0.0, "offpeak": 0.0},
            "out": {"peak": 0.0, "offpeak": 0.0},
        }
    )
    budget = budget_tokens(
        zero.peak,
        cap_cny=0.02,
        hit_ratio=0.0,
        expected_output_tokens=500,
        context_window=32_768,
    )
    assert budget == int(32_768 * 0.8)


def test_budget_rejects_bad_cap() -> None:
    with pytest.raises(ValueError):
        budget_tokens(
            DEEPSEEK_FLASH.peak,
            cap_cny=0,
            hit_ratio=0.85,
            expected_output_tokens=500,
            context_window=1_000_000,
        )


def test_compress_threshold() -> None:
    assert should_compress(850, 1000) is True
    assert should_compress(800, 1000) is False
    assert should_compress(1, 0) is True
