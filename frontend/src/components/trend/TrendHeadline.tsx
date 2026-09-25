import type { ReactNode } from 'react'
import type { AssetKind, TrendPair, TrendSummary } from '../../types'
import { useElementWidth } from '../../hooks/useElementWidth'
import {
  INK, TREND_WINDOW_LABEL, buildHeadline, fmtCount, fmtNet, netOf,
  type Segment, type Tone,
} from '../../utils/trendSummary'

const TONE_DOT: Record<Tone, string> = {
  bull: INK.bull, bear: INK.bear, accent: INK.accent, muted: INK.muted, violet: INK.violet,
}

const PREV_LABEL = { '1d': 'previous 24h', '7d': 'previous 7d', '30d': 'previous 30d' } as const

function Segments({ segments, onTickerClick }: { segments: Segment[]; onTickerClick?: (t: string) => void }) {
  return (
    <>
      {segments.map((s, i) => {
        if (typeof s === 'string') return <span key={i}>{s}</span>
        if ('ticker' in s) {
          return (
            <button
              key={i}
              type="button"
              onClick={() => onTickerClick?.(s.ticker)}
              className="font-mono font-semibold text-zinc-100 underline decoration-zinc-600 decoration-dotted underline-offset-2 hover:text-sky-300"
            >
              {s.ticker}
            </button>
          )
        }
        return <b key={i} className="font-mono font-semibold text-zinc-100">{s.value}</b>
      })}
    </>
  )
}

function Sparkline({ values, color, zeroLine = false, label }: { values: number[]; color: string; zeroLine?: boolean; label: string }) {
  const [ref, width] = useElementWidth<HTMLDivElement>(160)
  const h = 40
  if (values.length < 2) return <div ref={ref} className="h-10" />
  let lo = Math.min(...values), hi = Math.max(...values)
  if (zeroLine) { lo = Math.min(lo, -0.1); hi = Math.max(hi, 0.1) }
  const x = (i: number) => (i / (values.length - 1)) * (width - 4) + 2
  const y = (v: number) => h - 3 - ((v - lo) / (hi - lo || 1)) * (h - 6)
  const pts = values.map((v, i) => `${x(i)},${y(v)}`).join(' ')
  const last = values.length - 1
  return (
    <div ref={ref} className="mt-auto pt-2">
      <svg width={width} height={h} role="img" aria-label={`${label} trend`} className="block overflow-visible">
        {zeroLine && <line x1={0} x2={width} y1={y(0)} y2={y(0)} stroke={INK.grid} strokeDasharray="2 3" />}
        <polygon points={`${x(0)},${h} ${pts} ${x(last)},${h}`} fill={color} opacity={0.12} />
        <polyline points={pts} fill="none" stroke={color} strokeWidth={1.75} strokeLinejoin="round" />
        <circle cx={x(last)} cy={y(values[last])} r={2.75} fill={color} />
      </svg>
    </div>
  )
}

function CountDelta({ pair, prevLabel }: { pair: TrendPair; prevLabel: string }) {
  if (pair.previous === 0) {
    return <span className="text-zinc-500">{pair.current ? 'nothing to compare with yet' : 'no activity'}</span>
  }
  const d = pair.current / pair.previous - 1
  const cls = d > 0.02 ? 'text-emerald-400' : d < -0.02 ? 'text-rose-400' : 'text-zinc-500'
  return (
    <span>
      <span className={cls}>{d >= 0 ? '▲' : '▼'} {Math.abs(d * 100).toFixed(0)}%</span>
      <span className="text-zinc-500"> vs {prevLabel}</span>
    </span>
  )
}

function Kpi({ label, value, delta, children }: { label: string; value: string; delta: ReactNode; children: ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-0.5 rounded-xl bg-zinc-950/40 px-3 py-2.5">
      <span className="font-mono text-[10px] font-medium uppercase tracking-wider text-zinc-500">{label}</span>
      <span className="font-mono text-[22px] font-semibold tabular-nums text-zinc-100">{value}</span>
      <span className="font-mono text-[11px] leading-snug">{delta}</span>
      {children}
    </div>
  )
}

interface Props {
  data: TrendSummary
  assetKind: AssetKind
  onTickerClick?: (ticker: string) => void
}

export function TrendHeadline({ data, assetKind, onTickerClick }: Props) {
  const { lead, items } = buildHeadline(data, assetKind)
  const { totals } = data
  const prevLabel = PREV_LABEL[data.window]
  const netSeries = totals.series.bull.map((b, i) => netOf(b, totals.series.bear[i]) ?? 0)
  const net = totals.net_sentiment

  return (
    <section aria-label="Summary" className="grid grid-cols-1 gap-4 rounded-2xl border border-zinc-800 bg-zinc-900 p-4 lg:grid-cols-[minmax(0,1.25fr)_minmax(0,2fr)]">
      <div className="flex flex-col gap-2.5">
        <span className="font-mono text-[10px] font-medium uppercase tracking-wider text-zinc-500">
          What happened · {TREND_WINDOW_LABEL[data.window]}
        </span>
        <p className="text-[17px] font-semibold leading-snug text-zinc-100 [text-wrap:balance]">
          <Segments segments={lead} onTickerClick={onTickerClick} />
        </p>
        {items.length > 0 && (
          <ul className="flex flex-col gap-1.5">
            {items.map((item, i) => (
              <li key={i} className="flex gap-2 text-[13px] leading-snug text-zinc-400">
                <span className="mt-1.5 h-[7px] w-[7px] shrink-0 rounded-full" style={{ background: TONE_DOT[item.tone] }} />
                <span><Segments segments={item.segments} onTickerClick={onTickerClick} /></span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Kpi label="Tweets" value={fmtCount(totals.tweets.current)} delta={<CountDelta pair={totals.tweets} prevLabel={prevLabel} />}>
          <Sparkline values={totals.series.tweets} color={INK.accent} label="Tweets" />
        </Kpi>
        <Kpi label="Accounts" value={fmtCount(totals.authors.current)} delta={<CountDelta pair={totals.authors} prevLabel={prevLabel} />}>
          <Sparkline values={totals.series.authors} color={INK.accent} label="Accounts" />
        </Kpi>
        <Kpi
          label="Net sentiment"
          value={fmtNet(net.current)}
          delta={<span className="text-zinc-500">{fmtNet(net.previous)} in the {prevLabel}</span>}
        >
          <Sparkline values={netSeries} color={(net.current ?? 0) >= 0 ? INK.bull : INK.bear} zeroLine label="Net sentiment" />
        </Kpi>
        <Kpi label="Tickers" value={fmtCount(totals.tickers.current)} delta={<CountDelta pair={totals.tickers} prevLabel={prevLabel} />}>
          <Sparkline values={totals.series.tickers} color={INK.accent} label="Tickers" />
        </Kpi>
      </div>
    </section>
  )
}
