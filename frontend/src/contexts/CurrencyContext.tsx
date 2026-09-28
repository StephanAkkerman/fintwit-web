import { createContext, useContext, useMemo, useState, type ReactNode } from 'react'
import { useFxRates } from '../hooks/useFxRates'
import { formatCurrency, type CurrencyCode } from '../utils/currency'

type CurrencyContextValue = {
  currency: CurrencyCode
  setCurrency: (currency: CurrencyCode) => void
  rates: Record<string, number>
  ratesLoading: boolean
  /** Formats a USD-denominated value in the currently selected currency. */
  format: (valueUsd: number | null | undefined, options?: Intl.NumberFormatOptions) => string
}

const CurrencyContext = createContext<CurrencyContextValue>({
  currency: 'USD',
  setCurrency: () => {},
  rates: {},
  ratesLoading: false,
  format: (valueUsd, options) => formatCurrency(valueUsd, 'USD', {}, options),
})

export function CurrencyProvider({ children }: { children: ReactNode }) {
  const [currency, setCurrency] = useState<CurrencyCode>('USD')
  const { fxRates, loading } = useFxRates()

  const value = useMemo<CurrencyContextValue>(() => {
    const rates = fxRates?.rates ?? {}
    return {
      currency,
      setCurrency,
      rates,
      ratesLoading: loading,
      format: (valueUsd, options) => formatCurrency(valueUsd, currency, rates, options),
    }
  }, [currency, fxRates, loading])

  return <CurrencyContext.Provider value={value}>{children}</CurrencyContext.Provider>
}

export function useCurrency() {
  return useContext(CurrencyContext)
}
