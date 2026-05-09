# Design Brief — Swing-Trader Overview Dashboard

**Date:** 2026-05-09
**Status:** First prototype generated

---

## Problem Statement

**Who:** Swing trader / weekly horizon. Does not need tick-by-tick data. Needs sentiment trends, volume anomalies, and emerging tickers — signals that play out over hours to days, not seconds.

**What:** A top-level overview page (`/`) that replaces the current minimal home route with a structured dashboard answering three questions in one glance:
1. **State** — What is the market doing right now?
2. **Signal** — What is everyone talking about? What's unusual?
3. **Action** — What does that mean for me? What's emerging?

**Why:** The current home route has Fear & Greed + Reddit WSB + Market Overview — not enough structure for a swing trader scan. Discord channels become dashboard widgets.

---

## Chosen Direction

**Layout:** Newspaper Hero (Concept 01)
- Full-width macro strip (state, always visible)
- Asset filter tabs: All / Stocks / Crypto / Forex + freshness timestamp
- Hero: Mention Heat treemap (the signal at a glance)
- 3-column widget row below: Sentiment Shift | Volume Baseline | Hidden Gem

**Route structure:** One cross-asset overview at `/`. Existing `/stocks`, `/crypto`, `/forex` pages remain as drill-downs with their asset-specific widgets.

---

## Interaction Model

- **Pattern:** Dashboard / scan-first
- **Navigation:** Asset filter tabs on the overview; existing sidebar for route navigation
- **Data density:** Medium-dense (treemap is rich, widgets are compact leaderboards)
- **Responsive:** Desktop-first (swing trader at desk)
- **Freshness:** "Updated Xm ago" timestamp in the tab bar; widgets show their own staleness if needed

---

## Widget Specifications

### Macro Strip (State)
- 7 tickers: SPX, NDX, BTC, ETH, DXY, VIX, Gold
- Per ticker: label + 6-point sparkline + last price + Δ%
- Dark background (`bg-zinc-900` / `bg-zinc-950`) to visually separate from dashboard body
- Color: green sparkline = price up, red = down, amber = flat

### Asset Filter Tabs
- Pills: All / Stocks / Crypto / Forex
- Active tab controls the data scope of ALL widgets on the page
- Freshness timestamp (right-aligned): "Updated 2m ago"

### Mention Heat Treemap (Hero — Must Have #1)
- Full width, ~200px tall
- Cell size = mention volume in the selected window (24h default)
- Cell color = avg sentiment: dark emerald (strong bull) → light emerald (mild bull) → zinc (neutral) → amber (mild bear) → rose (strong bear)
- Cell border ring = price direction: bright ring = price up, dim ring = price down
- Click a cell → filters tweet feed to that ticker
- Sparse data handling: minimum threshold (default 50 mentions). Empty cells show "widen window to see more" nudge with inline link to switch to 48h.

### Sentiment Shift Leaderboard (Must Have #2)
- Top 10 tickers with biggest 24h sentiment swing
- Row: ticker | was (colored label) → now (colored badge)
- Sorted by magnitude of swing (BEAR → BULL ranked above NEUT → BULL)
- "+ N more" truncation

### Volume Baseline (Must Have #3)
- Tickers unusually loud vs their 7-day mention average
- Row: ticker | bar (amber/orange fill, proportional to multiplier) | multiplier label (+9.4×)
- Catches pre-trending signals before they hit the treemap hero
- "+ N more" truncation

### Hidden Gem
- Two subtypes, visually distinguished:
  - **Resurfacing** — last mentioned 7+ days ago, appearing again. Badge: "↩ resurface"
  - **First mention** — never seen before in the dataset. Badge: "✦ new"
- Row: ticker | subtype badge | days-since-last (for resurfacing) or "first time" label
- Rationale: contrarian discovery before crowd catches on

---

## Design Tokens (from codebase)

No custom token file found. Using Tailwind defaults aligned to existing app conventions:

| Token | Value |
|-------|-------|
| Background | `bg-black` / `bg-zinc-900` |
| Surface | `bg-zinc-900` / `bg-zinc-800` |
| Border | `border-zinc-800` / `border-zinc-700` |
| Text primary | `text-zinc-100` |
| Text secondary | `text-zinc-400` / `text-zinc-500` |
| Bullish | `emerald-400` / `emerald-500` |
| Bearish | `rose-400` / `rose-500` |
| Volume spike / alert | `amber-400` / `amber-500` |
| Active / selected | `zinc-100` bg + `zinc-900` text (inverted) |
| Links | `blue-400` / `blue-500` |
| Card radius | `rounded-2xl` (existing convention) |

---

## Rejected Alternatives

- **Bloomberg Grid (02):** Too dense for a swing trader's weekly scan. Terminal aesthetic requires full-time attention.
- **Intelligence Brief (03):** 3-column editorial is readable but the equal-weight columns don't give the treemap enough visual priority.
- **Concordance Split (07):** Strong concept but the concordance/divergence logic requires more backend work to surface actionably; better as a secondary widget once the must-haves are built.
- **Focus Tabs (08):** Too single-purpose. Swing traders want a summary view, not a drilled-down view as the default.
- **Per-asset dashboards:** Rejected in favour of filter tabs on a single overview. Avoids duplicating widget logic three times.
- **Earnings/Econ Calendar as third widget:** Replaced by Hidden Gem because the calendar is already a known future event; Hidden Gem surfaces unknown-unknown signals which are more valuable for swing discovery.

---

## Implementation Path (7-step migration workflow)

1. **DB model:** `TickerMentionSummary` — daily aggregated mention count, sentiment score, first_seen, last_seen per ticker
2. **Service:** `mention_aggregator.py` — aggregates from tweet store, computes 7-day baseline, detects resurfacing/new tickers
3. **Repository:** `MentionRepo` — CRUD for aggregated summaries
4. **Runtime worker:** periodic aggregation (every 15m) writing to SQLite
5. **API endpoints:** `GET /api/overview/mention-heat`, `/sentiment-shift`, `/volume-baseline`, `/hidden-gems`
6. **Frontend hooks:** `useMentionHeat`, `useSentimentShift`, `useVolumeBaseline`, `useHiddenGems`
7. **UI:** `OverviewDashboard.tsx` replacing the home route content

---

## Open Questions

- Minimum mention threshold for treemap: 50 (configurable via sidebar control?)
- Lookback window for "resurfacing": currently 7 days — is 14 days better for a weekly swing trader?
- Should the macro strip sparklines use real price data (Yahoo Finance) or just the relative delta?
