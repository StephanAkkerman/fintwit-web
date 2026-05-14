# Volume Spike Dynamic Baseline Design

**Date:** 2026-05-14  
**Status:** Approved

## Problem

The volume spike widget (`VolumeBaselineWidget`) compares mention counts in the active window against a 7-day rolling average. When the user selects the 7-day timeframe, the active window and the baseline span become identical — the formula reduces to `current_7d / current_7d = 1.0×`, which never exceeds the 1.5× spike threshold. The widget goes empty.

## Solution

Scale the baseline span dynamically as a multiple of the active window (4×), with a minimum floor of 7 days. This preserves current behavior at the 24h default and gives meaningful results at all timeframes.

### Baseline formula

```
baseline_hours = max(7 * 24, 4 * window_hours)
```

| window_hours | baseline_hours | buckets | meaning |
|---|---|---|---|
| 24 | 168 (7d) | 7.0 | unchanged — current behavior |
| 48 | 192 (8d) | 4.0 | 4 × 48h windows |
| 168 | 672 (28d) | 4.0 | 4 × 7d windows |

"Spike" always means the active window had 4× more mentions than a typical window of the same length — consistent sensitivity across timeframes.

## Changes

### Backend

**File:** `app/services/mention_aggregator.py` (line ~264)

```python
# Before
baseline_hours = max(24 * 7, window_hours)

# After
baseline_hours = max(24 * 7, 4 * window_hours)
```

No changes to the API response shape, query parameters, or database schema.

### Frontend

**File:** `frontend/src/components/VolumeBaselineWidget.tsx`

1. Compute baseline days from the `windowHours` prop (mirrors backend formula):

```ts
const baselineDays = Math.max(7, Math.round((4 * windowHours) / 24));
```

2. Replace the hardcoded subtitle `"today vs 7-day avg"` with a dynamic label:

| windowHours | active label | baseline label | subtitle |
|---|---|---|---|
| 24 | "today" | "7d avg" | "today vs 7d avg" |
| 48 | "last 48h" | "8d avg" | "last 48h vs 8d avg" |
| 168 | "this week" | "28d avg" | "this week vs 28d avg" |

No changes to `types.ts`, the API endpoint, `useVolumeBaseline.ts`, or any other file.

## Out of Scope

- Changing the 1.5× spike threshold
- Changing the minimum 5-mention filter
- Adjusting the top-10 result limit
