import { describe, expect, it } from 'vitest'
import {
  metricQualityTextClass,
  scoreMetric,
  scoreMetricTextClass,
  type MetricScale,
} from '../utils/metricQuality'

const LOWER_IS_BETTER: MetricScale = { good: 15, bad: 30 }
const HIGHER_IS_BETTER: MetricScale = { good: 20, bad: 5 }

describe('scoreMetric', () => {
  it('scores a lower-is-better metric', () => {
    expect(scoreMetric(9, LOWER_IS_BETTER)).toBe('good')
    expect(scoreMetric(22, LOWER_IS_BETTER)).toBe('neutral')
    expect(scoreMetric(48, LOWER_IS_BETTER)).toBe('bad')
  })

  it('scores a higher-is-better metric by inferring direction from the scale', () => {
    expect(scoreMetric(31, HIGHER_IS_BETTER)).toBe('good')
    expect(scoreMetric(12, HIGHER_IS_BETTER)).toBe('neutral')
    expect(scoreMetric(2, HIGHER_IS_BETTER)).toBe('bad')
  })

  it('treats the breakpoints themselves as inside the good and bad bands', () => {
    expect(scoreMetric(15, LOWER_IS_BETTER)).toBe('good')
    expect(scoreMetric(30, LOWER_IS_BETTER)).toBe('bad')
    expect(scoreMetric(20, HIGHER_IS_BETTER)).toBe('good')
    expect(scoreMetric(5, HIGHER_IS_BETTER)).toBe('bad')
  })

  it('falls back to neutral for values it cannot judge', () => {
    expect(scoreMetric(null, LOWER_IS_BETTER)).toBe('neutral')
    expect(scoreMetric(undefined, LOWER_IS_BETTER)).toBe('neutral')
    expect(scoreMetric(Number.NaN, LOWER_IS_BETTER)).toBe('neutral')
    expect(scoreMetric(Number.POSITIVE_INFINITY, LOWER_IS_BETTER)).toBe('neutral')
  })

  it('falls back to neutral for a degenerate scale rather than guessing', () => {
    expect(scoreMetric(10, { good: 15, bad: 15 })).toBe('neutral')
    expect(scoreMetric(10, { good: Number.NaN, bad: 30 })).toBe('neutral')
  })

  it('handles negative scales', () => {
    const drawdown: MetricScale = { good: -5, bad: -25 } // higher (shallower) is better
    expect(scoreMetric(-2, drawdown)).toBe('good')
    expect(scoreMetric(-15, drawdown)).toBe('neutral')
    expect(scoreMetric(-40, drawdown)).toBe('bad')
  })
})

describe('metricQualityTextClass', () => {
  it('uses the same green/red/grey palette as directionTextClass', () => {
    expect(metricQualityTextClass('good')).toBe('text-emerald-600 dark:text-emerald-400')
    expect(metricQualityTextClass('bad')).toBe('text-rose-600 dark:text-rose-400')
    expect(metricQualityTextClass('neutral')).toBe('text-zinc-500 dark:text-zinc-400')
  })

  it('scores and maps to classes in one step', () => {
    expect(scoreMetricTextClass(9, LOWER_IS_BETTER)).toBe(
      'text-emerald-600 dark:text-emerald-400'
    )
    expect(scoreMetricTextClass(48, LOWER_IS_BETTER)).toBe('text-rose-600 dark:text-rose-400')
  })
})
