import type { ReactNode } from 'react'
import { Sparkline } from './Sparkline'
import { useMarketPositioning } from '../hooks/useMarketPositioning'
import type {
  CtaExposure,
  CtaTriggers,
  FuturesCrowding,
  FuturesPositioning,
  MarketConcentration,
} from '../types'

const BADGE_BASE = 'rounded-full px-2 py-0.5 text-[11px] font-semibold'
const BADGE_UP = 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300'
const BADGE_DOWN = 'bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-300'
const BADGE_WARN = 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300'
const BADGE_NEUTRAL = 'bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300'

const CROWDING: Record<FuturesCrowding, { label: string; className: string }> = {
  crowded_short: { label: 'Crowded short', className: BADGE_WARN },
  neutral: { label: 'Neutral', className: BADGE_NEUTRAL },
  crowded_long: { label: 'Crowded long', className: BADGE_WARN },
}

const EXPOSURE: Record<CtaExposure, { label: string; className: string }> = {
  max_long: { label: 'Max long', className: BADGE_UP },
  long: { label: 'Leaning long', className: BADGE_UP },
  flat: { label: 'Flat', className: BADGE_NEUTRAL },
  short: { label: 'Leaning short', className: BADGE_DOWN },
  max_short: { label: 'Max short', className: BADGE_DOWN },
}

const BREADTH: Record<MarketConcentration['trend'], { label: string; className: string }> = {
  narrowing: { label: 'Narrowing', className: BADGE_WARN },
  stable: { label: 'Stable', className: BADGE_NEUTRAL },
  broadening: { label: 'Broadening', className: BADGE_UP },
}

function signed(value: number, digits = 1, suffix = '%'): string {
  return `${value > 0 ? '+' : ''}${value.toFixed(digits)}${suffix}`
}

function compact(value: number): string {
  return `${value > 0 ? '+' : ''}${value.toLocaleString(undefined, {
    notation: 'compact',
    maximumFractionDigits: 1,
  })}`
}

function toneClass(value: number): string {
  return value >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'
}

function Section({
  title,
  badge,
  children,
}: {
  title: string
  badge?: { label: string; className: string }
  children: ReactNode
}) {
  return (
    <section className="rounded-lg border border-zinc-200 bg-zinc-50 p-3 dark:border-zinc-800 dark:bg-zinc-900/60">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-zinc-500">{title}</h3>
        {badge && <span className={`${BADGE_BASE} ${badge.className}`}>{badge.label}</span>}
      </div>
      {children}
    </section>
  )
}

function Unavailable() {
  return <p className="py-4 text-center text-xs text-zinc-500">Source unavailable right now.</p>
}

function FuturesRow({ contract }: { contract: FuturesPositioning }) {
  const crowding = CROWDING[contract.crowding]
  return (
    <div className="space-y-1.5 border-t border-zinc-200 pt-2 first:border-t-0 first:pt-0 dark:border-zinc-800">
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-medium text-zinc-800 dark:text-zinc-200">{contract.name}</span>
        <span className={`${BADGE_BASE} ${crowding.className}`}>{crowding.label}</span>
      </div>
      <div className="flex items-end justify-between gap-2">
        <div>
          <p className={`text-base font-semibold ${toneClass(contract.lev_net_pct_oi)}`}>
            {signed(contract.lev_net_pct_oi)} of OI
          </p>
          <p className="text-[11px] text-zinc-500">
            Net {compact(contract.lev_net)} contracts
            {contract.lev_net_change != null && <> · {compact(contract.lev_net_change)} w/w</>}
          </p>
        </div>
        <Sparkline data={contract.history.map((h) => h.lev_net_pct_oi)} width={72} height={24} />
      </div>
      <div>
        <div
          className="relative h-1.5 rounded-full bg-gradient-to-r from-amber-300 via-zinc-200 to-amber-300 dark:from-amber-700 dark:via-zinc-700 dark:to-amber-700"
          aria-label={`${contract.lev_percentile.toFixed(0)}th percentile of the last ${contract.weeks_ranked} weeks`}
        >
          <span
            className="absolute top-1/2 h-3 w-1 -translate-x-1/2 -translate-y-1/2 rounded-sm bg-zinc-900 dark:bg-zinc-100"
            style={{ left: `${Math.min(100, Math.max(0, contract.lev_percentile))}%` }}
          />
        </div>
        <p className="mt-1 text-[11px] text-zinc-500">
          {contract.lev_percentile.toFixed(0)}th percentile over {contract.weeks_ranked} weeks ·
          asset managers {signed(contract.asset_mgr_net_pct_oi)} · {contract.report_date}
        </p>
      </div>
    </div>
  )
}

