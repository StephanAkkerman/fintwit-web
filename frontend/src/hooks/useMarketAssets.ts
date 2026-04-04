import { useEffect, useState, useRef } from 'react'
import type { Asset, Tweet } from '../types'

export function useMarketAssets(apiBase = '', maxItems = 10) {
  const [assets, setAssets] = useState<Asset[]>([])
  const assetsMap = useRef<Map<string, Asset>>(new Map())

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const r = await fetch(`${apiBase}/api/posts`, { credentials: 'include' })
        if (!r.ok) throw new Error('Network response was not ok')
        const data: Tweet[] = await r.json()
        if (cancelled) return

        const newMap = new Map<string, Asset>()
        // Process oldest to newest so newest overwrites
        ;[...data].reverse().forEach(t => {
          t.assets?.forEach(a => {
            if (a.financials) {
              newMap.delete(a.symbol)
              newMap.set(a.symbol, a)
            }
          })
        })
        assetsMap.current = newMap
        setAssets(Array.from(newMap.values()).reverse().slice(0, maxItems))
      } catch (e) {
        console.error('initial load failed for market assets', e)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [apiBase, maxItems])

  useEffect(() => {
    const es = new EventSource(`${apiBase}/api/stream`, { withCredentials: true })
    es.onmessage = (ev) => {
      try {
        const t: Tweet = JSON.parse(ev.data)
        if (t.assets && t.assets.length > 0) {
          let updated = false
          t.assets.forEach(a => {
            if (a.financials) {
              assetsMap.current.delete(a.symbol)
              assetsMap.current.set(a.symbol, a)
              updated = true
            }
          })

          if (updated) {
            setAssets(Array.from(assetsMap.current.values()).reverse().slice(0, maxItems))
          }
        }
      } catch (e) {
        console.error('error parsing event in useMarketAssets', e)
      }
    }
    es.onerror = () => {}
    return () => es.close()
  }, [apiBase, maxItems])

  return { assets }
}
