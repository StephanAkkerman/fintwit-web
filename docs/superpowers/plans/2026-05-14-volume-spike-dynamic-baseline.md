# Volume Spike Dynamic Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Scale the volume spike baseline window to 4× the active window so the widget produces results at all timeframes, including 7d.

**Architecture:** One-line change to `get_volume_baseline()` in the backend (the floor stays 7d for short windows, 4× kicks in at 48h+). Frontend derives the dynamic subtitle label from `windowHours` using the same formula.

**Tech Stack:** Python / SQLAlchemy / pytest-asyncio (backend), React / TypeScript (frontend)

---

## File Map

| File | Change |
|------|--------|
| `app/services/mention_aggregator.py` | Change `baseline_hours` formula (line 264) |
| `tests/test_mention_aggregator.py` | Add test for 7d-window spike detection |
| `frontend/src/components/VolumeBaselineWidget.tsx` | Replace hardcoded subtitle with dynamic label |

---

### Task 1: Update baseline formula in `get_volume_baseline`

**Files:**
- Modify: `app/services/mention_aggregator.py:264`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_mention_aggregator.py`:

```python
async def test_volume_baseline_7d_window_detects_spike(Session):
    """With window_hours=168, baseline = 28d, so spikes within the week still register."""
    from app.services.mention_aggregator import get_volume_baseline

    # 7 tweets in the last 7d (active window) — enough to clear the >5 filter
    active = [_tweet(i, ["SPIKE"], "NEUTRAL", 0.0, hours_ago)
              for i, hours_ago in enumerate([10, 30, 50, 70, 90, 110, 130], start=1)]
    # 2 tweets in the prior 21 days (within 28d baseline, outside 7d window)
    historical = [
        _tweet(20, ["SPIKE"], "NEUTRAL", 0.0, 200),
        _tweet(21, ["SPIKE"], "NEUTRAL", 0.0, 400),
    ]
    await _insert(Session, active + historical)

    rows = await get_volume_baseline(Session, window_hours=168, threshold=1.5)
    spike = next((r for r in rows if r["ticker"] == "SPIKE"), None)
    assert spike is not None, "Expected SPIKE to appear; widget was empty at 7d window"
    assert spike["volume_multiplier"] > 1.5
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_mention_aggregator.py::test_volume_baseline_7d_window_detects_spike -v
```

Expected: FAIL — `AssertionError: Expected SPIKE to appear; widget was empty at 7d window`

- [ ] **Step 3: Update the baseline formula**

In `app/services/mention_aggregator.py`, replace lines 263–264:

```python
    # Baseline span = 4× the active window, floored at 7d.
    # This ensures spikes are detectable even when window_hours = 168 (7d).
    baseline_hours = max(24 * 7, 4 * window_hours)
```

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/test_mention_aggregator.py::test_volume_baseline_7d_window_detects_spike -v
```

Expected: PASS

- [ ] **Step 5: Verify existing volume baseline test is unaffected**

```
pytest tests/test_mention_aggregator.py::test_volume_baseline_multiplier -v
```

Expected: PASS — for `window_hours=24`, `max(168, 96) = 168`, so behavior is identical to before.

- [ ] **Step 6: Run the full test suite**

```
pytest --maxfail=1 --disable-warnings -q
```

Expected: all passing.

- [ ] **Step 7: Commit**

```
git add app/services/mention_aggregator.py tests/test_mention_aggregator.py
git commit -m "feat: scale volume spike baseline to 4x active window"
```

---

### Task 2: Dynamic subtitle in `VolumeBaselineWidget`

**Files:**
- Modify: `frontend/src/components/VolumeBaselineWidget.tsx:56`

- [ ] **Step 1: Replace the hardcoded subtitle**

In `frontend/src/components/VolumeBaselineWidget.tsx`, replace the subtitle span (line 56) and add the two helper constants directly inside the component function, before the `return` statement.

Current code near line 50:

```tsx
  const visible = data.slice(0, 10)
  const overflow = data.length - 10
  const maxMultiplier = Math.max(...data.map(d => d.volume_multiplier)) || 1

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-950 p-4 flex flex-col gap-0">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-[13px] font-semibold text-zinc-100">Unusually loud</h2>
        <span className="text-[10px] text-zinc-500 font-mono">today vs 7-day avg</span>
      </div>
```

Replace with:

```tsx
  const visible = data.slice(0, 10)
  const overflow = data.length - 10
  const maxMultiplier = Math.max(...data.map(d => d.volume_multiplier)) || 1
  const baselineDays = Math.max(7, Math.round((4 * windowHours) / 24))
  const activeLabel = windowHours <= 24 ? 'today' : windowHours <= 48 ? 'last 48h' : 'this week'

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-950 p-4 flex flex-col gap-0">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-[13px] font-semibold text-zinc-100">Unusually loud</h2>
        <span className="text-[10px] text-zinc-500 font-mono">{activeLabel} vs {baselineDays}d avg</span>
      </div>
```

- [ ] **Step 2: Verify TypeScript compiles**

```
cd frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Verify labels at each window selection**

Start the dev server (`npm run dev` in `frontend/`) and open the dashboard. Select each timeframe button and confirm:

| Selected window | Expected subtitle |
|---|---|
| 24h | `today vs 7d avg` |
| 48h | `last 48h vs 8d avg` |
| 168h (7d) | `this week vs 28d avg` |

Also confirm the widget shows results (non-empty) when 7d is selected, provided there is data in the last 28 days.

- [ ] **Step 4: Commit**

```
git add frontend/src/components/VolumeBaselineWidget.tsx
git commit -m "feat: dynamic volume spike subtitle scales with selected timeframe"
```
