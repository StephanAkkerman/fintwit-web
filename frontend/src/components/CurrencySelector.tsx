import { useCurrency } from '../contexts/CurrencyContext'
import { SUPPORTED_CURRENCIES, isSupportedCurrency } from '../utils/currency'

export default function CurrencySelector() {
  const { currency, setCurrency } = useCurrency()

  return (
    <label className="flex items-center gap-1.5 text-xs text-zinc-500">
      <span className="hidden sm:inline">Currency</span>
      <select
        aria-label="Display currency"
        value={currency}
        onChange={(ev) => {
          const next = ev.target.value
          if (isSupportedCurrency(next)) setCurrency(next)
        }}
        className="rounded-lg border border-zinc-300 bg-white px-2 py-1 text-xs font-semibold text-zinc-700 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200"
      >
        {SUPPORTED_CURRENCIES.map((code) => (
          <option key={code} value={code}>
            {code}
          </option>
        ))}
      </select>
    </label>
  )
}
