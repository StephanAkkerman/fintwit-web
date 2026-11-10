"""Backtest of the advisor's trading rules on stored trader calls and daily prices.

The live strategy (``/advisor``) buys when a followed account turns bullish on
a stock whose technicals pass, and sells on three rules: a -35% loss with a
broken trend (rule 6), a trailing stop once a position is up 50% (rule 7) and
a weekly stage 4 (rule 8). This module replays those rules, and variations on
them, so they can be judged on what they would have earned rather than on how
they read.

Two studies come out of one run:

* **Portfolio replay.** Every bullish call stored in ``trader_calls`` becomes
  a candidate entry at the close of the next trading day. A simulated account
  takes the candidates its entry rules allow, sizes them, and exits them by its
  exit rules, day by day. Each variant changes one thing (who to follow, the
  entry filter, the exits, or the sizing) against the current rules.
* **Exit study.** Stored calls only go back to when the stream started, too
  short for exits that need a +50% run or a weekly downtrend to show up. So
  the exits are also tested on years of price history: a buy every month in
  every stock the accounts talk about, wherever the entry filter passes, held
  until each exit rule says sell.

What cannot be replayed is approximated and said so in ``assumptions``:
fundamentals and TradingView's rating have no point-in-time history, so
"technicals pass" is read as price above its 200-day average, and earnings
blackout days are not modelled.

Everything below ``run_backtest`` is pure: it takes signals and price series
and does no I/O, so it is tested on synthetic data.
"""

from __future__ import annotations

import asyncio
import bisect
import logging
import statistics
import time
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta, timezone
from typing import Iterable, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from .price_history_service import get_price_series
from .trend_stage import stage_at

logger = logging.getLogger(__name__)

BENCHMARK = "SPY"
#: Yahoo history behind every run: long enough for a 200-day average before
#: the first stored call, and for the multi-year exit study.
HISTORY_RANGE = "BACKTEST"
#: Asset kinds the advisor trades (it does not trade crypto from this feed).
TRADED_KINDS = ("EQUITY", "ETF")
#: Broad index trackers: a post about SPY or QQQ is market commentary, not a
#: stock pick, so these never become buys (SPY still serves as the benchmark).
INDEX_TRACKERS = frozenset(
    {"SPY", "QQQ", "IWM", "DIA", "VOO", "VTI", "IVV", "RSP", "QQQM", "SPX", "NDX"}
)
#: A call is graded for the rolling hit rate this many days after it is made,
#: the same 7-day horizon the live leaderboard uses.
GRADE_DAYS = 7
#: Repeat calls by one account on one symbol inside this window are one signal.
DEDUPE_DAYS = 10
#: Forward window (trading days) for the per-account signal quality table.
FORWARD_DAYS = 20
#: Exit-study entries: one every this many trading days per symbol.
EXIT_STUDY_STEP = 21
#: Sampled equity-curve points returned per variant.
CURVE_POINTS = 120


# --------------------------------------------------------------------------- #
# Rules
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class EntryRules:
    """Which calls the simulated account acts on.

    :param accounts: ``"followed"`` (the strategy's followed traders),
        ``"credible"`` (accounts whose rolling 7-day hit rate is at least
        ``min_hit_rate`` over ``min_graded`` graded calls *as of the call*, so
        no hindsight), or ``"all"``.
    :param min_accounts: Distinct qualifying accounts that must be bullish
        within ``consensus_days`` before a buy (rule 1's "3+ accounts").
    :param trend_filter: ``"none"``, ``"above_200d"`` (close above its
        200-day average, the stand-in for "technicals pass") or ``"stage2"``
        (last finished week in Weinstein stage 2).
    """

    accounts: str = "followed"
    min_accounts: int = 1
    consensus_days: int = 5
    min_hit_rate: float = 0.6
    min_graded: int = 20
    trend_filter: str = "above_200d"
    #: Only buy while SPY closes above this moving average (days); ``None``
    #: buys in any market.
    market_ma_days: Optional[int] = None


@dataclass(frozen=True)
class ExitRules:
    """When a position is sold. Every threshold is in percent; ``None`` turns
    the rule off. Rules are checked on daily closes, in the order listed."""

    #: Rule 8: sell everything when the week closes in stage 4.
    stage4: bool = True
    #: Rule 6: sell when this far below cost ...
    stop_loss_pct: Optional[float] = 35.0
    #: ... and (rule 6 only) the close is below its 200-day average.
    stop_needs_broken_trend: bool = True
    #: Rule 7: arm the trailing stop once this far above cost ...
    trail_arm_pct: Optional[float] = 50.0
    #: ... sell ``trail_fraction`` on a close this far below the high since ...
    trail_pct: float = 20.0
    trail_fraction: float = 1 / 3
    #: ... and the rest on a close below the 200-day average.
    trail_rest_below_200d: bool = True
    #: Plain trailing stop from the highest close since entry.
    trailing_stop_pct: Optional[float] = None
    #: Sell on a close below this moving average (days).
    below_ma_days: Optional[int] = None
    #: Sell everything this far above cost.
    take_profit_pct: Optional[float] = None
    #: Sell after this many trading days.
    max_hold_days: Optional[int] = None


