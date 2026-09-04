import { useState } from 'react'
import { useOptionsChain } from '../hooks/useOptionsChain'

function fmtNum(value: number | null | undefined, digits = 2): string {
  return value == null || Number.isNaN(value) ? 'N/A' : value.toFixed(digits)
}

function fmtInt(value: number | null | undefined): string {
  return value == null || Number.isNaN(value) ? 'N/A' : value.toLocaleString()
}

export default function OptionsChainWidget() {
  const [symbolInput, setSymbolInput] = useState('AAPL')
  const [symbol, setSymbol] = useState('AAPL')
  const [expiration, setExpiration] = useState<string | undefined>(undefined)
  const { data, loading, error } = useOptionsChain(symbol, expiration)

  const submitSymbol = () => {
    const next = symbolInput.trim().toUpperCase()
    if (!next) return
    setExpiration(undefined)
    setSymbol(next)
  }

  return (
    <div className="rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-500">Options Chain</h2>
        <div className="flex items-center gap-2">
          <input
            value={symbolInput}
            onChange={(e) => setSymbolInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') submitSymbol()
            }}
            placeholder="Symbol"
            className="w-24 rounded-md border border-zinc-300 bg-white px-2 py-1 text-xs uppercase text-zinc-900 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
          />
          <button
            type="button"
            onClick={submitSymbol}
            className="rounded-md bg-zinc-900 px-2.5 py-1 text-xs font-semibold text-white dark:bg-zinc-100 dark:text-zinc-900"
          >
            Load
          </button>
          {data.expirations.length > 0 && (
            <select
              value={data.expiration}
              onChange={(e) => setExpiration(e.target.value)}
              className="rounded-md border border-zinc-300 bg-white px-2 py-1 text-xs text-zinc-900 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
            >
              {data.expirations.map((exp) => (
                <option key={exp} value={exp}>
                  {exp}
                </option>
              ))}
            </select>
          )}
        </div>
      </div>

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-8 animate-pulse rounded bg-zinc-100 dark:bg-zinc-800" />
          ))}
        </div>
      ) : error ? (
        <p className="text-sm text-red-500">Could not load options chain for {symbol}.</p>
      ) : data.contracts.length === 0 ? (
        <p className="text-sm text-zinc-500">No options chain data available for {symbol}.</p>
      ) : (
        <>
          {data.underlying.name && (
            <p className="mb-2 text-xs text-zinc-500">
              {data.underlying.name} &middot; last {fmtNum(data.underlying.last_price)}
              {data.underlying.change_percent != null && (
                <span className={data.underlying.change_percent >= 0 ? 'text-emerald-600' : 'text-rose-600'}>
                  {' '}
                  ({data.underlying.change_percent >= 0 ? '+' : ''}
                  {fmtNum(data.underlying.change_percent, 2)}%)
                </span>
              )}
            </p>
          )}
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs sm:text-sm">
              <thead className="border-b border-zinc-200 text-zinc-500 dark:border-zinc-800">
                <tr>
                  <th className="py-2">Type</th>
                  <th className="py-2 text-right">Strike</th>
                  <th className="py-2 text-right">Bid</th>
                  <th className="py-2 text-right">Ask</th>
                  <th className="py-2 text-right">Last</th>
                  <th className="py-2 text-right">IV</th>
                  <th className="py-2 text-right">Volume</th>
                  <th className="py-2 text-right">OI</th>
                </tr>
              </thead>
              <tbody>
                {data.contracts.map((c, i) => (
                  <tr
                    key={`${c.option_type}-${c.strike}-${i}`}
                    className={`border-b border-zinc-100 dark:border-zinc-900/80 ${
                      c.in_the_money ? 'bg-zinc-50 dark:bg-zinc-800/40' : ''
                    }`}
                  >
                    <td className="py-2">
                      <span
                        className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${
                          c.option_type === 'CALL'
                            ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300'
                            : 'bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-300'
                        }`}
                      >
                        {c.option_type}
                      </span>
                    </td>
                    <td className="py-2 text-right font-mono">{fmtNum(c.strike)}</td>
                    <td className="py-2 text-right font-mono">{fmtNum(c.bid)}</td>
                    <td className="py-2 text-right font-mono">{fmtNum(c.ask)}</td>
                    <td className="py-2 text-right font-mono">{fmtNum(c.last_price)}</td>
                    <td className="py-2 text-right font-mono">
                      {c.implied_volatility == null ? 'N/A' : `${(c.implied_volatility * 100).toFixed(1)}%`}
                    </td>
                    <td className="py-2 text-right font-mono">{fmtInt(c.volume)}</td>
                    <td className="py-2 text-right font-mono text-zinc-500">{fmtInt(c.open_interest)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}
