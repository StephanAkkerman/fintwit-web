import { useOptionsFlow } from '../hooks/useResearch'
import type { FlowRanking, OptionsFlow } from '../types'
import { BADGE_BASE, DOWN, MUTED, UP, biasBadge, contractLabel, fmtMoney } from './flowFormat'

type RankingKey = 'scored_bullish_premium' | 'scored_bearish_premium' | 'bullish_call_premium'

const LISTS: { title: string; key: RankingKey; field: 'top_bullish' | 'top_bearish' | 'top_call_buying'; tone: string; tooltip: string }[] = [
  {
    title: 'Most bullish',
    key: 'scored_bullish_premium',
    field: 'top_bullish',
    tone: UP,
    tooltip: 'Premium in trades Signa scored bullish (bought calls, sold puts).',
  },
  {
    title: 'Most bearish',
    key: 'scored_bearish_premium',
    field: 'top_bearish',
    tone: DOWN,
    tooltip: 'Premium in trades Signa scored bearish (bought puts, sold calls).',
  },
  {
    title: 'Call buying',
    key: 'bullish_call_premium',
    field: 'top_call_buying',
    tone: UP,
    tooltip: 'Premium in $250K+ call trades Unusual Whales marked bullish.',
  },
]

function Ranking({
  title,
  rows,
  valueKey,
  tone,
  tooltip,
  onTickerClick,
}: {
  title: string
  rows: FlowRanking[]
  valueKey: RankingKey
  tone: string
  tooltip: string
  onTickerClick?: (ticker: string) => void
}) {
  return (
    <div className="rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-2 dark:border-zinc-800 dark:bg-zinc-900/60">
      <p className="mb-1 text-[11px] uppercase tracking-wide text-zinc-500" title={tooltip}>
        {title}
      </p>
      {rows.length === 0 ? (
        <p className={`text-xs ${MUTED}`}>None today.</p>
      ) : (
        <ol className="space-y-0.5 text-xs">
          {rows.slice(0, 6).map((row) => (
            <li key={row.symbol} className="flex items-center justify-between gap-2">
              <button
                type="button"
                onClick={() => onTickerClick?.(row.symbol)}
                className="font-semibold text-zinc-800 hover:underline dark:text-zinc-100"
              >
                ${row.symbol}
              </button>
              <span className={`font-mono font-semibold ${tone}`}>{fmtMoney(row[valueKey])}</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}

function TopTrades({ data }: { data: OptionsFlow }) {
  const trades = data.top_scored.slice(0, 5)
  if (trades.length === 0) return null
  return (
    <div>
      <p className="mb-1 text-[11px] uppercase tracking-wide text-zinc-500">Biggest scored trades</p>
      <ul className="divide-y divide-zinc-200 text-xs dark:divide-zinc-800">
        {trades.map((t, i) => (
          <li key={`${t.at}-${i}`} className="flex flex-wrap items-baseline justify-between gap-x-3 py-1">
            <span className="font-semibold text-zinc-800 dark:text-zinc-100">
              {contractLabel(t)}
              {t.sweep ? <span className={`ml-1 font-normal ${MUTED}`}>sweep</span> : null}
            </span>
            <span className={`font-mono font-semibold ${t.direction === 'BULLISH' ? UP : t.direction === 'BEARISH' ? DOWN : ''}`}>
              {fmtMoney(t.premium)}
              {t.conviction != null ? <span className={`ml-1 font-normal ${MUTED}`}>{t.conviction}/100</span> : null}
            </span>
            {t.rationale && <p className={`w-full truncate ${MUTED}`} title={t.rationale}>{t.rationale}</p>}
          </li>
        ))}
      </ul>
    </div>
  )
}

/**
 * Market-wide unusual options flow over about the last trading day, from
 * Signa (Unusual Whales): which symbols drew the most bullish and bearish
 * premium, and the biggest trades Signa scored.
 */
export default function OptionsFlowWidget({ onTickerClick }: { onTickerClick?: (ticker: string) => void }) {
  const { data, loading, error } = useOptionsFlow(null)
  const badge = data ? biasBadge(data.bias) : null

  return (
    <div className="rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-500">Options Flow</h2>
          <p className="text-[11px] text-zinc-500">Signa (Unusual Whales), about the last trading day</p>
        </div>
        {badge && (
          <span className={`${BADGE_BASE} ${badge.className}`} title="Premium-weighted direction of the trades Signa scored">
            {badge.label}
          </span>
        )}
      </div>

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-8 animate-pulse rounded bg-zinc-100 dark:bg-zinc-800" />
          ))}
        </div>
      ) : error || !data ? (
        <p className="text-sm text-red-500">Could not load options flow.</p>
      ) : (
        <div className="space-y-3">
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-zinc-600 dark:text-zinc-300">
            <span>
              <span className="text-zinc-500">Scored bullish</span>{' '}
              <span className={`font-semibold ${UP}`}>{fmtMoney(data.scored_bullish_premium)}</span>
            </span>
            <span>
              <span className="text-zinc-500">Scored bearish</span>{' '}
              <span className={`font-semibold ${DOWN}`}>{fmtMoney(data.scored_bearish_premium)}</span>
            </span>
            <span>
              <span className="text-zinc-500">$250K+ calls / puts</span>{' '}
              <span className="font-semibold">
                {fmtMoney(data.call_premium)} / {fmtMoney(data.put_premium)}
              </span>
            </span>
          </div>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
            {LISTS.map((list) => (
              <Ranking
                key={list.field}
                title={list.title}
                rows={data[list.field] ?? []}
                valueKey={list.key}
                tone={list.tone}
                tooltip={list.tooltip}
                onTickerClick={onTickerClick}
              />
            ))}
          </div>
          <TopTrades data={data} />
        </div>
      )}
    </div>
  )
}
