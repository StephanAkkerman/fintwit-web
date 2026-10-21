import { useState } from 'react'
import type { IndicatorsAssetKind } from '../hooks/useTechnicalIndicators'
import { useTechnicalIndicators } from '../hooks/useTechnicalIndicators'
import type { TechnicalIndicators } from '../types'

const UP = 'text-emerald-600 dark:text-emerald-400'
const DOWN = 'text-rose-600 dark:text-rose-400'
const MUTED = 'text-zinc-500 dark:text-zinc-400'
const WARN = 'text-amber-600 dark:text-amber-400'

const TOOLTIPS = {
  rsi: 'RSI (14-day) — momentum from 0 to 100. Over 70 is overbought (it has run hard), under 30 oversold. The second number is the 4-hour RSI.',
  macd: 'MACD (12, 26, 9) — trend momentum. Above its signal line is bullish, below is bearish; a cross on the latest daily bar is flagged.',
  sma: 'Distance of the price from its simple moving average over that many trading days.',
  cross: 'Whether the 50-day average sits above the 200-day (golden cross, a long-term uptrend) or below it (death cross).',
  atr: 'ATR (14-day) — the typical daily price range, as a percent of the price. Useful for sizing a stop: two ATRs is a common distance.',
  adx: 'ADX (14-day) — trend strength, regardless of direction: 25+ is a strong trend, under 20 a range. The arrow shows which way it points.',
  volume: 'Today’s volume against its 30-day average. Today is partial until the close.',
} as const

/** The asset kinds `/api/research/indicators` covers, from a tweet asset's kind. */
export function indicatorsKind(kind: string | null | undefined): IndicatorsAssetKind | null {
  switch ((kind ?? '').trim().toUpperCase()) {
    case 'EQUITY':
    case 'STOCK':
      return 'stock'
    case 'ETF':
      return 'etf'
    case 'CRYPTO':
      return 'crypto'
    default:
      return null
  }
}

function fmtPct(value: number): string {
  return `${value > 0 ? '+' : ''}${value.toFixed(1)}%`
}

type Row = { key: string; label: string; tooltip: string; value: string; className: string }

function buildRows(data: TechnicalIndicators): Row[] {
  const rows: Row[] = []
  const { rsi, macd, moving_averages: ma, atr, adx, volume } = data

  if (rsi.value !== null) {
    const fourH = typeof rsi.four_h === 'number' ? ` · 4H ${rsi.four_h.toFixed(0)}` : ''
    const state = rsi.state === 'overbought' || rsi.state === 'oversold' ? ` ${rsi.state}` : ''
    rows.push({
      key: 'rsi',
      label: 'RSI',
      tooltip: TOOLTIPS.rsi,
      value: `${rsi.value.toFixed(0)}${state}${fourH}`,
      className: rsi.state === 'overbought' ? WARN : rsi.state === 'oversold' ? UP : '',
    })
  }
  if (macd.above_signal !== null) {
    const cross = macd.cross ? ' (crossed)' : ''
    rows.push({
      key: 'macd',
      label: 'MACD',
      tooltip: TOOLTIPS.macd,
      value: `${macd.above_signal ? 'Above' : 'Below'} signal${cross}`,
      className: macd.above_signal ? UP : DOWN,
    })
  }
  for (const days of [20, 50, 200] as const) {
    const value = ma[`price_vs_sma${days}_percent`]
    if (value === null) continue
    rows.push({
      key: `sma${days}`,
      label: `vs ${days}D`,
      tooltip: TOOLTIPS.sma,
      value: fmtPct(value),
      className: value >= 0 ? UP : DOWN,
    })
  }
  if (ma.sma50_vs_sma200) {
    const golden = ma.sma50_vs_sma200 === 'golden_cross'
    rows.push({
      key: 'cross',
      label: '50/200',
      tooltip: TOOLTIPS.cross,
      value: `${golden ? 'Golden' : 'Death'} cross${ma.cross_today ? ' today' : ''}`,
      className: golden ? UP : DOWN,
    })
  }
  if (atr.percent_of_price !== null) {
    rows.push({
      key: 'atr',
      label: 'ATR',
      tooltip: TOOLTIPS.atr,
      value: `${atr.percent_of_price.toFixed(1)}% / day`,
      className: '',
    })
  }
  if (adx.value !== null) {
    const arrow = adx.direction === 'up' ? ' ↑' : adx.direction === 'down' ? ' ↓' : ''
    rows.push({
      key: 'adx',
      label: 'ADX',
      tooltip: TOOLTIPS.adx,
      value: `${adx.value.toFixed(0)} ${adx.trend_strength ?? ''}${arrow}`.trim(),
      className:
        adx.trend_strength === 'strong' ? (adx.direction === 'down' ? DOWN : UP) : '',
    })
  }
  if (volume.vs_avg_30d !== null) {
    rows.push({
      key: 'volume',
      label: 'Volume',
      tooltip: TOOLTIPS.volume,
      value: `${volume.vs_avg_30d.toFixed(2)}× avg`,
      className: volume.vs_avg_30d >= 1.5 ? WARN : '',
    })
  }
  return rows
}

/**
 * Collapsed "Technicals" toggle under a ticker card. Expanding it fetches the
 * daily indicators for that one symbol, so the timeline stays uncluttered and
 * makes no requests until someone asks.
 */
export default function TechnicalIndicatorsPanel({
  symbol,
  assetKind,
  className = '',
}: {
  symbol: string
  assetKind: IndicatorsAssetKind
  className?: string
}) {
  const [open, setOpen] = useState(false)
  const { data, loading, error } = useTechnicalIndicators(symbol, assetKind, open)
  const rows = data ? buildRows(data) : []

  return (
    <div className={className}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-label={`${open ? 'Hide' : 'Show'} technical indicators for $${symbol}`}
        className="flex w-full items-center justify-between rounded-lg px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-zinc-500 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-800/70"
      >
        <span>Technicals</span>
        <svg
          className={`h-3 w-3 transition-transform ${open ? 'rotate-180' : ''}`}
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          aria-hidden="true"
        >
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>
      {open && (
        <div className="mt-1 rounded-lg bg-zinc-100 px-2 py-1.5 text-[10px] text-zinc-700 dark:bg-zinc-800/70 dark:text-zinc-200">
          {loading && !data && <div className={MUTED}>Loading indicators…</div>}
          {!loading && error && <div className={MUTED}>No indicator data for ${symbol}.</div>}
          {rows.length > 0 && (
            <dl className="grid grid-cols-2 gap-x-3 gap-y-0.5">
              {rows.map((row) => (
                <div key={row.key} className="flex items-center justify-between gap-2" title={row.tooltip}>
                  <dt className={MUTED}>{row.label}</dt>
                  <dd className={`truncate font-semibold ${row.className}`.trim()}>{row.value}</dd>
                </div>
              ))}
            </dl>
          )}
          {data?.source === 'price_history' && (
            <div className={`mt-1 ${MUTED}`}>Computed from daily prices; TradingView was unavailable.</div>
          )}
        </div>
      )}
    </div>
  )
}
