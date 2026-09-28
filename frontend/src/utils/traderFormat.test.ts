import { describe, expect, it } from 'vitest'
import { signedReturn, traderFromPath } from './traderFormat'

describe('signedReturn', () => {
  it('keeps a bullish return as-is', () => {
    expect(signedReturn('bullish', 5)).toBe(5)
  })

  it('flips a bearish return so a falling price reads as a gain', () => {
    expect(signedReturn('bearish', -8)).toBe(8)
  })
})

describe('traderFromPath', () => {
  it('is null for the bare leaderboard route', () => {
    expect(traderFromPath('/traders')).toBeNull()
    expect(traderFromPath('/traders/')).toBeNull()
  })

  it('reads the handle from a deep link', () => {
    expect(traderFromPath('/traders/finguru')).toBe('finguru')
    expect(traderFromPath('/traders/@finguru/')).toBe('finguru')
  })

  it('ignores other routes and nested paths', () => {
    expect(traderFromPath('/stocks/finguru')).toBeNull()
    expect(traderFromPath('/traders/finguru/calls')).toBeNull()
  })
})
