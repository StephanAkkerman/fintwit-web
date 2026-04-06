import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import RedditWsbWidget from '../components/RedditWsbWidget'

let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  fetchMock = vi.fn(() =>
    Promise.resolve(
      {
        ok: true,
        json: async () => [
          {
            id: 'abc123',
            subreddit: 'wallstreetbets',
            title: 'Big bet on $AAPL',
            description: 'discussion',
            author: 'wsb_user',
            score: 123,
            num_comments: 45,
            created_utc: Math.floor(Date.now() / 1000) - 3600,
            url: 'https://www.reddit.com/r/wallstreetbets/comments/abc123',
            image_urls: [],
          },
        ],
      } as Response
    )
  )
  vi.stubGlobal('fetch', fetchMock)
})

describe('RedditWsbWidget', () => {
  it('renders heading and fetched post rows', async () => {
    render(<RedditWsbWidget />)

    expect(screen.getByText(/wallstreetbets radar/i)).toBeInTheDocument()

    await waitFor(() => {
      expect(screen.getByRole('link', { name: /big bet on \$aapl/i })).toBeInTheDocument()
    })

    expect(screen.getByText(/123 upvotes/i)).toBeInTheDocument()
    expect(screen.getByText(/45 comments/i)).toBeInTheDocument()
  })
})