@dataclass(frozen=True)
class Sizing:
    """How much each buy gets, as a share of current equity."""

    position_pct: float = 15.0
    cash_reserve_pct: float = 10.0
    #: Rule 4: at most this many new positions per calendar week.
    max_new_per_week: Optional[int] = 2
    start_capital: float = 10_000.0


@dataclass(frozen=True)
class Variant:
    key: str
    label: str
    group: str  # "baseline" | "accounts" | "entry" | "exit" | "sizing"
    entry: EntryRules = field(default_factory=EntryRules)
    exit: ExitRules = field(default_factory=ExitRules)
    sizing: Sizing = field(default_factory=Sizing)


_BASE = Variant("current", "Current rules (6, 7, 8)", "baseline")


def _vary(key: str, label: str, group: str, **changes) -> Variant:
    entry = replace(_BASE.entry, **changes.pop("entry", {}))
    exit_ = replace(_BASE.exit, **changes.pop("exit", {}))
    sizing = replace(_BASE.sizing, **changes.pop("sizing", {}))
    return Variant(key, label, group, entry, exit_, sizing)


#: Hold every position to the end of the data: the "do nothing" exit.
NO_EXITS = {
    "stage4": False,
    "stop_loss_pct": None,
    "trail_arm_pct": None,
}

#: One change at a time against the current rules, so each row reads as
#: "what this one rule is worth".
VARIANTS: list[Variant] = [
    _BASE,
    _vary(
        "credible",
        "Any account with a 60%+ rolling hit rate",
        "accounts",
        entry={"accounts": "credible"},
    ),
    _vary(
        "credible_x3",
        "3+ credible accounts within 5 days",
        "accounts",
        entry={"accounts": "credible", "min_accounts": 3},
    ),
    _vary("all", "Every account", "accounts", entry={"accounts": "all"}),
    _vary("no_filter", "No trend filter", "entry", entry={"trend_filter": "none"}),
    _vary("stage2", "Weekly stage 2 filter", "entry", entry={"trend_filter": "stage2"}),
    _vary(
        "market50",
        "Only buy while SPY is above its 50-day",
        "entry",
        entry={"market_ma_days": 50},
    ),
    _vary("hold", "No exits (hold)", "exit", exit=NO_EXITS),
    _vary("rule6_only", "Rule 6 only", "exit", exit={**NO_EXITS, "stop_loss_pct": 35}),
    _vary(
        "rule8_only", "Rule 8 only (stage 4)", "exit", exit={**NO_EXITS, "stage4": True}
    ),
    _vary(
        "stop10",
        "Plain -10% stop",
        "exit",
        exit={**NO_EXITS, "stop_loss_pct": 10, "stop_needs_broken_trend": False},
    ),
    _vary(
        "stop20",
        "Plain -20% stop",
        "exit",
        exit={**NO_EXITS, "stop_loss_pct": 20, "stop_needs_broken_trend": False},
    ),
    _vary(
        "trail15",
        "15% trailing stop",
        "exit",
        exit={**NO_EXITS, "trailing_stop_pct": 15},
    ),
    _vary(
        "trail25",
        "25% trailing stop",
        "exit",
        exit={**NO_EXITS, "trailing_stop_pct": 25},
    ),
    _vary(
        "below50d", "Close below 50-day", "exit", exit={**NO_EXITS, "below_ma_days": 50}
    ),
    _vary(
        "rules_plus_trail25",
        "Rules 6-8 plus 25% trailing stop",
        "exit",
        exit={"trailing_stop_pct": 25},
    ),
    _vary(
        "time20",
        "Sell after 20 trading days",
        "exit",
        exit={**NO_EXITS, "max_hold_days": 20},
    ),
    _vary(
        "size10_free",
        "10% positions, no weekly cap",
        "sizing",
        sizing={"position_pct": 10, "max_new_per_week": None},
    ),
    _vary(
        "size5_free",
        "5% positions, no weekly cap",
        "sizing",
        sizing={"position_pct": 5, "max_new_per_week": None},
    ),
    _vary("size20", "20% positions", "sizing", sizing={"position_pct": 20}),
]

ASSUMPTIONS = [
    "Buys fill at the close of the first trading day after the call; sells at "
    "the close of the day a rule triggers. No fees, slippage or FX.",
    "'Technicals pass' is read as a close above the 200-day average; "
    "fundamentals, TradingView's rating and earnings blackouts have no "
    "point-in-time history and are not modelled.",
    "Rule 6 needs a close below the 200-day average (TradingView's Sell is "
    "not replayable). Rule 8 is checked on the last close of each week.",
    "'Followed' uses today's followed list for the whole window; those "
    "accounts were picked on this same data, so their rows flatter them. "
    "'Credible' has no such hindsight: it uses each account's hit rate as of "
    "the call.",
    "Open positions are valued at the last close. Stored calls cover a short "
    "window, so most positions are still open and returns are mostly "
    "unrealised.",
    "The exit study buys monthly in every stock the accounts mention today, "
    "which leans toward stocks that did well enough to be talked about.",
]


