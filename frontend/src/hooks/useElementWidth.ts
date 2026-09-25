import { useEffect, useRef, useState } from 'react'

/**
 * Track an element's content width so SVG charts can lay out in real pixels
 * (text stays 11px instead of scaling with a viewBox). Falls back to
 * `fallback` until measured, and in environments without layout (jsdom).
 */
export function useElementWidth<T extends HTMLElement>(fallback = 600) {
  const ref = useRef<T>(null)
  const [width, setWidth] = useState(fallback)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const measure = () => { if (el.clientWidth > 0) setWidth(el.clientWidth) }
    measure()
    if (typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(measure)
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  return [ref, width] as const
}