function CtaTable({ cta }: { cta: CtaTriggers }) {
  return (
    <>
      <table className="w-full text-xs">
        <thead>
          <tr className="text-left text-[11px] uppercase tracking-wide text-zinc-500">
            <th className="pb-1 font-medium">Lookback</th>
            <th className="pb-1 text-right font-medium">Trigger</th>
            <th className="pb-1 text-right font-medium">Distance</th>
            <th className="pb-1 text-right font-medium">Signal</th>
          </tr>
        </thead>
        <tbody>
          {cta.signals.map((s) => (
            <tr
              key={s.lookback}
              className={
                s.lookback === cta.nearest_trigger ? 'font-semibold text-zinc-900 dark:text-zinc-100' : ''
              }
            >
              <td className="py-0.5">{s.lookback}</td>
              <td className="py-0.5 text-right font-mono">{s.trigger.toFixed(2)}</td>
              <td className={`py-0.5 text-right font-mono ${toneClass(s.distance_pct)}`}>
                {signed(s.distance_pct)}
              </td>
              <td
                className={`py-0.5 text-right ${
                  s.signal === 'long'
                    ? 'text-emerald-600 dark:text-emerald-400'
                    : 'text-rose-600 dark:text-rose-400'
                }`}
              >
                {s.signal === 'long' ? 'Long' : 'Short'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-[11px] text-zinc-500">
        {cta.symbol} {cta.spot.toFixed(2)} · the bold row is the closest flip.
      </p>
    </>
  )
}

function ConcentrationTable({ concentration }: { concentration: MarketConcentration }) {
  return (
    <>
      <div className="mb-2 flex items-center justify-between gap-2">
        <span className="text-[11px] text-zinc-500">
          {concentration.equal_weighted} / {concentration.cap_weighted}, 1Y
        </span>
        <Sparkline data={concentration.ratio_history.map((p) => p.ratio)} width={96} height={24} />
      </div>
      <table className="w-full text-xs">
        <thead>
          <tr className="text-left text-[11px] uppercase tracking-wide text-zinc-500">
            <th className="pb-1 font-medium">Window</th>
            <th className="pb-1 text-right font-medium">{concentration.cap_weighted}</th>
            <th className="pb-1 text-right font-medium">{concentration.equal_weighted}</th>
            <th className="pb-1 text-right font-medium">Spread</th>
          </tr>
        </thead>
        <tbody>
          {concentration.windows.map((w) => (
            <tr key={w.window}>
              <td className="py-0.5">{w.window}</td>
              <td className="py-0.5 text-right font-mono">{signed(w.cap_weighted_pct)}</td>
              <td className="py-0.5 text-right font-mono">{signed(w.equal_weighted_pct)}</td>
              <td className={`py-0.5 text-right font-mono ${toneClass(w.spread_pp)}`}>
                {signed(w.spread_pp, 1, 'pp')}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-[11px] text-zinc-500">
        A negative spread means the biggest names are carrying the index.
      </p>
    </>
  )
}

export default function MarketPositioningWidget() {
  const { data, loading, error } = useMarketPositioning()

  return (
    <div className="rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-zinc-500">
        Market Positioning
      </h2>

      {loading ? (
        <div className="grid gap-3 lg:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-48 animate-pulse rounded-lg bg-zinc-100 dark:bg-zinc-800" />
          ))}
        </div>
      ) : error || !data ? (
        <p className="text-sm text-red-500">Could not load market positioning data.</p>
      ) : (
        <>
          <div className="grid gap-3 lg:grid-cols-3">
            <Section title="Hedge funds in index futures">
              {data.futures?.length ? (
                <div className="space-y-2">
                  {data.futures.map((contract) => (
                    <FuturesRow key={contract.code} contract={contract} />
                  ))}
                </div>
              ) : (
                <Unavailable />
              )}
            </Section>

            <Section
              title={`CTA trigger levels${data.cta ? ` · ${data.cta.symbol}` : ''}`}
              badge={data.cta ? EXPOSURE[data.cta.exposure] : undefined}
            >
              {data.cta ? <CtaTable cta={data.cta} /> : <Unavailable />}
            </Section>

            <Section
              title="Breadth vs. concentration"
              badge={data.concentration ? BREADTH[data.concentration.trend] : undefined}
            >
              {data.concentration ? (
                <ConcentrationTable concentration={data.concentration} />
              ) : (
                <Unavailable />
              )}
            </Section>
          </div>

          <p className="mt-3 text-[11px] text-zinc-400">
            Estimates from free public data, not anyone's actual book. Hedge funds are the CFTC
            "leveraged funds" bucket (weekly Traders in Financial Futures report); a net short near
            the bottom of its 3-year range is the setup for a forced short squeeze. CTA signals
            approximate trend followers with time-series momentum: each lookback flips when price
            crosses the close it is measured from. Breadth compares equal-weight (RSP) with
            cap-weighted (SPY) S&P 500, the free proxy for passive money crowding into the largest
            names. The options gamma regime is in the widget above.
          </p>
        </>
      )}
    </div>
  )
}
