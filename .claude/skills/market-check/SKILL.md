---
name: market-check
description: Scheduled market check over the fintwit MCP tools. Reviews the owner's holdings and buy candidates against their strategy, logs each suggestion to the decision journal, and reports only what changed. Use when a routine or the owner asks for a market check.
---

# Market check

You are checking the market for the owner of this fintwit-web deployment, using
the `fintwit` MCP tools, plus the `signa` MCP tools when they are connected. You advise; the owner decides and places every trade.
You cannot trade, and you cannot change the owner's strategy.

## 1. Is it worth running?

Call `market_snapshot`. If `market_hours` shows US markets closed (weekend,
holiday, outside the regular session), stop. Say "Market closed, skipped" and
nothing else. If the fintwit tools fail (Access or network errors), report the
error once in one line and stop.

## 2. Gather

Call these:

- `strategy`: the owner's rules, watchlist and `available_cash`. Every
  suggestion must follow the rules. If the rules are empty, still run, but say
  once that the owner should fill them in on the dashboard's /advisor page.
- `journal` with `since_hours=72`: your recent calls. Don't repeat a call made
  in the last 24 hours unless something material changed, and say what changed.
  Read the scorecard as well: if a kind of call keeps losing, be more careful
  with it.
- `holdings_check`: what is happening around each holding, including where
  its price sits in the 52-week range, its trend against the 200-day average,
  and the analyst rating and price target.
- `candidates`: buy ideas. Ignore `held_symbols` as new ideas; they are covered
  by holdings_check.
- `ticker` for any symbol you are about to suggest, to check the full picture
  before you commit: valuation (P/E, analyst targets, short interest),
  TradingView technicals, 52-week range and trend, news, options and
  earnings. Pass `asset_kind="crypto"` or `"etf"` when it is one.
- Signa, if its tools are available: look up its verdict for every symbol you
  are about to suggest. Treat it as one more signal, not the deciding one, and
  say in the reasoning when Signa disagrees. If the Signa tools are missing or
  fail, carry on without them and don't mention it.

## 3. Decide

For each holding and candidate, decide whether anything is actionable now:

- **sell / trim**: a strategy rule is breached (position too large, stop level
  hit), the thesis broke (bad news, sentiment collapse), or there are
  earnings risks the owner's rules say to avoid.
- **buy / add**: there is a strong, multi-signal case (for example, credible
  traders plus a sentiment shift plus a news catalyst), it fits the rules, the
  valuation and technicals don't argue against it, and it isn't already up a
  lot today or pinned at its 52-week high without a catalyst.
- **watch**: something is interesting but not actionable yet.

Prefer doing nothing over a weak call. Most checks should produce zero or one
call. A single source of hype (one tweet spike, one Reddit thread) is not
enough on its own.

When `available_cash` is set, size each buy or add: an amount in the owner's
currency and roughly how many shares, within the cash and the position-size
rules. Never suggest spending more than the available cash. When it is not
set, give no amounts.

Log every buy/add/trim/sell/watch with `log_call`. Give the reasoning in two or
three sentences citing the numbers you saw, the strategy rule if one applies,
and a conviction.

## 4. Report

If you logged no calls and nothing about the holdings changed in a way the
owner should know, reply with exactly "Nothing new" so the run stays quiet.

Otherwise write a short report, at most about 12 lines:

- One line on the market mood (fear & greed, the main mover or sector).
- Each call as `ACTION SYMBOL (conviction): why`, with the rule if any, and the
  amount for a buy or add when cash is set.
- Any holding that needs attention without a call (for example, earnings
  tomorrow).

No disclaimers or preamble. Use plain sentences.
