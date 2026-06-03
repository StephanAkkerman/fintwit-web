import type { IbkrAccountSummary, IbkrPosition, IbkrStatus, IbkrTrade } from '../types'

function fmt(n: number | null | undefined, decimals = 2): string {
  if (n == null) return '—'
  return n.toLocaleString(undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })
}

function fmtCurrency(n: number | null | undefined, currency = 'USD'): string {
  if (n == null) return '—'
  return new Intl.NumberFormat(undefined, {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(n)
}

function PnlCell({ value }: { value: number }) {
  const color =
    value > 0
      ? 'text-green-400'
      : value < 0
        ? 'text-red-400'
        : 'text-zinc-400'
  return (
    <span className={color}>
      {value >= 0 ? '+' : ''}
      {fmt(value)}
    </span>
  )
}

function StatusBadge({
  configured,
  connected,
  lastSync,
  lastError,
}: {
  configured: boolean
  connected: boolean
  lastSync: string | null
  lastError: string | null
}) {
  if (!configured) {
    return (
      <div className="rounded border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-400">
        IBKR sync not enabled. Set{' '}
        <code className="text-zinc-300">IBKR_ENABLED=true</code> and add{' '}
        <code className="text-zinc-300">TWS_USERID</code> /{' '}
        <code className="text-zinc-300">TWS_PASSWORD</code> to your{' '}
        <code className="text-zinc-300">.env</code>.
      </div>
    )
  }

  const dotColor = connected ? 'bg-green-500' : 'bg-red-500'
  const label = connected ? 'Connected' : 'Disconnected'
  const syncText = lastSync
    ? `Last sync ${new Date(lastSync).toLocaleTimeString()}`
    : 'Not yet synced'

  return (
    <div className="flex flex-wrap items-center gap-3 rounded border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm">
      <span className="flex items-center gap-1.5">
        <span className={`inline-block h-2 w-2 rounded-full ${dotColor}`} />
        <span className="text-zinc-200">{label}</span>
      </span>
      <span className="text-zinc-400">{syncText}</span>
      {lastError && (
        <span className="text-red-400" title={lastError}>
          Error: {lastError.slice(0, 80)}
        </span>
      )}
    </div>
  )
}

function AccountSummary({ account }: { account: IbkrAccountSummary }) {
  const cards = [
    { label: 'Net Liquidation', key: 'NetLiquidation' },
    { label: 'Cash', key: 'TotalCashValue' },
    { label: 'Gross Positions', key: 'GrossPositionValue' },
    { label: 'Unrealized P&L', key: 'UnrealizedPnL' },
    { label: 'Realized P&L', key: 'RealizedPnL' },
  ] as const

  const hasAny = cards.some((c) => account[c.key] != null)
  if (!hasAny) return null

  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
      {cards.map(({ label, key }) => {
        const entry = account[key]
        if (!entry) return null
        const isNegative = typeof entry.value === 'number' && entry.value < 0
        return (
          <div
            key={key}
            className="rounded border border-zinc-700 bg-zinc-900 p-3"
          >
            <div className="text-xs text-zinc-500">{label}</div>
            <div
              className={`mt-1 text-sm font-semibold ${isNegative ? 'text-red-400' : 'text-zinc-100'}`}
            >
              {fmtCurrency(entry.value, entry.currency)}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function PositionsTable({ positions }: { positions: IbkrPosition[] }) {
  if (positions.length === 0) {
    return <p className="text-sm text-zinc-500">No open positions.</p>
  }

  const totalMarketValue = positions.reduce((s, p) => s + p.market_value, 0)
  const totalPnl = positions.reduce((s, p) => s + p.unrealized_pnl, 0)
  const totalCost = positions.reduce((s, p) => s + p.cost_basis, 0)
  const totalPnlPct = totalCost ? (totalPnl / totalCost) * 100 : 0

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-zinc-700 text-left text-xs text-zinc-500">
            <th className="pb-2 pr-4">Symbol</th>
            <th className="pb-2 pr-4">Type</th>
            <th className="pb-2 pr-4 text-right">Qty</th>
            <th className="pb-2 pr-4 text-right">Avg Cost</th>
            <th className="pb-2 pr-4 text-right">Price</th>
            <th className="pb-2 pr-4 text-right">Market Value</th>
            <th className="pb-2 pr-4 text-right">Unrealized P&L</th>
            <th className="pb-2 text-right">P&L %</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-800">
          {positions.map((p) => (
            <tr key={p.id} className="text-zinc-200">
              <td className="py-1.5 pr-4 font-medium">{p.symbol}</td>
              <td className="py-1.5 pr-4 text-xs text-zinc-500">{p.sec_type}</td>
              <td className="py-1.5 pr-4 text-right">{fmt(p.quantity, 0)}</td>
              <td className="py-1.5 pr-4 text-right">{fmt(p.avg_cost)}</td>
              <td className="py-1.5 pr-4 text-right">
                {p.market_price != null ? fmt(p.market_price) : '—'}
              </td>
              <td className="py-1.5 pr-4 text-right">{fmt(p.market_value)}</td>
              <td className="py-1.5 pr-4 text-right">
                <PnlCell value={p.unrealized_pnl} />
              </td>
              <td className="py-1.5 text-right">
                <PnlCell value={p.unrealized_pnl_percent} />%
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="border-t border-zinc-700 font-semibold text-zinc-100">
            <td colSpan={5} className="pt-2 text-xs text-zinc-500">
              TOTAL
            </td>
            <td className="pt-2 text-right">{fmt(totalMarketValue)}</td>
            <td className="pt-2 text-right">
              <PnlCell value={totalPnl} />
            </td>
            <td className="pt-2 text-right">
              <PnlCell value={totalPnlPct} />%
            </td>
          </tr>
        </tfoot>
      </table>
    </div>
  )
}

function TradesTable({ trades }: { trades: IbkrTrade[] }) {
  const filtered = trades.filter((t) => t.quantity * t.price >= 100)

  if (filtered.length === 0) {
    return <p className="text-sm text-zinc-500">No executions today.</p>
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-zinc-700 text-left text-xs text-zinc-500">
            <th className="pb-2 pr-4">Time</th>
            <th className="pb-2 pr-4">Symbol</th>
            <th className="pb-2 pr-4">Side</th>
            <th className="pb-2 pr-4 text-right">Qty</th>
            <th className="pb-2 pr-4 text-right">Price</th>
            <th className="pb-2 text-right">Commission</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-800">
          {trades.map((t) => {
            const isBuy = t.side === 'BOT'
            return (
              <tr key={t.id} className="text-zinc-200">
                <td className="py-1.5 pr-4 text-xs text-zinc-400">
                  {t.executed_at
                    ? new Date(t.executed_at).toLocaleTimeString()
                    : '—'}
                </td>
                <td className="py-1.5 pr-4 font-medium">{t.symbol}</td>
                <td className={`py-1.5 pr-4 font-semibold ${isBuy ? 'text-green-400' : 'text-red-400'}`}>
                  {isBuy ? 'BUY' : 'SELL'}
                </td>
                <td className="py-1.5 pr-4 text-right">{fmt(t.quantity, 0)}</td>
                <td className="py-1.5 pr-4 text-right">{fmt(t.price)}</td>
                <td className="py-1.5 text-right text-zinc-400">
                  {t.commission != null ? fmt(t.commission) : '—'}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

type IbkrPanelProps = {
  status: IbkrStatus | null
  positions: IbkrPosition[]
  trades: IbkrTrade[]
  account: IbkrAccountSummary
  loading: boolean
  error: string | null
  reload: () => void
}

export default function IbkrPanel({
  status,
  positions,
  trades,
  account,
  loading,
  error,
  reload,
}: IbkrPanelProps) {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-zinc-100">
          IBKR Live Positions
        </h2>
        <button
          onClick={() => void reload()}
          className="rounded border border-zinc-600 px-3 py-1 text-xs text-zinc-400 hover:border-zinc-400 hover:text-zinc-200"
        >
          Refresh
        </button>
      </div>

      {status && (
        <StatusBadge
          configured={status.configured}
          connected={status.connected}
          lastSync={status.last_sync}
          lastError={status.last_error}
        />
      )}

      {loading && <p className="text-sm text-zinc-500">Loading…</p>}
      {error && <p className="text-sm text-red-400">{error}</p>}

      {!loading && !error && (
        <>
          <AccountSummary account={account} />

          <section>
            <h3 className="mb-2 text-sm font-medium text-zinc-400">
              Open Positions
            </h3>
            <PositionsTable positions={positions} />
          </section>

          <section>
            <h3 className="mb-2 text-sm font-medium text-zinc-400">
              Today&apos;s Executions
            </h3>
            <TradesTable trades={trades} />
          </section>
        </>
      )}
    </div>
  )
}
