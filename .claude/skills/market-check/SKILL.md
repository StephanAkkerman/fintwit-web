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
- `followed_traders` with `since_hours=24`: tickers the traders the owner
  follows just posted about. These come first among buy ideas; see "Leads from
  followed traders" below.
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

### Leads from followed traders

The owner picked these traders because they rate their calls, so every lead
that isn't already held gets a `ticker` look, even when nothing else flags it.
Skip a lead the journal already covered in the last 24 hours unless the trader
posted again with something new. Then judge two things separately:

- **Fundamentals**: valuation against growth (P/E or EV/sales against peers
  and its own history), revenue and earnings trend, balance sheet, analyst
  rating and target versus price, short interest. Pass when the business is
  sound and the price isn't stretched for what it delivers.
- **Technicals**: TradingView's summary and moving-average ratings, trend
  against the 50- and 200-day averages, where it sits in the 52-week range,
  and how far it has run since the trader posted (`price_at_post`). Pass when
  the trend is up or basing and the entry isn't a chase.

Only when **both** pass is it a `buy`. If one passes and the other doesn't,
log a `watch` that names the side that failed and what would change your mind.
If both fail, skip it silently. Bearish posts from a followed trader about a
holding belong in the holdings review, not here.

For a lead you do buy, name the trader and link their post in the reasoning,
pass `rule="followed trader @name"` to `log_call`, and mention their 7-day
hit rate from `traders` when it is there.

**No cash for it.** When `available_cash` is 0, or too small for a position
the rules allow, pick the one holding the new idea should replace: the
weakest of them on the same two tests (broken trend, thesis gone stale, worst
valuation for its growth, smallest expected upside to target), and never one
with earnings or a catalyst in the next few days that the owner is holding for.
Log a `sell` (or `trim`, if part of it is enough) for that holding with
`rule="swap for SYMBOL"`, and size the `buy` from what the sale frees up. If
no holding is clearly weaker than the new idea, log the idea as a `watch` and
say no swap is worth it. When `available_cash` is not set, don't assume
either way: give the buy without an amount and name the swap candidate in one
line in case the owner has no cash.

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
  A swap gets one line instead of two: `SWAP SELL_SYMBOL -> BUY_SYMBOL: why`.
- Any holding that needs attention without a call (for example, earnings
  tomorrow).

No disclaimers or preamble. Use plain sentences.
