export const SUPPORTED_CURRENCIES = ['USD', 'EUR', 'GBP', 'JPY', 'CHF', 'AUD', 'CAD'] as const

export type CurrencyCode = (typeof SUPPORTED_CURRENCIES)[number]

export function isSupportedCurrency(value: string | null | undefined): value is CurrencyCode {
  return SUPPORTED_CURRENCIES.includes(value as CurrencyCode)
}

/** All portfolio figures are stored/fetched in USD; `rates` holds USD -> currency multipliers. */
export function convertFromUsd(
  valueUsd: number,
  currency: CurrencyCode,
  rates: Record<string, number>,
): number {
  if (currency === 'USD') return valueUsd
  const rate = rates[currency]
  return rate ? valueUsd * rate : valueUsd
}

export function formatCurrency(
  valueUsd: number | null | undefined,
  currency: CurrencyCode,
  rates: Record<string, number>,
  options: Intl.NumberFormatOptions = {},
): string {
  if (valueUsd == null || !Number.isFinite(valueUsd)) return '—'
  const converted = convertFromUsd(valueUsd, currency, rates)
  return converted.toLocaleString(undefined, {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
    ...options,
  })
}
