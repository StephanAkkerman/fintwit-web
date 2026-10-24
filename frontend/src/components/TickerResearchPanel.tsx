import { useState } from 'react'
import { useIntegrationsStatus } from '../hooks/useIntegrationsStatus'
import { useAnalystActivity, useDarkPool, useOptionsFlow, useTrendStage } from '../hooks/useResearch'
import type { AnalystActivity, DarkPool, OptionsFlow, RelativeStrength, TrendStage } from '../types'
import {
  BADGE_BASE,
  DOWN,
  MUTED,
  UP,
  biasBadge,
  contractLabel,
  fmtMoney,
  fmtSigned,
  signTone,
  stageBadge,
} from './flowFormat'

const CARD = 'rounded-xl bg-zinc-100/80 p-3 text-xs dark:bg-zinc-800/70'
const HEADING = 'text-xs font-semibold uppercase tracking-wide text-zinc-500'

const TOOLTIPS = {
  stage:
    'Weinstein stage from the weekly chart and its 30-week average: 1 basing, 2 advancing (the stage to buy), 3 topping, 4 declining.',
  rs: 'Mansfield relative strength: how the price ratio against the benchmark compares with its own 52-week average. Above 0 is outperforming lately.',
  eps: 'How the consensus EPS estimate for this fiscal year moved over the last 30 days, and how many analysts revised it up or down.',
  buy: 'Share of analysts rating it buy or strong buy, and the change against three months ago.',
  flow: 'Unusual options flow over about the last trading day, from Signa (Unusual Whales). Scored trades carry Signa’s direction: sold puts count as bullish.',
  dark: 'The latest off-exchange (dark pool) prints. At the ask leans on buyers, at the bid on sellers. Covers only the minutes those prints span.',
} as const

function Placeholder({ children }: { children: string }) {
  return <p className={MUTED}>{children}</p>
}

function Skeleton() {
  return <div className="h-16 animate-pulse rounded-lg bg-zinc-200/70 dark:bg-zinc-700/50" />
}

function rsLine(label: string, rs: RelativeStrength | null | undefined) {
  if (!rs || rs.mansfield == null) return null
  const arrow = rs.mansfield_rising_4w === true ? ' ↑' : rs.mansfield_rising_4w === false ? ' ↓' : ''
  return (
    <div className="flex items-center justify-between gap-2" title={TOOLTIPS.rs}>
      <dt className={MUTED}>{label}</dt>
      <dd className={`font-semibold ${signTone(rs.mansfield)}`}>
        {fmtSigned(rs.mansfield, 1, '')}
        {arrow}
      </dd>
    </div>
  )
}

function TrendStageCard({ data }: { data: TrendStage }) {
  const { stage, sector } = data
  const badge = stageBadge(stage)
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2" title={TOOLTIPS.stage}>
        <span className={`${BADGE_BASE} ${badge.className}`}>{badge.label}</span>
        <span className={MUTED}>
          {stage.weeks_in_stage} week{stage.weeks_in_stage === 1 ? '' : 's'}
          {stage.previous_stage ? `, after stage ${stage.previous_stage}` : ''}
        </span>
      </div>
      <dl className="space-y-0.5">
        <div className="flex items-center justify-between gap-2">
          <dt className={MUTED}>vs 30-week avg</dt>
          <dd className={`font-semibold ${signTone(stage.price_vs_ma30w_percent)}`}>
            {fmtSigned(stage.price_vs_ma30w_percent)}
          </dd>
        </div>
        <div className="flex items-center justify-between gap-2">
          <dt className={MUTED}>Avg slope, 5 weeks</dt>
          <dd className={`font-semibold ${signTone(stage.ma30w_slope_5w_percent)}`}>
            {fmtSigned(stage.ma30w_slope_5w_percent)}
          </dd>
        </div>
        {rsLine(`RS vs ${data.benchmark}`, data.vs_market)}
        {sector && rsLine(`RS vs ${sector.etf}`, sector.stock_vs_sector)}
      </dl>
      {sector && (
        <p className={MUTED}>
          {sector.name} ({sector.etf})
          {sector.stage ? `: stage ${sector.stage.stage}` : ''}
          {sector.vs_market?.mansfield != null
            ? `, RS vs ${data.benchmark} ${fmtSigned(sector.vs_market.mansfield, 1, '')}`
            : ''}
        </p>
      )}
    </div>
  )
}