# --------------------------------------------------------------------------- #
# Inputs
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Signal:
    """One stored call: an account bullish or bearish on a symbol."""

    symbol: str
    account: str
    day: date
    direction: str  # "bullish" | "bearish"
    price: Optional[float] = None
    sentiment: float = 0.0


class Series:
    """Daily closes of one symbol, with the averages and weekly stages the
    rules read, all indexed by trading day."""

    def __init__(self, symbol: str, points: Iterable[dict]):
        by_day: dict[date, float] = {}
        for point in points:
            close = point.get("close")
            if close is None:
                continue
            by_day[date.fromisoformat(str(point["t"])[:10])] = float(close)
        self.symbol = symbol
        self.days = sorted(by_day)
        self.closes = [by_day[d] for d in self.days]
        self._sums = [0.0]
        for close in self.closes:
            self._sums.append(self._sums[-1] + close)
        self._sma: dict[int, list[Optional[float]]] = {}
        self._weekly()

    def __len__(self) -> int:
        return len(self.days)

    def sma(self, window: int, index: int) -> Optional[float]:
        if index + 1 < window:
            return None
        return (self._sums[index + 1] - self._sums[index + 1 - window]) / window

    def _weekly(self) -> None:
        """Mark each week's last trading day and the stage it closed in, plus
        the stage of the last finished week before every day."""
        self.week_end = [False] * len(self.days)
        self.stage_on_week_end: list[Optional[int]] = [None] * len(self.days)
        self.last_week_stage: list[Optional[int]] = [None] * len(self.days)
        weekly: list[float] = []
        ends: list[int] = []
        for i, day in enumerate(self.days):
            nxt = self.days[i + 1] if i + 1 < len(self.days) else None
            if nxt is None or nxt.isocalendar()[:2] != day.isocalendar()[:2]:
                ends.append(i)
                weekly.append(self.closes[i])
        latest: Optional[int] = None
        end_iter = iter(enumerate(ends))
        upcoming = next(end_iter, None)
        for i in range(len(self.days)):
            self.last_week_stage[i] = latest
            if upcoming is not None and upcoming[1] == i:
                w = upcoming[0]
                stage = stage_at(weekly, w)
                self.week_end[i] = True
                self.stage_on_week_end[i] = stage
                latest = stage
                upcoming = next(end_iter, None)

    def index_after(self, day: date) -> Optional[int]:
        """First trading day strictly after ``day``."""
        i = bisect.bisect_right(self.days, day)
        return i if i < len(self.days) else None

    def index_on_or_before(self, day: date) -> Optional[int]:
        i = bisect.bisect_right(self.days, day) - 1
        return i if i >= 0 else None

    def close_on_or_before(self, day: date) -> Optional[float]:
        i = self.index_on_or_before(day)
        return None if i is None else self.closes[i]


# --------------------------------------------------------------------------- #
# One trade
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Fill:
    index: int
    day: date
    fraction: float  # share of the original position sold
    price: float
    reason: str


@dataclass
class TradePath:
    entry_index: int
    entry_day: date
    entry_price: float
    fills: list[Fill]
    last_price: float
    last_day: date

    @property
    def open_fraction(self) -> float:
        return max(0.0, 1.0 - sum(f.fraction for f in self.fills))

    def open_fraction_after(self, booked: int) -> float:
        """Share still held once the first ``booked`` fills have gone through."""
        return max(0.0, 1.0 - sum(f.fraction for f in self.fills[:booked]))

    @property
    def final_reason(self) -> str:
        """The rule that closed the position, or ``open``."""
        return "open" if self.open_fraction > 1e-9 else self.fills[-1].reason

    @property
    def return_pct(self) -> float:
        value = sum(f.fraction * f.price for f in self.fills)
        value += self.open_fraction * self.last_price
        return (value / self.entry_price - 1) * 100

    @property
    def days_held(self) -> int:
        end = self.fills[-1].day if self.open_fraction <= 1e-9 else self.last_day
        return (end - self.entry_day).days


