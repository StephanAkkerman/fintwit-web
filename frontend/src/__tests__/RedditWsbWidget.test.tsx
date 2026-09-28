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

  it('shows a preview, a description excerpt and the flair instead of a title prefix', async () => {
    fetchMock.mockImplementation(() =>
      Promise.resolve({
        ok: true,
        json: async () => [
          {
            id: 'img1',
            subreddit: 'wallstreetbets',
            title: 'My loss porn',
            description: 'Bought **weeklies** on [NVDA](https://example.com) and it went badly',
            author: 'u1',
            score: 5,
            num_comments: 1,
            created_utc: Math.floor(Date.now() / 1000) - 60,
            url: 'https://www.reddit.com/r/wallstreetbets/comments/img1',
            image_urls: ['https://i.redd.it/loss.jpeg'],
            media_type: 'image',
            flair: 'Loss',
            upvote_ratio: 0.93,
          },
          {
            id: 'link1',
            subreddit: 'wallstreetbets',
            title: 'Fed holds rates',
            description: '',
            author: 'u2',
            score: 50,
            num_comments: 10,
            created_utc: Math.floor(Date.now() / 1000) - 120,
            url: 'https://www.reddit.com/r/wallstreetbets/comments/link1',
            image_urls: [],
            media_type: 'link',
            link_url: 'https://www.reuters.com/markets/fed',
          },
        ],
      } as Response)
    )

    const { container } = render(<RedditWsbWidget />)

    expect(await screen.findByRole('link', { name: 'My loss porn' })).toBeInTheDocument()
    expect(screen.getByText('Bought weeklies on NVDA and it went badly')).toBeInTheDocument()
    expect(screen.getByText('Loss')).toBeInTheDocument()
    expect(screen.getByText('93% upvoted')).toBeInTheDocument()
    expect(container.querySelector('img')?.getAttribute('src')).toBe('https://i.redd.it/loss.jpeg')
    expect(screen.getByRole('link', { name: 'reuters.com' })).toHaveAttribute(
      'href',
      'https://www.reuters.com/markets/fed'
    )
  })

  it('renders every requested post', async () => {
    const post = (i: number) => ({
      id: `p${i}`,
      subreddit: 'stocks',
      title: `Post ${i}`,
      description: '',
      author: 'a',
      score: 1,
      num_comments: 0,
      created_utc: Math.floor(Date.now() / 1000),
      url: `https://www.reddit.com/r/stocks/comments/p${i}`,
      image_urls: [],
    })
    fetchMock.mockImplementation(() =>
      Promise.resolve({
        ok: true,
        json: async () => Array.from({ length: 10 }, (_, i) => post(i)),
      } as Response)
    )

    render(<RedditWsbWidget subreddit="stocks" limit={10} />)

    await waitFor(() => expect(screen.getAllByRole('article')).toHaveLength(10))
  })
})
