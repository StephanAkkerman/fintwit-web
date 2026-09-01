export type MetricQuality = 'good' | 'neutral' | 'bad'

/**
 * The two breakpoints of a three-band scale.
 *
 * Direction is inferred rather than configured: when `good` is below `bad` the
 * metric reads lower-is-better (a P/E, an expense ratio), and when `good` is
 * above `bad` it reads higher-is-better (a margin, a growth rate). Callers just
 * state the two ends and the ordering carries the meaning.
 */
export type MetricScale = {
  /** Value at or beyond which the metric reads as good. */
  good: number
  /** Value at or beyond which the metric reads as bad. */
  bad: number
}

const METRIC_QUALITY_TEXT_CLASS: Record<MetricQuality, string> = {
  good: 'text-emerald-600 dark:text-emerald-400',
  bad: 'text-rose-600 dark:text-rose-400',
  neutral: 'text-zinc-500 dark:text-zinc-400',
}

/**
 * Place a number on a three-band scale.
 *
 * Anything unusable — a missing value, a non-finite one, or a degenerate scale
 * whose ends coincide — reads `neutral`, so a broken input greys out rather
 * than claiming a verdict it cannot support.
 */
export function scoreMetric(
  value: number | null | undefined,
  scale: MetricScale
): MetricQuality {
  if (typeof value !== 'number' || !Number.isFinite(value)) return 'neutral'

  const { good, bad } = scale
  if (!Number.isFinite(good) || !Number.isFinite(bad) || good === bad) return 'neutral'

  if (good < bad) {
    // Lower is better.
    if (value <= good) return 'good'
    if (value >= bad) return 'bad'
    return 'neutral'
  }

  // Higher is better.
  if (value >= good) return 'good'
  if (value <= bad) return 'bad'
  return 'neutral'
}

/**
 * Tailwind text-color classes (green / red / grey) for a quality band.
 *
 * Deliberately the same palette as `directionTextClass`, so a green number and
 * a green verdict on the same card mean the same thing to the eye.
 */
export function metricQualityTextClass(quality: MetricQuality): string {
  return METRIC_QUALITY_TEXT_CLASS[quality]
}

/** Convenience: score a value and return its color classes in one step. */
export function scoreMetricTextClass(
  value: number | null | undefined,
  scale: MetricScale
): string {
  return metricQualityTextClass(scoreMetric(value, scale))
}
