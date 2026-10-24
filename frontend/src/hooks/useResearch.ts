import { useEffect, useState } from 'react'
import type { AnalystActivity, DarkPool, OptionsFlow, TrendStage } from '../types'

type JsonState<T> = {
  data: T | null
  loading: boolean
  error: boolean
  /** The backend answered 404: there is no such data for this symbol (a
   * fund has no analysts, a new listing no 30-week average). */
  missing: boolean
}

/** Fetch one JSON view; `url` null means "not yet" (nothing is requested).
 * A payload `isValid` rejects counts as an error rather than reaching a
 * component that would read fields off it. */
function useJson<T>(url: string | null, isValid: (payload: unknown) => boolean): JsonState<T> {
  const [state, setState] = useState<JsonState<T>>({
    data: null,
    loading: url !== null,
    error: false,
    missing: false,
  })

  useEffect(() => {
    if (url === null) {
      setState({ data: null, loading: false, error: false, missing: false })
      return
    }
    const controller = new AbortController()
    setState({ data: null, loading: true, error: false, missing: false })
    fetch(url, { signal: controller.signal })
      .then(async (res) => {
        if (res.status === 404) {
          setState({ data: null, loading: false, error: false, missing: true })
          return
        }
        if (!res.ok) throw new Error(url)
        const payload: unknown = await res.json()
        if (!isValid(payload)) throw new Error(url)
        setState({ data: payload as T, loading: false, error: false, missing: false })
      })
      .catch((err) => {
        if (err instanceof Error && err.name === 'AbortError') return
        setState({ data: null, loading: false, error: true, missing: false })
      })
    return () => controller.abort()
  }, [url, isValid])

  return state
}

function hasKey(key: string) {
  return (payload: unknown) =>
    typeof payload === 'object' && payload !== null && !Array.isArray(payload) && key in payload
}

const isTrendStage = hasKey('stage')
const isAnalystActivity = hasKey('rating_changes')
const isOptionsFlow = hasKey('top_scored')
const isDarkPool = hasKey('prints')

function symbolUrl(path: string, symbol: string | null, enabled = true): string | null {
  if (!symbol || !enabled) return null
  return `${path}?${new URLSearchParams({ symbol: symbol.toUpperCase() })}`
}

/** Weekly Weinstein stage and relative strength against SPY and the sector. */
export function useTrendStage(symbol: string | null) {
  return useJson<TrendStage>(symbolUrl('/api/research/trend-stage', symbol), isTrendStage)
}

/** Rating changes, buy/hold/sell mix and EPS estimate revisions. */
export function useAnalystActivity(symbol: string | null) {
  return useJson<AnalystActivity>(symbolUrl('/api/research/analysts', symbol), isAnalystActivity)
}

/**
 * Signa options flow, for one symbol or (symbol null) the whole market.
 * Each request spends Signa's shared daily quota, so per-symbol callers pass
 * `enabled` only once someone asks for it.
 */
export function useOptionsFlow(symbol: string | null, enabled = true) {
  const url = !enabled
    ? null
    : symbol
      ? symbolUrl('/api/signa/options-flow', symbol)
      : '/api/signa/options-flow'
  return useJson<OptionsFlow>(url, isOptionsFlow)
}

/** The latest dark pool prints for one symbol (Signa). */
export function useDarkPool(symbol: string | null, enabled = true) {
  return useJson<DarkPool>(symbolUrl('/api/signa/dark-pool', symbol, enabled), isDarkPool)
}
