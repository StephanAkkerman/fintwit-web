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
    expect(result.current.tweets[0].id).toBe(1)
    expect(result.current.tweets[1].id).toBe(2)
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
})
