import { useEffect, useState } from 'react'
import type { StocktwitsItem, StocktwitsKeyword } from '../types'

export function useStocktwits(keyword: StocktwitsKeyword = 'ts') {
  const [data, setData] = useState<StocktwitsItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    const controller = new AbortController()

    setLoading(true)
    setError(false)

    fetch(`/api/stocktwits?keyword=${keyword}`, { signal: controller.signal })
      .then((res) => {
        if (!res.ok) throw new Error('Failed to fetch StockTwits data')
        return res.json()
      })
      .then((payload) => {
        setData(Array.isArray(payload) ? payload : [])
      })
      .catch((err) => {
        if (err.name === 'AbortError') return
        setError(true)
      })
      .finally(() => setLoading(false))

    return () => controller.abort()
  }, [keyword])

  return { data, loading, error }
}
