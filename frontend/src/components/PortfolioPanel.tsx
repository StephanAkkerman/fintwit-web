import { FormEvent, useMemo, useState } from 'react'
import { usePortfolio } from '../hooks/usePortfolio'
import type { PortfolioPosition, PortfolioSummaryPosition } from '../types'

function money(value: number): string {
  return `$${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

export default function PortfolioPanel() {
  const { positions, summary, loading, error, addPosition, toggleActive, removePosition } = usePortfolio()

  const [symbol, setSymbol] = useState('')
  const [quantity, setQuantity] = useState('')
  const [avgCost, setAvgCost] = useState('')
  const [notes, setNotes] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  const summaryById = useMemo(() => {
    const map = new Map<number, PortfolioSummaryPosition>()
    for (const item of summary?.positions ?? []) {
      map.set(item.id, item)
    }
    return map
  }, [summary])

  const onSubmit = async (ev: FormEvent<HTMLFormElement>) => {
    ev.preventDefault()
    setActionError(null)

    const qty = Number(quantity)
    const cost = Number(avgCost)

    if (!symbol.trim() || !Number.isFinite(qty) || qty <= 0 || !Number.isFinite(cost) || cost < 0) {
      setActionError('Enter a valid symbol, quantity, and average cost.')
      return
    }

    setSubmitting(true)
    try {
      await addPosition({
        symbol: symbol.trim().toUpperCase(),
        quantity: qty,
        avg_cost: cost,
        notes: notes.trim() || undefined,
      })
      setSymbol('')
      setQuantity('')
      setAvgCost('')
      setNotes('')
    } catch (e) {
      setActionError(e instanceof Error ? e.message : 'Could not add position')
    } finally {
      setSubmitting(false)
    }
  }

  const handleToggle = async (p: PortfolioPosition) => {
    setActionError(null)
    try {
      await toggleActive(p)
    } catch (e) {
      setActionError(e instanceof Error ? e.message : 'Could not update position')
    }
  }

  const handleDelete = async (positionId: number) => {
    setActionError(null)
    try {
      await removePosition(positionId)
    } catch (e) {
      setActionError(e instanceof Error ? e.message : 'Could not delete position')
    }
  }

  return (
    <section className="rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-500">IBKR Portfolio</h2>
        <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[11px] font-semibold text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
          Stocks only
        </span>
      </div>

      <form className="grid gap-2 md:grid-cols-[1fr_110px_130px_1fr_auto]" onSubmit={onSubmit}>
        <input
          value={symbol}
          onChange={(ev) => setSymbol(ev.target.value)}
          placeholder="Symbol (AAPL)"
          aria-label="Portfolio symbol"
          className="rounded-lg border border-zinc-300 bg-white px-2.5 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900"
        />
        <input
          value={quantity}
          onChange={(ev) => setQuantity(ev.target.value)}
          placeholder="Qty"
          aria-label="Portfolio quantity"
          className="rounded-lg border border-zinc-300 bg-white px-2.5 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900"
        />
        <input
          value={avgCost}
          onChange={(ev) => setAvgCost(ev.target.value)}
          placeholder="Avg cost"
          aria-label="Portfolio average cost"
          className="rounded-lg border border-zinc-300 bg-white px-2.5 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900"
        />
        <input
          value={notes}
          onChange={(ev) => setNotes(ev.target.value)}
          placeholder="Notes (optional)"
          aria-label="Portfolio notes"
          className="rounded-lg border border-zinc-300 bg-white px-2.5 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900"
        />
        <button
          type="submit"
          disabled={submitting}
          className="rounded-lg bg-zinc-900 px-3 py-1.5 text-xs font-semibold text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
        >
          {submitting ? 'Adding...' : 'Add'}
        </button>
      </form>

      {actionError && <p className="mt-2 text-xs text-red-500">{actionError}</p>}

      {summary?.totals && (
        <div className="mt-3 grid gap-2 sm:grid-cols-3">
          <div className="rounded-lg border border-zinc-200 bg-zinc-50 p-2 dark:border-zinc-700 dark:bg-zinc-900/50">
            <div className="text-[11px] text-zinc-500">Market Value</div>
            <div className="text-sm font-semibold">{money(summary.totals.market_value)}</div>
          </div>
          <div className="rounded-lg border border-zinc-200 bg-zinc-50 p-2 dark:border-zinc-700 dark:bg-zinc-900/50">
            <div className="text-[11px] text-zinc-500">Cost Basis</div>
            <div className="text-sm font-semibold">{money(summary.totals.cost_basis)}</div>
          </div>
          <div className="rounded-lg border border-zinc-200 bg-zinc-50 p-2 dark:border-zinc-700 dark:bg-zinc-900/50">
            <div className="text-[11px] text-zinc-500">Unrealized PnL</div>
            <div className={`text-sm font-semibold ${summary.totals.unrealized_pnl >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}`}>
              {money(summary.totals.unrealized_pnl)} ({summary.totals.unrealized_pnl_percent.toFixed(2)}%)
            </div>
          </div>
        </div>
      )}

      {loading ? (
        <div className="mt-3 h-24 animate-pulse rounded-lg bg-zinc-100 dark:bg-zinc-800" />
      ) : error ? (
        <p className="mt-3 text-sm text-red-500">{error}</p>
      ) : positions.length === 0 ? (
        <p className="mt-3 text-sm text-zinc-500">No portfolio positions yet.</p>
      ) : (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-left text-xs sm:text-sm">
            <thead className="border-b border-zinc-200 text-zinc-500 dark:border-zinc-800">
              <tr>
                <th className="py-2">Symbol</th>
                <th className="py-2 text-right">Qty</th>
                <th className="py-2 text-right">Avg Cost</th>
                <th className="py-2 text-right">Price</th>
                <th className="py-2 text-right">PnL</th>
                <th className="py-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((position) => {
                const live = summaryById.get(position.id)
                const pnl = live?.unrealized_pnl ?? 0
                const price = live?.market_price
                return (
                  <tr key={position.id} className="border-b border-zinc-100 dark:border-zinc-900/80">
                    <td className="py-2 font-semibold">{position.symbol}</td>
                    <td className="py-2 text-right font-mono">{position.quantity}</td>
                    <td className="py-2 text-right font-mono">{money(position.avg_cost)}</td>
                    <td className="py-2 text-right font-mono">
                      {typeof price === 'number' ? money(price) : 'N/A'}
                    </td>
                    <td className={`py-2 text-right font-mono ${pnl >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}`}>
                      {live ? `${money(pnl)} (${live.unrealized_pnl_percent.toFixed(2)}%)` : 'N/A'}
                    </td>
                    <td className="py-2 text-right">
                      <div className="inline-flex gap-1">
                        <button
                          type="button"
                          onClick={() => void handleToggle(position)}
                          className="rounded-md border border-zinc-300 px-2 py-1 text-[11px] dark:border-zinc-700"
                        >
                          {position.is_active ? 'Close' : 'Reopen'}
                        </button>
                        <button
                          type="button"
                          onClick={() => void handleDelete(position.id)}
                          className="rounded-md border border-rose-300 px-2 py-1 text-[11px] text-rose-600 dark:border-rose-700 dark:text-rose-400"
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
