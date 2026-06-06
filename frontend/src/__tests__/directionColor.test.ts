import { describe, expect, it } from 'vitest'
import { classifyDirection, directionTextClass } from '../utils/directionColor'

describe('classifyDirection', () => {
  it('classifies bullish-leaning verdicts', () => {
    expect(classifyDirection('Bullish')).toBe('bullish')
    expect(classifyDirection('Buy')).toBe('bullish')
    expect(classifyDirection('Strong Buy')).toBe('bullish')
    expect(classifyDirection('up')).toBe('bullish')
  })

  it('classifies bearish-leaning verdicts', () => {
    expect(classifyDirection('Bearish')).toBe('bearish')
    expect(classifyDirection('Sell')).toBe('bearish')
    expect(classifyDirection('Strong Sell')).toBe('bearish')
    expect(classifyDirection('down')).toBe('bearish')
  })

  it('falls back to neutral for unknown or empty input', () => {
    expect(classifyDirection('Neutral')).toBe('neutral')
    expect(classifyDirection('')).toBe('neutral')
    expect(classifyDirection(null)).toBe('neutral')
    expect(classifyDirection(undefined)).toBe('neutral')
  })
})

describe('directionTextClass', () => {
  it('maps direction to green/red/grey text classes', () => {
    expect(directionTextClass('Bullish')).toContain('emerald')
    expect(directionTextClass('Sell')).toContain('rose')
    expect(directionTextClass('Neutral')).toContain('zinc')
  })
})
