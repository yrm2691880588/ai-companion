"""定价与成本：按官方「百万 token」口径计价，支持高峰/空闲时段与缓存命中率。

DeepSeek 官方（2026-10）计价规则：
- 单价以「元 / 百万 tokens」给出；
- 周一至周五 09:00-12:00、14:00-18:00（北京时间，不含法定节假日）为高峰，
  其余（含夜间与周末）为空闲，空闲价为高峰价的一半；
- 输入分「缓存命中」与「缓存未命中」两档，相差可达 50 倍——缓存命中率直接决定成本。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import ROUND_FLOOR, Decimal
from enum import StrEnum
from zoneinfo import ZoneInfo

SHANGHAI = ZoneInfo("Asia/Shanghai")
PER_MILLION = Decimal(1_000_000)


class TimeBand(StrEnum):
    PEAK = "peak"
    OFFPEAK = "offpeak"


@dataclass(frozen=True)
class Price:
    """人民币元 / 百万 token。"""

    input_hit: Decimal
    input_miss: Decimal
    output: Decimal


@dataclass(frozen=True)
class BandedPrice:
    peak: Price
    offpeak: Price

    def for_band(self, band: TimeBand) -> Price:
        return self.peak if band is TimeBand.PEAK else self.offpeak


def parse_banded_price(raw: dict[str, object]) -> BandedPrice:
    """从配置/YAML 解析价格，例如：

    {"hit": {"peak": 0.04, "offpeak": 0.02},
     "miss": {"peak": 2.0, "offpeak": 1.0},
     "out": {"peak": 8.0, "offpeak": 4.0}}
    """

    def band_value(section: str, band: str) -> Decimal:
        block = raw[section]
        assert isinstance(block, dict)
        return Decimal(str(block[band]))

    return BandedPrice(
        peak=Price(
            input_hit=band_value("hit", "peak"),
            input_miss=band_value("miss", "peak"),
            output=band_value("out", "peak"),
        ),
        offpeak=Price(
            input_hit=band_value("hit", "offpeak"),
            input_miss=band_value("miss", "offpeak"),
            output=band_value("out", "offpeak"),
        ),
    )


def time_band(
    now: datetime,
    *,
    holidays: frozenset[date] = frozenset(),
) -> TimeBand:
    """按北京时间判断当前处于高峰还是空闲时段。"""
    local = now.astimezone(SHANGHAI)
    if local.weekday() >= 5 or local.date() in holidays:
        return TimeBand.OFFPEAK
    current = local.time()
    if time(9, 0) <= current < time(12, 0) or time(14, 0) <= current < time(18, 0):
        return TimeBand.PEAK
    return TimeBand.OFFPEAK


def clamp_ratio(value: float | Decimal) -> Decimal:
    ratio = Decimal(str(value))
    if ratio < 0:
        return Decimal(0)
    if ratio > 1:
        return Decimal(1)
    return ratio


def effective_input_price(price: Price, hit_ratio: float | Decimal) -> Decimal:
    """每百万 token 的有效输入价（命中与未命中按比例混合）。"""
    ratio = clamp_ratio(hit_ratio)
    return price.input_hit * ratio + price.input_miss * (Decimal(1) - ratio)


def turn_cost(
    price: Price,
    *,
    input_tokens: int,
    output_tokens: int,
    hit_ratio: float | Decimal,
) -> Decimal:
    """单轮成本（元）。"""
    if input_tokens < 0 or output_tokens < 0:
        raise ValueError("token 数不能为负")
    mixed = effective_input_price(price, hit_ratio) * Decimal(input_tokens)
    out = price.output * Decimal(output_tokens)
    return (mixed + out) / PER_MILLION


def budget_tokens(
    price: Price,
    *,
    cap_cny: float | Decimal,
    hit_ratio: float | Decimal,
    expected_output_tokens: int,
    context_window: int,
    max_context_ratio: float | Decimal = 0.8,
) -> int:
    """由「单轮成本上限」倒推可容纳的输入 token，再与窗口安全水位取小。

    B = min(0.8 × W, (C − c_out) / p_eff)
    """
    cap = Decimal(str(cap_cny))
    if cap <= 0:
        raise ValueError("成本上限必须为正")
    out_cost = price.output * Decimal(expected_output_tokens) / PER_MILLION
    remaining = cap - out_cost
    if remaining <= 0:
        return 0
    eff_per_million = effective_input_price(price, hit_ratio)
    if eff_per_million <= 0:
        # 本地模型等零成本场景：只受窗口限制
        return int(Decimal(context_window) * Decimal(str(max_context_ratio)))
    by_cost = remaining * PER_MILLION / eff_per_million
    by_window = Decimal(context_window) * Decimal(str(max_context_ratio))
    return int(min(by_cost, by_window).to_integral_value(rounding=ROUND_FLOOR))


def should_compress(estimated_input_tokens: int, budget: int, *, threshold: float = 0.85) -> bool:
    if budget <= 0:
        return True
    return estimated_input_tokens >= budget * threshold
