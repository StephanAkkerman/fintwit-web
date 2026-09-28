import { describe, expect, it } from 'vitest'
import { convertFromUsd, formatCurrency, isSupportedCurrency } from '../utils/currency'

describe('convertFromUsd', () => {
  it('returns the USD value unchanged when currency is USD', () => {
    expect(convertFromUsd(100, 'USD', { EUR: 0.92 })).toBe(100)
  })

  it('multiplies by the USD -> currency rate', () => {
    expect(convertFromUsd(100, 'EUR', { EUR: 0.92 })).toBeCloseTo(92)
  })

  it('falls back to the raw USD value when no rate is available', () => {
    expect(convertFromUsd(100, 'EUR', {})).toBe(100)
  })
})

describe('formatCurrency', () => {
  it('formats a missing value as an em dash', () => {
    expect(formatCurrency(null, 'USD', {})).toBe('—')
    expect(formatCurrency(undefined, 'USD', {})).toBe('—')
    expect(formatCurrency(NaN, 'USD', {})).toBe('—')
  })

  it('formats using the selected currency symbol', () => {
    expect(formatCurrency(100, 'USD', {})).toBe('$100.00')
    expect(formatCurrency(100, 'EUR', { EUR: 0.5 })).toBe('€50.00')
  })
})

describe('isSupportedCurrency', () => {
  it('accepts known currency codes', () => {
    expect(isSupportedCurrency('EUR')).toBe(true)
    expect(isSupportedCurrency('USD')).toBe(true)
  })

  it('rejects unknown values', () => {
    expect(isSupportedCurrency('XYZ')).toBe(false)
    expect(isSupportedCurrency(null)).toBe(false)
    expect(isSupportedCurrency(undefined)).toBe(false)
  })
})
