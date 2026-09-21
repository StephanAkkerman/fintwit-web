import { describe, expect, it } from 'vitest'
import {
  displayLabel,
  effectiveTickerScore,
  emojiForLabel,
  labelFromScore,
  sentimentBadgeClass,
} from '../utils/sentiment'

describe('labelFromScore', () => {
  it('labels scores above the threshold as bullish', () => {
    expect(labelFromScore(0.11)).toBe('BULLISH')
    expect(labelFromScore(0.97)).toBe('BULLISH')
  })

  it('labels scores below the negative threshold as bearish', () => {
    expect(labelFromScore(-0.11)).toBe('BEARISH')
    expect(labelFromScore(-0.97)).toBe('BEARISH')
  })

  it('labels scores at or inside the threshold as neutral', () => {
    expect(labelFromScore(0.1)).toBe('NEUTRAL')
    expect(labelFromScore(-0.1)).toBe('NEUTRAL')
    expect(labelFromScore(0)).toBe('NEUTRAL')
  })
})

describe('emojiForLabel', () => {
  it('maps each label to its emoji', () => {
    expect(emojiForLabel('BULLISH')).toBe('🐂')
    expect(emojiForLabel('BEARISH')).toBe('🐻')
    expect(emojiForLabel('NEUTRAL')).toBe('🦆')
  })
})

describe('sentimentBadgeClass', () => {
  it('maps each known label to its pill color classes', () => {
    expect(sentimentBadgeClass('BULLISH')).toContain('emerald')
    expect(sentimentBadgeClass('BEARISH')).toContain('rose')
    expect(sentimentBadgeClass('NEUTRAL')).toContain('zinc')
  })

  it('falls back to the neutral classes for unrecognized or missing labels', () => {
    expect(sentimentBadgeClass('weird-value')).toContain('zinc')
    expect(sentimentBadgeClass(null)).toContain('zinc')
    expect(sentimentBadgeClass(undefined)).toContain('zinc')
  })
})

describe('displayLabel', () => {
  it('title-cases a sentiment label for display', () => {
    expect(displayLabel('BULLISH')).toBe('Bullish')
    expect(displayLabel('BEARISH')).toBe('Bearish')
    expect(displayLabel('NEUTRAL')).toBe('Neutral')
  })
})

describe('effectiveTickerScore', () => {
  it('uses the ticker override when present', () => {
    expect(effectiveTickerScore(0.6, { INTC: -0.85 }, 'INTC')).toBe(-0.85)
  })

  it('falls back to the overall score when the ticker has no override', () => {
    expect(effectiveTickerScore(0.6, { INTC: -0.85 }, 'NVDA')).toBe(0.6)
  })

  it('falls back to the overall score when ticker_sentiment is absent entirely', () => {
    expect(effectiveTickerScore(0.6, null, 'NVDA')).toBe(0.6)
    expect(effectiveTickerScore(0.6, undefined, 'NVDA')).toBe(0.6)
  })

  it('defaults to 0 when neither an override nor an overall score exists', () => {
    expect(effectiveTickerScore(null, null, 'NVDA')).toBe(0)
    expect(effectiveTickerScore(undefined, undefined, 'NVDA')).toBe(0)
  })

  it('matches the override case-insensitively against the symbol', () => {
    expect(effectiveTickerScore(0.6, { INTC: -0.85 }, 'intc')).toBe(-0.85)
  })
})
