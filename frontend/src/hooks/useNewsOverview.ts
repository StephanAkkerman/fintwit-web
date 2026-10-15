import { useEffect, useState } from 'react'
import type { NewsOverviewResponse } from '../types'
import { EMPTY_NEWS_SENTIMENT } from './useCompanyNews'

export const EMPTY_NEWS_OVERVIEW: NewsOverviewResponse = {
  symbols: [],
  top_stories: [],
  themes: [],
  articles: [],
  sentiment: EMPTY_NEWS_SENTIMENT,
  generated_at: '',
  source: 'yfinance',
}

function normalizePayload(payload: unknown): NewsOverviewResponse {
  if (!payload || typeof payload !== 'object') return EMPTY_NEWS_OVERVIEW
  const candidate = payload as Partial<NewsOverviewResponse>
  return {
    symbols: Array.isArray(candidate.symbols) ? candidate.symbols : [],
    top_stories: Array.isArray(candidate.top_stories) ? candidate.top_stories : [],
    themes: Array.isArray(candidate.themes) ? candidate.themes : [],
    articles: Array.isArray(candidate.articles) ? candidate.articles : [],
    sentiment:
      candidate.sentiment && typeof candidate.sentiment === 'object'
        ? { ...EMPTY_NEWS_SENTIMENT, ...candidate.sentiment }
        : EMPTY_NEWS_SENTIMENT,
    generated_at: String(candidate.generated_at ?? ''),
    source: String(candidate.source ?? 'yfinance'),
  }
}

export function useNewsOverview() {
  const [data, setData] = useState<NewsOverviewResponse>(EMPTY_NEWS_OVERVIEW)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/news/overview', { signal: controller.signal })
      .then((res) => {
        if (!res.ok) throw new Error('Failed to fetch news overview')
        return res.json()
      })
      .then((payload) => setData(normalizePayload(payload)))
      .catch((err) => {
        if (err.name === 'AbortError') return
        setError(true)
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [])

  return { data, loading, error }
}