function actionLabel(action: string | null): string {
  if (!action) return ''
  return action.charAt(0).toUpperCase() + action.slice(1)
}

function AnalystCard({ data }: { data: AnalystActivity }) {
  const changes = data.rating_changes
  const recs = data.recommendations
  const year = data.estimates.periods['0y']
  const direction = data.estimates.direction
  const directionTone = direction === 'rising' ? UP : direction === 'falling' ? DOWN : ''
  return (
    <div className="space-y-2">
      <dl className="space-y-0.5">
        <div className="flex items-center justify-between gap-2">
          <dt className={MUTED}>Up / down, {changes.days}d</dt>
          <dd className="font-semibold">
            <span className={changes.upgrades ? UP : ''}>{changes.upgrades}</span>
            {' / '}
            <span className={changes.downgrades ? DOWN : ''}>{changes.downgrades}</span>
          </dd>
        </div>
        <div className="flex items-center justify-between gap-2">
          <dt className={MUTED}>Target raises / cuts</dt>
          <dd className="font-semibold">
            {changes.target_raises} / {changes.target_cuts}
          </dd>
        </div>
        {recs?.buy_percent != null && (
          <div className="flex items-center justify-between gap-2" title={TOOLTIPS.buy}>
            <dt className={MUTED}>Buy ratings</dt>
            <dd className="font-semibold">
              {recs.buy_percent.toFixed(0)}%{' '}
              <span className={signTone(recs.buy_percent_change_3m)}>
                ({fmtSigned(recs.buy_percent_change_3m, 0, 'pp')} 3m)
              </span>
            </dd>
          </div>
        )}
        {direction && (
          <div className="flex items-center justify-between gap-2" title={TOOLTIPS.eps}>
            <dt className={MUTED}>EPS est.</dt>
            <dd className={`font-semibold ${directionTone}`}>
              {direction}
              {year?.change_30d_percent != null ? ` (${fmtSigned(year.change_30d_percent)} 30d)` : ''}
              {year?.up_30d != null ? ` · ${year.up_30d}↑ ${year.down_30d ?? 0}↓` : ''}
            </dd>
          </div>
        )}
      </dl>
      {changes.recent_actions.length > 0 && (
        <ul className="space-y-0.5">
          {changes.recent_actions.slice(0, 4).map((a, i) => (
            <li key={`${a.date}-${a.firm}-${i}`} className="flex justify-between gap-2">
              <span className="truncate">
                <span className={MUTED}>{a.date.slice(5)}</span> {a.firm} {actionLabel(a.action).toLowerCase()}
                {a.to_grade ? ` ${a.to_grade}` : ''}
              </span>
              {a.price_target ? (
                <span className={`shrink-0 font-semibold ${signTone(a.target_change_percent)}`}>
                  ${a.price_target.toFixed(0)}
                </span>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function FlowCard({ flow, dark }: { flow: OptionsFlow | null; dark: DarkPool | null }) {
  return (
    <div className="space-y-2">
      {flow && (
        <>
          <div className="flex flex-wrap items-center gap-2" title={TOOLTIPS.flow}>
            <span className={`${BADGE_BASE} ${biasBadge(flow.bias).className}`}>{biasBadge(flow.bias).label}</span>
            <span className={MUTED}>
              {flow.scored_trades} scored · {flow.large_trades} large trades
            </span>
          </div>
          <dl className="space-y-0.5">
            <div className="flex items-center justify-between gap-2">
              <dt className={MUTED}>Scored bull / bear</dt>
              <dd className="font-semibold">
                <span className={UP}>{fmtMoney(flow.scored_bullish_premium)}</span>
                {' / '}
                <span className={DOWN}>{fmtMoney(flow.scored_bearish_premium)}</span>
              </dd>
            </div>
            <div className="flex items-center justify-between gap-2">
              <dt className={MUTED}>Big calls / puts</dt>
              <dd className="font-semibold">
                {fmtMoney(flow.call_premium)} / {fmtMoney(flow.put_premium)}
              </dd>
            </div>
          </dl>
          {flow.top_scored.length > 0 && (
            <ul className="space-y-0.5">
              {flow.top_scored.slice(0, 3).map((t, i) => (
                <li key={`${t.at}-${i}`} title={t.rationale ?? undefined} className="flex justify-between gap-2">
                  <span className="truncate">
                    {contractLabel(t)}
                    {t.sweep ? ' · sweep' : ''}
                  </span>
                  <span
                    className={`shrink-0 font-semibold ${
                      t.direction === 'BULLISH' ? UP : t.direction === 'BEARISH' ? DOWN : ''
                    }`}
                  >
                    {fmtMoney(t.premium)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
      {dark && dark.prints > 0 && (
        <p title={TOOLTIPS.dark}>
          <span className={MUTED}>Dark pool:</span>{' '}
          <span className="font-semibold">{fmtMoney(dark.notional)}</span> in {dark.prints} prints
          {dark.lean ? (
            <>
              , leaning{' '}
              <span
                className={`font-semibold ${
                  dark.lean === 'buyers' ? UP : dark.lean === 'sellers' ? DOWN : ''
                }`}
              >
                {dark.lean}
              </span>
            </>
          ) : null}
        </p>
      )}
    </div>
  )
}

/**
 * Weekly trend stage, analyst activity and (on request) Signa options flow
 * for one ticker, shown in the ticker detail modal. Flow waits for a click
 * because every lookup spends Signa's shared daily quota.
 */
export default function TickerResearchPanel({ ticker }: { ticker: string }) {
  const trend = useTrendStage(ticker)
  const analysts = useAnalystActivity(ticker)
  const { signa } = useIntegrationsStatus()
  const [showFlow, setShowFlow] = useState(false)
  const flow = useOptionsFlow(ticker, showFlow)
  const dark = useDarkPool(ticker, showFlow)

  return (
    <div className="mt-4 grid gap-2 sm:grid-cols-3">
      <section className={CARD} aria-label="Weekly trend stage">
        <h3 className={`${HEADING} mb-2`}>Weekly trend</h3>
        {trend.loading ? (
          <Skeleton />
        ) : trend.data ? (
          <TrendStageCard data={trend.data} />
        ) : (
          <Placeholder>{trend.missing ? 'Not enough weekly history.' : 'Could not load the trend stage.'}</Placeholder>
        )}
      </section>

      <section className={CARD} aria-label="Analyst activity">
        <h3 className={`${HEADING} mb-2`}>Analysts</h3>
        {analysts.loading ? (
          <Skeleton />
        ) : analysts.data ? (
          <AnalystCard data={analysts.data} />
        ) : (
          <Placeholder>{analysts.missing ? 'No analyst coverage.' : 'Could not load analyst data.'}</Placeholder>
        )}
      </section>

      <section className={CARD} aria-label="Options flow">
        <h3 className={`${HEADING} mb-2`}>Options flow</h3>
        {signa === false ? (
          <Placeholder>Needs a Signa key on the server.</Placeholder>
        ) : !showFlow ? (
          <button
            type="button"
            onClick={() => setShowFlow(true)}
            className="rounded-md border border-zinc-300 px-2 py-1 text-[11px] font-semibold text-zinc-700 hover:bg-zinc-200 dark:border-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-700"
          >
            Load flow and dark pool
          </button>
        ) : flow.loading || dark.loading ? (
          <Skeleton />
        ) : flow.data || dark.data ? (
          <FlowCard flow={flow.data} dark={dark.data} />
        ) : (
          <Placeholder>Could not load options flow.</Placeholder>
        )}
      </section>
    </div>
  )
}
