import { useEffect, useState } from 'react'
import type { CompanyNewsResponse, CompanyNewsSentimentSummary } from '../types'

export const EMPTY_NEWS_SENTIMENT: CompanyNewsSentimentSummary = {
  analyzed: 0,
  bullish: 0,
  neutral: 0,
  bearish: 0,
  mean_score: null,
  label: null,
}

const EMPTY_NEWS: CompanyNewsResponse = {
  articles: [],
  sentiment: EMPTY_NEWS_SENTIMENT,
  source: 'yfinance',
}

function normalizePayload(payload: unknown): CompanyNewsResponse {
  if (!payload || typeof payload !== 'object') return EMPTY_NEWS

  const candidate = payload as Partial<CompanyNewsResponse>
  if (!Array.isArray(candidate.articles)) return EMPTY_NEWS

  return {
    articles: candidate.articles,
    // Older backends (and a model-less install) send no summary.
    sentiment:
      candidate.sentiment && typeof candidate.sentiment === 'object'
        ? { ...EMPTY_NEWS_SENTIMENT, ...candidate.sentiment }
        : EMPTY_NEWS_SENTIMENT,
    source: String(candidate.source ?? 'yfinance'),
  }
}

export function useCompanyNews(symbol: string, limit = 10) {
  const [data, setData] = useState<CompanyNewsResponse>(EMPTY_NEWS)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    const trimmed = symbol.trim()
    if (!trimmed) {
      setData(EMPTY_NEWS)
      setLoading(false)
      setError(false)
      return
    }

    const controller = new AbortController()
    setLoading(true)
    setError(false)

    const params = new URLSearchParams({ symbols: trimmed, limit: String(limit) })

    fetch(`/api/news/company?${params.toString()}`, { signal: controller.signal })
      .then((res) => {
        if (!res.ok) throw new Error('Failed to fetch company news')
        return res.json()
      })
      .then((payload) => {
        setData(normalizePayload(payload))
      })
      .catch((err) => {
        if (err.name === 'AbortError') return
        setError(true)
      })
      .finally(() => setLoading(false))

    return () => controller.abort()
  }, [symbol, limit])

  return { data, loading, error }
}
