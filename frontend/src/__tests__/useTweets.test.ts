import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useTweets } from '../hooks/useTweets'
import type { Tweet } from '../types'

const makeTweet = (id: number): Tweet => ({
  id,
  text: `Tweet ${id}`,
  user_name: 'User',
  user_screen_name: 'user',
  user_img: '',
  url: `https://x.com/user/status/${id}`,
  media: [],
  tickers: [],
  hashtags: [],
  title: '',
  media_types: [],
})

// Minimal EventSource mock
class MockEventSource {
  static instances: MockEventSource[] = []
  onmessage: ((ev: MessageEvent) => void) | null = null
  onerror: (() => void) | null = null
  close = vi.fn()

  constructor(public url: string, _init?: EventSourceInit) {
    MockEventSource.instances.push(this)
  }

  emit(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) } as MessageEvent)
  }
}

describe('useTweets', () => {
  beforeEach(() => {
    MockEventSource.instances = []
    vi.stubGlobal('EventSource', MockEventSource)
    vi.stubGlobal('fetch', vi.fn())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('loads initial tweets from /api/posts', async () => {
    const initialData = [makeTweet(1), makeTweet(2)]
    vi.mocked(fetch).mockResolvedValueOnce({
      json: async () => initialData,
    } as Response)

    const { result } = renderHook(() => useTweets(''))

    await waitFor(() => expect(result.current.tweets).toHaveLength(2))
    expect(fetch).toHaveBeenCalledWith('/api/posts?limit=200&since_hours=24', { credentials: 'include' })
    expect(result.current.tweets[0].id).toBe(1)
    expect(result.current.tweets[1].id).toBe(2)
  })

  it('uses selected lookback window and reloads when it changes', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ json: async () => [makeTweet(1)] } as Response)
      .mockResolvedValueOnce({ json: async () => [makeTweet(2)] } as Response)

    const { result, rerender } = renderHook(
      ({ hours }) => useTweets('', 2000, 200, false, hours),
      { initialProps: { hours: 48 as number | null } }
    )

    await waitFor(() => expect(result.current.tweets[0]?.id).toBe(1))
    expect(fetch).toHaveBeenNthCalledWith(1, '/api/posts?limit=200&since_hours=48', {
      credentials: 'include',
    })

    rerender({ hours: 168 })

    await waitFor(() => expect(result.current.tweets[0]?.id).toBe(2))
    expect(fetch).toHaveBeenNthCalledWith(2, '/api/posts?limit=200&since_hours=168', {
      credentials: 'include',
    })
  })

  it('loads older tweets using before_id pagination', async () => {
    const initialData = [makeTweet(5), makeTweet(4)]
    const olderData = [makeTweet(3), makeTweet(2)]
    vi.mocked(fetch)
      .mockResolvedValueOnce({ json: async () => initialData } as Response)
      .mockResolvedValueOnce({ json: async () => olderData } as Response)

    const { result } = renderHook(() => useTweets('', 2000, 2))
    await waitFor(() => expect(result.current.tweets).toHaveLength(2))

    await act(async () => {
      await result.current.loadOlder()
    })

    await waitFor(() => expect(result.current.tweets).toHaveLength(4))
    expect(fetch).toHaveBeenNthCalledWith(2, '/api/posts?limit=2&before_id=4&since_hours=24', {
      credentials: 'include',
    })
    expect(result.current.tweets.map((t) => t.id)).toEqual([5, 4, 3, 2])
  })

  it('prepends new tweet received via SSE', async () => {
    const initialData = [makeTweet(1)]
    vi.mocked(fetch).mockResolvedValueOnce({
      json: async () => initialData,
    } as Response)

    const { result } = renderHook(() => useTweets(''))
    await waitFor(() => expect(result.current.tweets).toHaveLength(1))

    const [es] = MockEventSource.instances
    act(() => {
      es.emit(makeTweet(2))
    })

    await waitFor(() => expect(result.current.tweets).toHaveLength(2))
    expect(result.current.tweets[0].id).toBe(2)
  })

  it('deduplicates tweets with the same id', async () => {
    const initialData = [makeTweet(1)]
    vi.mocked(fetch).mockResolvedValueOnce({
      json: async () => initialData,
    } as Response)

    const { result } = renderHook(() => useTweets(''))
    await waitFor(() => expect(result.current.tweets).toHaveLength(1))

    const [es] = MockEventSource.instances
    act(() => {
      es.emit({ ...makeTweet(1), text: 'Updated Tweet 1' }) // duplicate ID update
    })

    // Still only one tweet, but with refreshed content
    expect(result.current.tweets).toHaveLength(1)
    expect(result.current.tweets[0].text).toBe('Updated Tweet 1')
  })

  it('caps the list at maxItems', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      json: async () => [],
    } as Response)

    const { result } = renderHook(() => useTweets('', 3))
    await waitFor(() => expect(result.current.tweets).toHaveLength(0))

    const [es] = MockEventSource.instances
    act(() => {
      es.emit(makeTweet(1))
      es.emit(makeTweet(2))
      es.emit(makeTweet(3))
      es.emit(makeTweet(4))
    })

    await waitFor(() => expect(result.current.tweets.length).toBeLessThanOrEqual(3))
  })

  it('closes the EventSource on unmount', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      json: async () => [],
    } as Response)

    const { unmount } = renderHook(() => useTweets(''))
    await waitFor(() => MockEventSource.instances.length > 0)

    unmount()
    expect(MockEventSource.instances[0].close).toHaveBeenCalled()
  })

  it('uses options-only feed params when optionsOnly is enabled', async () => {
    const initialData = [makeTweet(10)]
    const olderData = [makeTweet(9)]
    vi.mocked(fetch)
      .mockResolvedValueOnce({ json: async () => initialData } as Response)
      .mockResolvedValueOnce({ json: async () => olderData } as Response)

    const { result } = renderHook(() => useTweets('', 2000, 1, true))

    await waitFor(() => expect(result.current.tweets).toHaveLength(1))
    expect(fetch).toHaveBeenNthCalledWith(1, '/api/posts?limit=1&since_hours=24&options_only=true', {
      credentials: 'include',
    })
    expect(MockEventSource.instances[0].url).toBe('/api/stream?options_only=true')

    await act(async () => {
      await result.current.loadOlder()
    })

    expect(fetch).toHaveBeenNthCalledWith(
      2,
      '/api/posts?limit=1&before_id=10&since_hours=24&options_only=true',
      {
        credentials: 'include',
      }
    )
  })
})
