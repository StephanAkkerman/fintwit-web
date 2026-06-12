import type { TickerScopeStat } from '../types'
import type { MentionLookup } from '../hooks/useMentionFrequency'

function compact(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`
  return String(n)
}

const SIGNAL_EMOJI: Record<TickerScopeStat['signal'], string> = {
  new: '🆕',
  resurfacing: '🆕',
  top: '🥇',
  hot: '🔥',
  rising: '📈',
  falling: '📉',
  neutral: '',
}

function stanceEmoji(stat: TickerScopeStat): string {
  if (stat.stance_flipped) return '🔀'
  if (stat.stance === 'bullish') return '🐂'
  if (stat.stance === 'bearish') return '🐻'
  if (stat.stance === 'mixed') return '🔀'
  return ''
}

function signalPhrase(stat: TickerScopeStat, who: string, isPersonal: boolean): string {
  const pct =
    stat.pct_change != null
      ? `${stat.pct_change > 0 ? '+' : ''}${Math.round(stat.pct_change * 100)}%`
      : null

  switch (stat.signal) {
    case 'new':
      return `${who}: first mention ever`
    case 'resurfacing':
      return stat.days_since_last != null
        ? `${who}: first mention in ${stat.days_since_last}d`
        : `${who}: resurfacing after a long silence`
    case 'top':
      return isPersonal
        ? `${who}: #1 ticker (${stat.mentions} in 30d)`
        : `#1 most-mentioned overall (${compact(stat.mentions)} in 30d)`
    case 'hot':
      return `${who}: ${compact(stat.mentions)} mentions in 30d`
    case 'rising':
    case 'falling':
      return `${who}: ${pct} vs prev 30d (${stat.mentions} vs ${stat.prev_mentions})`
    default:
      return `${who}: ${compact(stat.mentions)} in 30d`
  }
}

function stancePhrase(stat: TickerScopeStat): string | null {
  if (stat.stance_flipped) {
    const to = stat.stance ?? 'mixed'
    return `flipped to ${to} (was the opposite prior 30d)`
  }
  if (stat.stance === 'bullish') return `bullish ${stat.stance_bull}/${stat.stance_total} mentions`
  if (stat.stance === 'bearish') return `bearish ${stat.stance_bear}/${stat.stance_total} mentions`
  if (stat.stance === 'mixed') return 'mixed views'
  return null
}

function tooltip(stat: TickerScopeStat, who: string, isPersonal: boolean): string {
  const parts = [signalPhrase(stat, who, isPersonal)]
  const stance = stancePhrase(stat)
  if (stance) parts.push(stance)
  return parts.join(' · ')
}

function TrendLabel({ stat }: { stat: TickerScopeStat }) {
  if (stat.pct_change == null) return null
  const pct = Math.round(stat.pct_change * 100)
  if (pct === 0) return null
  const up = pct > 0
  return (
    <span
      className={up ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}
    >
      {up ? '📈' : '📉'} {up ? '+' : ''}
      {pct}%
    </span>
  )
}

function ScopeLine({
  label,
  who,
  isPersonal,
  stat,
}: {
  label: string
  who: string
  isPersonal: boolean
  stat: TickerScopeStat | null
}) {
  if (!stat) return null
  const emoji = `${SIGNAL_EMOJI[stat.signal]}${stanceEmoji(stat)}`
  return (
    <div
      title={tooltip(stat, who, isPersonal)}
      className="flex cursor-help items-center gap-1.5 text-[11px] text-zinc-600 dark:text-zinc-300"
    >
      <span className="max-w-[6.5rem] shrink-0 truncate text-zinc-500 dark:text-zinc-400">
        {label}
      </span>
      {emoji && <span>{emoji}</span>}
      <span className="font-medium tabular-nums">{compact(stat.mentions)}</span>
      <TrendLabel stat={stat} />
    </div>
  )
}

/** Per-ticker mention-frequency block rendered inside an asset card. */
export default function AssetMentions({
  author,
  ticker,
  lookup,
}: {
  author: string
  ticker: string
  lookup: MentionLookup
}) {
  const freq = lookup(author, ticker)
  if (!freq) return null
  if (!freq.personal?.notable && !freq.global?.notable) return null

  return (
    <div className="mt-1.5 border-t border-zinc-200 pt-1.5 dark:border-zinc-700">
      <div className="mb-0.5 text-[9px] font-semibold uppercase tracking-wide text-zinc-400 dark:text-zinc-500">
        Mentions · 30d
      </div>
      <ScopeLine
        label={`@${author}`}
        who={`@${author}`}
        isPersonal
        stat={freq.personal ?? null}
      />
      <ScopeLine label="all" who="all" isPersonal={false} stat={freq.global ?? null} />
    </div>
  )
}