def run_trade(
    series: Series,
    entry_index: int,
    rules: ExitRules,
    *,
    until: Optional[date] = None,
) -> TradePath:
    """Walk one long position forward from a buy at ``entry_index``'s close
    until the exit rules sell all of it, or the data (or ``until``) runs out.
    """
    cost = series.closes[entry_index]
    fills: list[Fill] = []
    remaining = 1.0
    highest = cost
    armed_peak: Optional[float] = None
    trimmed = False
    last = entry_index

    def sell(i: int, fraction: float, reason: str) -> None:
        nonlocal remaining
        fraction = min(fraction, remaining)
        if fraction <= 1e-9:
            return
        fills.append(Fill(i, series.days[i], fraction, series.closes[i], reason))
        remaining -= fraction

    for i in range(entry_index + 1, len(series)):
        if until is not None and series.days[i] > until:
            break
        last = i
        close = series.closes[i]
        highest = max(highest, close)
        sma200 = series.sma(200, i)
        below_200d = sma200 is not None and close < sma200

        if rules.stage4 and series.week_end[i] and series.stage_on_week_end[i] == 4:
            sell(i, remaining, "rule8_stage4")
        elif (
            rules.stop_loss_pct is not None
            and close <= cost * (1 - rules.stop_loss_pct / 100)
            and (not rules.stop_needs_broken_trend or sma200 is None or below_200d)
        ):
            sell(
                i,
                remaining,
                "rule6_stop" if rules.stop_needs_broken_trend else "stop_loss",
            )
        elif rules.take_profit_pct is not None and close >= cost * (
            1 + rules.take_profit_pct / 100
        ):
            sell(i, remaining, "take_profit")
        else:
            if rules.trail_arm_pct is not None:
                if armed_peak is None and close >= cost * (
                    1 + rules.trail_arm_pct / 100
                ):
                    armed_peak = close
                if armed_peak is not None:
                    armed_peak = max(armed_peak, close)
                    if not trimmed and close <= armed_peak * (
                        1 - rules.trail_pct / 100
                    ):
                        sell(i, rules.trail_fraction, "rule7_trim")
                        trimmed = True
                    if rules.trail_rest_below_200d and below_200d:
                        sell(i, remaining, "rule7_200d")
            if remaining > 1e-9 and rules.trailing_stop_pct is not None:
                if close <= highest * (1 - rules.trailing_stop_pct / 100):
                    sell(i, remaining, "trailing_stop")
            if remaining > 1e-9 and rules.below_ma_days is not None:
                ma = series.sma(rules.below_ma_days, i)
                if ma is not None and close < ma:
                    sell(i, remaining, f"below_{rules.below_ma_days}d")
            if remaining > 1e-9 and rules.max_hold_days is not None:
                if i - entry_index >= rules.max_hold_days:
                    sell(i, remaining, "time_exit")

        if remaining <= 1e-9:
            break

    return TradePath(
        entry_index=entry_index,
        entry_day=series.days[entry_index],
        entry_price=cost,
        fills=fills,
        last_price=series.closes[last],
        last_day=series.days[last],
    )


def passes_trend_filter(series: Series, index: int, kind: str) -> bool:
    if kind == "none":
        return True
    if kind == "above_200d":
        sma = series.sma(200, index)
        return sma is not None and series.closes[index] > sma
    if kind == "stage2":
        return series.last_week_stage[index] == 2
    raise ValueError(f"unknown trend filter {kind!r}")


# --------------------------------------------------------------------------- #
# Signals
# --------------------------------------------------------------------------- #


def dedupe(signals: Iterable[Signal], days: int = DEDUPE_DAYS) -> list[Signal]:
    """Keep the first of an account's repeat calls on one symbol within
    ``days`` (an account posting a ticker daily is one idea, not ten)."""
    kept: list[Signal] = []
    last: dict[tuple[str, str, str], date] = {}
    for sig in sorted(signals, key=lambda s: s.day):
        key = (sig.account, sig.symbol, sig.direction)
        prev = last.get(key)
        if prev is not None and (sig.day - prev).days < days:
            continue
        last[key] = sig.day
        kept.append(sig)
    return kept


class HitRates:
    """Each account's 7-day hit rate as it stood on any given day, built only
    from calls already graded by then."""

    def __init__(self, signals: Iterable[Signal], series: dict[str, Series]):
        graded: dict[str, list[tuple[date, bool]]] = {}
        for sig in signals:
            s = series.get(sig.symbol)
            if s is None or not sig.price:
                continue
            due = sig.day + timedelta(days=GRADE_DAYS)
            i = bisect.bisect_left(s.days, due)
            if i >= len(s):
                continue
            up = s.closes[i] > sig.price
            correct = up if sig.direction == "bullish" else not up
            graded.setdefault(sig.account, []).append((s.days[i], correct))
        self._days: dict[str, list[date]] = {}
        self._hits: dict[str, list[int]] = {}
        for account, rows in graded.items():
            rows.sort()
            self._days[account] = [d for d, _ in rows]
            cumulative = [0]
            for _, ok in rows:
                cumulative.append(cumulative[-1] + int(ok))
            self._hits[account] = cumulative

    def as_of(self, account: str, day: date) -> tuple[int, Optional[float]]:
        """(graded calls, hit rate) known before ``day``."""
        days = self._days.get(account)
        if not days:
            return 0, None
        n = bisect.bisect_left(days, day)
        if n == 0:
            return 0, None
        return n, self._hits[account][n] / n


