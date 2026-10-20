import { StrictMode, createElement, type ReactNode } from 'react'
import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useMentionHeat } from '../hooks/useMentionHeat'

// A fetch that never answers on its own, but rejects like the browser does
// when its request is aborted.
function pendingFetch() {
  return vi.fn((_input: string | URL | Request, init?: RequestInit) =>
    new Promise<Response>((_resolve, reject) => {
      init?.signal?.addEventListener('abort', () =>
        reject(new DOMException('aborted', 'AbortError')),
      )
    }),
  )
}

describe('useMentionHeat', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('keeps loading while the live request is pending after an aborted one', async () => {
    const fetchMock = pendingFetch()
    vi.stubGlobal('fetch', fetchMock)

    // StrictMode mounts, aborts and re-runs the effect, like `npm run dev`.
    const wrapper = ({ children }: { children: ReactNode }) => createElement(StrictMode, null, children)
    const { result } = renderHook(() => useMentionHeat('all'), { wrapper })

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    await new Promise((r) => setTimeout(r, 0))
    expect(result.current.loading).toBe(true)
    expect(result.current.error).toBe(false)
  })
})
