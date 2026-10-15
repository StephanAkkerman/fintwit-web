import { useWorldIndices } from '../hooks/useWorldIndices'
import type { WorldIndex, WorldIndexRegion, WorldIndices } from '../types'

const BADGE_BASE = 'rounded-full px-2 py-0.5 text-[11px] font-semibold'
const BADGE_UP = 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300'
const BADGE_DOWN = 'bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-300'
const BADGE_NEUTRAL = 'bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300'

const SEMIS_TONE: Record<NonNullable<WorldIndices['semis']>['tone'], { text: string; className: string }> = {
  bearish: { text: 'pressure on US semis', className: BADGE_DOWN },
  neutral: { text: 'no strong signal for US semis', className: BADGE_NEUTRAL },
  bullish: { text: 'tailwind for US semis', className: BADGE_UP },
}

function signed(value: number): string {
  return `${value > 0 ? '+' : ''}${value.toFixed(2)}%`
}

function toneClass(value: number | null): string {
  if (value == null || value === 0) return 'text-zinc-500'
  return value > 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'
}

/** Regional-indicator flag emoji from an ISO alpha-2 code ("EU" has one too). */
function flag(country: string): string {
  if (!/^[A-Z]{2}$/.test(country)) return ''
  return String.fromCodePoint(...[...country].map((c) => 0x1f1e6 + c.charCodeAt(0) - 65))
}

function formatPrice(value: number): string {
  return value.toLocaleString(undefined, { maximumFractionDigits: 2, minimumFractionDigits: 2 })
}

function sessionDay(date: string): string {
  // Plain YYYY-MM-DD: format in UTC so the viewer's timezone can't shift the day.
  const parsed = new Date(`${date}T00:00:00Z`)
  if (Number.isNaN(parsed.getTime())) return date
  return parsed.toLocaleDateString(undefined, { month: 'short', day: 'numeric', timeZone: 'UTC' })
}

function opensIn(nextOpen: string, now: number): string | null {
  const ms = new Date(nextOpen).getTime() - now
  if (!Number.isFinite(ms) || ms <= 0 || ms > 36 * 3_600_000) return null
  const hours = Math.floor(ms / 3_600_000)
  const minutes = Math.round((ms % 3_600_000) / 60_000)
  return hours > 0 ? `opens in ${hours}h ${minutes}m` : `opens in ${minutes}m`
}

function SessionLabel({ index, now }: { index: WorldIndex; now: number }) {
  if (index.is_open == null) return null
  if (index.is_open) {
    return (
      <span className="inline-flex items-center gap-1 text-[11px] text-emerald-600 dark:text-emerald-400">
        <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" aria-hidden />
        Open
      </span>
    )
  }
  const parts = ['Closed']
  if (index.session_date) parts.push(sessionDay(index.session_date))
  const next = index.next_open ? opensIn(index.next_open, now) : null
  if (next) parts.push(next)
  return <span className="text-[11px] text-zinc-500">{parts.join(' · ')}</span>
}

function IndexRow({ index, now }: { index: WorldIndex; now: number }) {
  return (
    <li className="border-t border-zinc-200 py-2 first:border-t-0 first:pt-0 last:pb-0 dark:border-zinc-800">
      <div className="flex items-baseline justify-between gap-2">
        <a
          href={index.website ?? undefined}
          target="_blank"
          rel="noreferrer"
          className="truncate text-sm font-medium text-zinc-800 hover:underline dark:text-zinc-200"
          title={index.tv_symbol}
        >
          <span className="mr-1" aria-hidden>
            {flag(index.country)}
          </span>
          {index.name}
        </a>
        <span className={`shrink-0 text-sm font-semibold tabular-nums ${toneClass(index.change_percent)}`}>
          {index.change_percent == null ? '—' : signed(index.change_percent)}
        </span>
      </div>
      <div className="flex items-baseline justify-between gap-2">
        <SessionLabel index={index} now={now} />
        <span className="text-[11px] tabular-nums text-zinc-500">{formatPrice(index.price)}</span>
      </div>
      <p className="mt-0.5 text-[11px] text-zinc-400">{index.read_through}</p>
    </li>
  )
}

function RegionCard({ region, now }: { region: WorldIndexRegion; now: number }) {
  return (
    <section className="rounded-lg border border-zinc-200 bg-zinc-50 p-3 dark:border-zinc-800 dark:bg-zinc-900/60">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-zinc-500">{region.label}</h3>
        {region.avg_change_percent != null && (
          <span className={`text-xs font-semibold tabular-nums ${toneClass(region.avg_change_percent)}`}>
            avg {signed(region.avg_change_percent)}
          </span>
        )}
      </div>
      <ul>
        {region.indices.map((index) => (
          <IndexRow key={index.symbol} index={index} now={now} />
        ))}
      </ul>
    </section>
  )
}

export default function WorldIndicesWidget() {
  const { data, loading, error } = useWorldIndices()
  const now = Date.now()
  const semis = data?.semis ? { ...data.semis, ...SEMIS_TONE[data.semis.tone] } : null

  return (
    <div className="rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-500">World Markets</h2>
        {semis && (
          <span
            className={`${BADGE_BASE} ${semis.className}`}
            title={`Average of ${semis.symbols.join(', ')}`}
          >
            Chip-heavy indices {signed(semis.avg_change_percent)}: {semis.text}
          </span>
        )}
      </div>

      {loading ? (
        <div className="grid gap-3 lg:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-64 animate-pulse rounded-lg bg-zinc-100 dark:bg-zinc-800" />
          ))}
        </div>
      ) : error || !data ? (
        <p className="text-sm text-red-500">Could not load world market data.</p>
      ) : data.regions.length === 0 ? (
        <p className="py-4 text-center text-xs text-zinc-500">No index quotes available right now.</p>
      ) : (
        <>
          <div className="grid gap-3 lg:grid-cols-3">
            {data.regions.map((region) => (
              <RegionCard key={region.key} region={region} now={now} />
            ))}
          </div>
          <p className="mt-3 text-[11px] text-zinc-400">
            Asia trades while New York sleeps and Europe overlaps the US pre-market, so their moves
            hint at how US stocks open. A closed market's change is from the session dated next to
            it. The chip-heavy badge averages the Nikkei, KOSPI, TAIEX and AEX (Tokyo Electron, SK
            Hynix, Samsung, TSMC, ASML) as a read-through for US semiconductors.
          </p>
        </>
      )}
    </div>
  )
}