def qualifying_accounts(
    rules: EntryRules,
    followed: set[str],
    hit_rates: HitRates,
):
    def ok(account: str, day: date) -> bool:
        if rules.accounts == "all":
            return True
        if rules.accounts == "followed":
            return account in followed
        n, rate = hit_rates.as_of(account, day)
        return n >= rules.min_graded and rate is not None and rate >= rules.min_hit_rate

    return ok


@dataclass
class Candidate:
    symbol: str
    index: int
    day: date
    accounts: tuple[str, ...]
    strength: float


def candidates_for(
    rules: EntryRules,
    bullish: list[Signal],
    series: dict[str, Series],
    followed: set[str],
    hit_rates: HitRates,
    start: date,
    end: date,
) -> dict[date, list[Candidate]]:
    """Buy candidates per trading day: each qualifying bullish call (or, with
    ``min_accounts > 1``, each time enough accounts agree) turns into a
    candidate on the next trading day."""
    ok = qualifying_accounts(rules, followed, hit_rates)
    by_day: dict[date, list[Candidate]] = {}
    recent: dict[str, list[Signal]] = {}
    for sig in sorted(bullish, key=lambda s: s.day):
        s = series.get(sig.symbol)
        if s is None or not ok(sig.account, sig.day):
            continue
        window = [
            r
            for r in recent.get(sig.symbol, [])
            if (sig.day - r.day).days <= rules.consensus_days
        ]
        window.append(sig)
        recent[sig.symbol] = window
        accounts = tuple(sorted({r.account for r in window}))
        if len(accounts) < rules.min_accounts:
            continue
        if rules.min_accounts > 1:
            # Fire once when the count is first reached, not on every call after.
            before = {r.account for r in window[:-1]}
            if len(before) >= rules.min_accounts:
                continue
        i = s.index_after(sig.day)
        if i is None or not (start <= s.days[i] <= end):
            continue
        cand = Candidate(sig.symbol, i, s.days[i], accounts, sig.sentiment)
        by_day.setdefault(s.days[i], []).append(cand)
    for cands in by_day.values():
        cands.sort(key=lambda c: (-len(c.accounts), -c.strength, c.symbol))
    return by_day


# --------------------------------------------------------------------------- #
# Portfolio replay
# --------------------------------------------------------------------------- #


@dataclass
class Position:
    symbol: str
    shares: float
    cost: float
    path: TradePath
    accounts: tuple[str, ...]
    filled: int = 0  # fills already booked


def _summarise_trades(trades: list[dict]) -> dict:
    returns = [t["return_pct"] for t in trades]
    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r <= 0]
    return {
        "trades": len(trades),
        "win_rate": round(len(wins) / len(returns), 4) if returns else None,
        "avg_return_pct": round(statistics.fmean(returns), 2) if returns else None,
        "median_return_pct": round(statistics.median(returns), 2) if returns else None,
        "avg_win_pct": round(statistics.fmean(wins), 2) if wins else None,
        "avg_loss_pct": round(statistics.fmean(losses), 2) if losses else None,
    }


