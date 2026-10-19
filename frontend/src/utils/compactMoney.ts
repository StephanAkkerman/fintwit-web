/** `1_234_567` -> `$1.2M`; the sign is dropped (callers show direction). */
export function compactMoney(value: number | null | undefined): string {
  if (value == null) return '—'
  return `$${Math.abs(value).toLocaleString(undefined, { notation: 'compact', maximumFractionDigits: 1 })}`
}