def simulate_portfolio(
    variant: Variant,
    candidates: dict[date, list[Candidate]],
    series: dict[str, Series],
    calendar: list[date],
) -> dict:
    """Run one simulated account through ``calendar``."""
    sizing = variant.sizing
    cash = sizing.start_capital
    open_positions: dict[str, Position] = {}
    closed: list[Position] = []
    curve: list[tuple[date, float]] = []
    entries_per_week: dict[tuple[int, int], int] = {}
    skipped = {"held": 0, "trend": 0, "market": 0, "weekly_cap": 0, "cash": 0}
    market = series.get(BENCHMARK)
    invested_share: list[float] = []
    end = calendar[-1] if calendar else None

    def equity_on(day: date) -> float:
        value = cash
        for pos in open_positions.values():
            price = series[pos.symbol].close_on_or_before(day) or 0.0
            value += pos.shares * pos.path.open_fraction_after(pos.filled) * price
        return value

    for day in calendar:
        # Sells first: the rules act on today's close.
        for symbol in list(open_positions):
            pos = open_positions[symbol]
            fills = pos.path.fills
            while pos.filled < len(fills) and fills[pos.filled].day <= day:
                fill = fills[pos.filled]
                cash += pos.shares * fill.fraction * fill.price
                pos.filled += 1
            if pos.filled == len(fills) and pos.path.open_fraction <= 1e-9:
                closed.append(open_positions.pop(symbol))

        week = day.isocalendar()[:2]
        for cand in candidates.get(day, []):
            s = series[cand.symbol]
            if cand.symbol in open_positions:
                skipped["held"] += 1
                continue
            if not passes_trend_filter(s, cand.index, variant.entry.trend_filter):
                skipped["trend"] += 1
                continue
            if variant.entry.market_ma_days and market is not None:
                m = market.index_on_or_before(day)
                ma = None if m is None else market.sma(variant.entry.market_ma_days, m)
                if ma is None or market.closes[m] <= ma:
                    skipped["market"] += 1
                    continue
            if (
                sizing.max_new_per_week is not None
                and entries_per_week.get(week, 0) >= sizing.max_new_per_week
            ):
                skipped["weekly_cap"] += 1
                continue
            equity = equity_on(day)
            target = equity * sizing.position_pct / 100
            spare = cash - equity * sizing.cash_reserve_pct / 100
            amount = min(target, spare)
            if amount < target * 0.25:
                skipped["cash"] += 1
                continue
            price = s.closes[cand.index]
            path = run_trade(s, cand.index, variant.exit, until=end)
            open_positions[cand.symbol] = Position(
                cand.symbol, amount / price, amount, path, cand.accounts
            )
            cash -= amount
            entries_per_week[week] = entries_per_week.get(week, 0) + 1

        equity = equity_on(day)
        curve.append((day, equity))
        invested_share.append(1 - cash / equity if equity else 0.0)

    trades = []
    for pos in closed + list(open_positions.values()):
        trades.append(
            {
                "symbol": pos.symbol,
                "accounts": list(pos.accounts),
                "entry_day": pos.path.entry_day.isoformat(),
                "entry_price": round(pos.path.entry_price, 4),
                "exit_day": (
                    pos.path.fills[-1].day.isoformat()
                    if pos.path.final_reason != "open"
                    else None
                ),
                "exit_reason": pos.path.final_reason,
                "rules_hit": [f.reason for f in pos.path.fills],
                "return_pct": round(pos.path.return_pct, 2),
                "days_held": pos.path.days_held,
                "cost": round(pos.cost, 2),
            }
        )
    trades.sort(key=lambda t: t["entry_day"])

    final = curve[-1][1] if curve else sizing.start_capital
    peak = sizing.start_capital
    max_dd = 0.0
    for _, value in curve:
        peak = max(peak, value)
        max_dd = min(max_dd, (value / peak - 1) * 100)

    by_reason: dict[str, list[dict]] = {}
    by_account: dict[str, list[dict]] = {}
    for trade in trades:
        by_reason.setdefault(trade["exit_reason"], []).append(trade)
        for account in trade["accounts"]:
            by_account.setdefault(account, []).append(trade)

    step = max(1, len(curve) // CURVE_POINTS)
    sampled = curve[::step]
    if curve and sampled[-1] != curve[-1]:
        sampled.append(curve[-1])

    return {
        "key": variant.key,
        "label": variant.label,
        "group": variant.group,
        "final_equity": round(final, 2),
        "return_pct": round((final / sizing.start_capital - 1) * 100, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "avg_invested_pct": (
            round(statistics.fmean(invested_share) * 100, 1) if invested_share else 0
        ),
        "open_positions": len(open_positions),
        **_summarise_trades(trades),
        "skipped": skipped,
        "exits": {
            reason: _summarise_trades(rows)
            for reason, rows in sorted(by_reason.items())
        },
        "accounts": {
            account: _summarise_trades(rows)
            for account, rows in sorted(by_account.items())
        },
        "curve": [
            {"t": day.isoformat(), "equity": round(value, 2)} for day, value in sampled
        ],
        "trade_log": trades,
    }


# --------------------------------------------------------------------------- #
# Account quality and the long-history exit study
# --------------------------------------------------------------------------- #


def account_quality(
    bullish: list[Signal],
    series: dict[str, Series],
    benchmark: Series,
    followed: set[str],
    *,
    horizons: tuple[int, ...] = (5, FORWARD_DAYS),
    min_signals: int = 5,
) -> list[dict]:
    """Per account: how its (deduplicated) bullish calls did over the next
    5 and 20 trading days (bought at the next close), in absolute terms and
    against SPY. Sorted by the 20-day excess return, then the 5-day one."""
    rows: dict[str, dict[int, list[tuple[float, float]]]] = {}
    for sig in bullish:
        s = series.get(sig.symbol)
        if s is None:
            continue
        i = s.index_after(sig.day)
        if i is None:
            continue
        per = rows.setdefault(sig.account, {h: [] for h in horizons})
        for h in horizons:
            if i + h >= len(s):
                continue
            ret = (s.closes[i + h] / s.closes[i] - 1) * 100
            b0 = benchmark.close_on_or_before(s.days[i])
            b1 = benchmark.close_on_or_before(s.days[i + h])
            excess = ret - ((b1 / b0 - 1) * 100 if b0 and b1 else 0.0)
            per[h].append((ret, excess))

    def stats(values: list[tuple[float, float]]) -> Optional[dict]:
        if len(values) < min_signals:
            return None
        rets = [r for r, _ in values]
        excess = [e for _, e in values]
        return {
            "signals": len(values),
            "hit_rate": round(sum(r > 0 for r in rets) / len(rets), 4),
            "avg_return_pct": round(statistics.fmean(rets), 2),
            "avg_excess_pct": round(statistics.fmean(excess), 2),
            "beat_spy_rate": round(sum(e > 0 for e in excess) / len(excess), 4),
        }

    out = []
    for account, per in rows.items():
        windows = {f"d{h}": stats(per[h]) for h in horizons}
        if all(w is None for w in windows.values()):
            continue
        out.append({"account": account, "followed": account in followed, **windows})

    def key(row: dict) -> tuple[float, float]:
        def excess(name: str) -> float:
            w = row.get(name)
            return w["avg_excess_pct"] if w else float("-inf")

        return excess(f"d{horizons[-1]}"), excess(f"d{horizons[0]}")

    out.sort(key=key, reverse=True)
    return out


def exit_study(
    series: dict[str, Series],
    symbols: Iterable[str],
    exits: list[Variant],
    *,
    trend_filter: str = "above_200d",
    step: int = EXIT_STUDY_STEP,
) -> dict:
    """Every exit rule on the same synthetic entries: a buy every ``step``
    trading days in each symbol, wherever ``trend_filter`` passes."""
    entries: list[tuple[Series, int]] = []
    for symbol in sorted(set(symbols)):
        s = series.get(symbol)
        if s is None or len(s) < 260:
            continue
        for i in range(200, len(s) - 1, step):
            if passes_trend_filter(s, i, trend_filter):
                entries.append((s, i))

    rows = []
    for variant in exits:
        paths = [run_trade(s, i, variant.exit) for s, i in entries]
        if not paths:
            continue
        returns = [p.return_pct for p in paths]
        held = [max(p.days_held, 1) for p in paths]
        reasons: dict[str, int] = {}
        for p in paths:
            reasons[p.final_reason] = reasons.get(p.final_reason, 0) + 1
        # Return per year held: compares exits that hold for very different
        # spells on the same footing (what the freed cash can earn elsewhere).
        per_year = sum(returns) / sum(held) * 365
        rows.append(
            {
                "key": variant.key,
                "label": variant.label,
                "trades": len(paths),
                "avg_return_pct": round(statistics.fmean(returns), 2),
                "median_return_pct": round(statistics.median(returns), 2),
                "win_rate": round(sum(r > 0 for r in returns) / len(returns), 4),
                "avg_days_held": round(statistics.fmean(held), 1),
                "return_per_year_held_pct": round(per_year, 2),
                "worst_pct": round(min(returns), 2),
                "p10_pct": round(_percentile(returns, 10), 2),
                "still_open": reasons.get("open", 0),
                "exits": dict(sorted(reasons.items())),
            }
        )
    first = min((s.days[i] for s, i in entries), default=None)
    last = max((s.days[i] for s, i in entries), default=None)
    return {
        "entries": len(entries),
        "symbols": len({s.symbol for s, _ in entries}),
        "first_entry": first.isoformat() if first else None,
        "last_entry": last.isoformat() if last else None,
        "trend_filter": trend_filter,
        "rows": rows,
    }


def _percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    k = (len(ordered) - 1) * pct / 100
    lo = int(k)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #


def build_report(
    signals: list[Signal],
    series: dict[str, Series],
    followed: Iterable[str],
    *,
    variants: list[Variant] = VARIANTS,
    include_trades_for: Iterable[str] = ("current",),
) -> dict:
    """Run every variant and both studies; pure, no I/O.

    :param signals: Every stored call, both directions (bearish calls count
        towards the rolling hit rates).
    :param series: Daily series per symbol, including :data:`BENCHMARK`.
    :param followed: The strategy's followed accounts (lower-case).
    """
    followed_set = {f.lower() for f in followed}
    benchmark = series.get(BENCHMARK)
    signals = [replace(s, account=s.account.lower()) for s in signals]
    deduped = dedupe(signals)
    bullish = [
        s
        for s in deduped
        if s.direction == "bullish" and s.symbol not in INDEX_TRACKERS
    ]
    priced = [s for s in bullish if s.symbol in series]
    if benchmark is None or not priced:
        return {
            "window": None,
            "signals": len(bullish),
            "variants": [],
            "accounts": [],
            "exit_study": None,
            "assumptions": ASSUMPTIONS,
        }

    start = min(s.day for s in priced)
    end = benchmark.days[-1]
    calendar = [d for d in benchmark.days if start < d <= end]
    hit_rates = HitRates(deduped, series)
    keep_trades = set(include_trades_for)

    results = []
    cache: dict[EntryRules, dict[date, list[Candidate]]] = {}
    for variant in variants:
        if variant.entry not in cache:
            cache[variant.entry] = candidates_for(
                variant.entry, priced, series, followed_set, hit_rates, start, end
            )
        result = simulate_portfolio(variant, cache[variant.entry], series, calendar)
        if variant.key not in keep_trades:
            result.pop("trade_log")
        results.append(result)

    b0 = benchmark.close_on_or_before(calendar[0]) if calendar else None
    b1 = benchmark.closes[-1]
    first_day = benchmark.index_on_or_before(start)
    spy_start = benchmark.closes[first_day] if first_day is not None else b0
    bench_return = (b1 / spy_start - 1) * 100 if spy_start else None

    exits = [v for v in variants if v.group in ("baseline", "exit")]
    mentioned = {s.symbol for s in priced if s.symbol != BENCHMARK}

    return {
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "benchmark": {
            "symbol": BENCHMARK,
            "return_pct": round(bench_return, 2) if bench_return is not None else None,
        },
        "signals": len(bullish),
        "signals_priced": len(priced),
        "accounts_seen": len({s.account for s in priced}),
        "symbols_priced": len(mentioned),
        "followed": sorted(followed_set),
        "variants": results,
        "accounts": account_quality(priced, series, benchmark, followed_set),
        "exit_study": exit_study(series, mentioned, exits),
        "assumptions": ASSUMPTIONS,
    }


# --------------------------------------------------------------------------- #
# Loading and caching (the only I/O)
# --------------------------------------------------------------------------- #


async def load_signals(Session: async_sessionmaker) -> list[Signal]:
    """Every stored stock/ETF call, oldest first."""
    kinds = ", ".join(f"'{k}'" for k in TRADED_KINDS)
    sql = text(
        "SELECT ticker, user_screen_name, called_at, direction, price_at_call, "
        "sentiment_score FROM trader_calls "
        f"WHERE UPPER(COALESCE(asset_kind, '')) IN ({kinds}) ORDER BY called_at"
    )
    async with Session() as session:
        rows = (await session.execute(sql)).all()
    out = []
    for ticker, user, called_at, direction, price, score in rows:
        if isinstance(called_at, str):
            called_at = datetime.fromisoformat(called_at)
        if called_at is None or direction not in ("bullish", "bearish"):
            continue
        out.append(
            Signal(
                symbol=str(ticker).upper(),
                account=str(user).lower(),
                day=called_at.date(),
                direction=direction,
                price=float(price) if price else None,
                sentiment=abs(float(score or 0.0)),
            )
        )
    return out


async def load_series(symbols: Iterable[str]) -> dict[str, Series]:
    names = sorted(set(symbols) | {BENCHMARK})
    fetched = await asyncio.gather(
        *(get_price_series(name, HISTORY_RANGE) for name in names),
        return_exceptions=True,
    )
    out: dict[str, Series] = {}
    for name, points in zip(names, fetched):
        if isinstance(points, BaseException) or not points:
            continue
        series = Series(name, points)
        if len(series) >= 30:
            out[name] = series
    return out


async def run_backtest(Session: async_sessionmaker, followed: Iterable[str]) -> dict:
    """Load every stored call and the prices behind them, and build the report."""
    started = time.monotonic()
    signals = await load_signals(Session)
    bullish = {s.symbol for s in signals if s.direction == "bullish"}
    series = await load_series(bullish)
    report = await asyncio.to_thread(build_report, signals, series, list(followed))
    report["symbols_missing"] = len(bullish - set(series))
    report["computed_at"] = datetime.now(timezone.utc).isoformat()
    report["took_seconds"] = round(time.monotonic() - started, 1)
    return report


#: Results stay fresh this long; a run reads a few hundred price histories.
CACHE_TTL = 6 * 3600


class BacktestRunner:
    """Runs one backtest at a time in the background and keeps the last
    result, so the HTTP request never waits on hundreds of price fetches."""

    def __init__(self) -> None:
        self.result: Optional[dict] = None
        self.error: Optional[str] = None
        self.finished_at: float = 0.0
        self._task: Optional[asyncio.Task] = None
        self._followed: tuple[str, ...] = ()

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def status(self) -> dict:
        state = (
            "running"
            if self.running
            else "ready"
            if self.result
            else ("error" if self.error else "idle")
        )
        return {"status": state, "error": self.error, "result": self.result}

    def ensure(
        self, Session: async_sessionmaker, followed: Iterable[str], *, force=False
    ) -> None:
        followed_key = tuple(sorted(f.lower() for f in followed))
        stale = (
            self.result is None
            or time.time() - self.finished_at > CACHE_TTL
            or followed_key != self._followed
        )
        if self.running or not (force or stale):
            return
        self._followed = followed_key
        self._task = asyncio.create_task(self._run(Session, followed_key))

    async def _run(self, Session: async_sessionmaker, followed: tuple[str, ...]):
        try:
            self.result = await run_backtest(Session, followed)
            self.error = None
        except Exception as exc:  # surfaced through status(), not raised
            logger.exception("[backtest] run failed")
            self.error = repr(exc)
        finally:
            self.finished_at = time.time()


RUNNER = BacktestRunner()
