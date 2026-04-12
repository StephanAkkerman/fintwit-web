import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import TweetCard from '../components/TweetCard'
import type { Tweet } from '../types'

const baseTweet: Tweet = {
  id: 1,
  text: 'Hello world',
  user_name: 'Test User',
  user_screen_name: 'testuser',
  user_img: 'https://example.com/avatar.jpg',
  url: 'https://x.com/testuser/status/1',
  created_at: '',
  media: [],
  tickers: [],
  hashtags: [],
  title: '',
  media_types: [],
  replies: 0,
  likes: 0,
  views: 0,
  retweets: 0,
}

describe('TweetCard', () => {
  it('renders user name and screen name', () => {
    render(<TweetCard t={baseTweet} />)
    expect(screen.getByText('Test User')).toBeInTheDocument()
    expect(screen.getByText('@testuser')).toBeInTheDocument()
  })

  it('renders tweet text', () => {
    render(<TweetCard t={baseTweet} />)
    expect(screen.getByText('Hello world')).toBeInTheDocument()
  })

  it('renders quote-tweet markdown as blockquote with parsed links', () => {
    const quoteText =
      '> [@opensea](https://x.com/opensea/status/1893717105483483558):\n> Treasure Chests from our final Wave are now unlocked.'

    const { container } = render(
      <TweetCard
        t={{
          ...baseTweet,
          text: quoteText,
          quoted_tweet: {
            id: '1893717105483483558',
            text: 'Treasure Chests from our final Wave are now unlocked.',
            user_name: 'OpenSea',
            user_screen_name: 'opensea',
            user_img: 'https://example.com/opensea.jpg',
            url: 'https://x.com/user/status/1893717105483483558',
            media: [],
            tickers: [],
            hashtags: [],
            title: 'OpenSea quote',
            media_types: [],
            created_at: '2026-03-08T18:00:00Z',
            likes: 1,
            retweets: 1,
            replies: 1,
            views: 1,
          },
        }}
      />
    )

    expect(container.querySelector('blockquote')).toBeInTheDocument()
    expect(screen.queryByText('Quoted post')).not.toBeInTheDocument()

    const quoteUserLink = screen.getByLabelText('Quoted tweet author')
    expect(quoteUserLink).toHaveTextContent('OpenSea')
    expect(quoteUserLink).toHaveAttribute('href', 'https://x.com/opensea/status/1893717105483483558')
    expect(screen.queryByRole('link', { name: '@opensea' })).not.toBeInTheDocument()
    const quoteAvatar = screen.getByAltText('Quoted user avatar') as HTMLImageElement
    expect(quoteAvatar.src).toContain('opensea.jpg')

    const quotedTime = screen.getByLabelText('Quoted tweet timestamp')
    expect(quotedTime).toBeInTheDocument()
    expect(quotedTime.getAttribute('datetime')).toBeTruthy()
  })

  it('renders quoted image inside the quote embed', () => {
    const quoteText =
      '> [@opensea](https://twitter.com/opensea):\n> Treasure Chests from our final Wave are now unlocked.'

    render(
      <TweetCard
        t={{
          ...baseTweet,
          text: quoteText,
          media: [
            { url: 'https://example.com/inline.jpg', type: 'photo' },
            { url: 'https://example.com/quoted.jpg', type: 'photo' },
          ],
          quoted_tweet: {
            id: 2,
            text: 'Treasure Chests from our final Wave are now unlocked.',
            user_name: 'OpenSea',
            user_screen_name: 'opensea',
            user_img: 'https://example.com/opensea.jpg',
            url: 'https://x.com/user/status/2',
            media: [{ url: 'https://example.com/quoted.jpg', type: 'photo' }],
            tickers: [],
            hashtags: [],
            title: 'OpenSea quote',
            media_types: ['photo'],
            created_at: '2026-03-08T18:00:00Z',
            likes: 1,
            retweets: 1,
            replies: 1,
            views: 1,
          },
        }}
      />
    )

    const quotedImage = screen.getByAltText('Quoted media') as HTMLImageElement
    expect(quotedImage.src).toContain('quoted.jpg')

    const inlineImage = screen.getByAltText('photo') as HTMLImageElement
    expect(inlineImage.src).toContain('inline.jpg')

    const quoteBlock = quotedImage.closest('blockquote')
    expect(quoteBlock).toBeInTheDocument()
    if (!quoteBlock) {
      throw new Error('Expected quoted media to be inside a blockquote')
    }
    expect(quoteBlock.compareDocumentPosition(inlineImage) & Node.DOCUMENT_POSITION_PRECEDING).toBeTruthy()
  })

  it('renders quote header metadata from quoted_tweet when markdown header is absent', () => {
    const quoteText = '> Quoted body only.'

    render(
      <TweetCard
        t={{
          ...baseTweet,
          text: quoteText,
          quoted_tweet: {
            id: 321,
            text: 'Quoted body only.',
            user_name: 'Macro Analyst',
            user_screen_name: 'macroanalyst',
            user_img: 'https://example.com/macro.jpg',
            url: 'https://x.com/user/status/321',
            media: [],
            tickers: [],
            hashtags: [],
            title: 'Macro quote',
            media_types: [],
            created_at: '2026-04-09T08:15:00Z',
            likes: 0,
            retweets: 0,
            replies: 0,
            views: 0,
          },
        }}
      />
    )

    const quoteUserLink = screen.getByLabelText('Quoted tweet author')
    expect(quoteUserLink).toHaveTextContent('Macro Analyst')
    expect(quoteUserLink).toHaveAttribute('href', 'https://x.com/macroanalyst/status/321')
    expect(screen.getByLabelText('Quoted tweet timestamp')).toBeInTheDocument()
    const quoteAvatar = screen.getByAltText('Quoted user avatar') as HTMLImageElement
    expect(quoteAvatar.src).toContain('macro.jpg')
  })

  it('renders quote avatar from quoted_user_img fallback when quoted_tweet is absent', () => {
    const quoteText = '> [@legacyuser](https://x.com/legacyuser/status/333):\n> Legacy quote payload.'

    render(
      <TweetCard
        t={{
          ...baseTweet,
          text: quoteText,
          quoted_user_name: 'Legacy User',
          quoted_user_screen_name: 'legacyuser',
          quoted_user_img: 'https://example.com/legacy-avatar.jpg',
          quoted_created_at: '2026-04-09T09:00:00Z',
        }}
      />
    )

    const quoteAvatar = screen.getByAltText('Quoted user avatar') as HTMLImageElement
    expect(quoteAvatar.src).toContain('legacy-avatar.jpg')
  })

  it('renders an Open link pointing to the tweet URL', () => {
    render(<TweetCard t={baseTweet} />)
    const link = screen.getByRole('link', { name: /open/i })
    expect(link).toHaveAttribute('href', baseTweet.url)
  })

  it('renders tickers as pill badges', () => {
    render(<TweetCard t={{ ...baseTweet, tickers: ['AAPL', 'TSLA'] }} />)
    expect(screen.getByText('$AAPL')).toBeInTheDocument()
    expect(screen.getByText('$TSLA')).toBeInTheDocument()
  })

  it('renders hashtags as pill badges', () => {
    render(<TweetCard t={{ ...baseTweet, hashtags: ['crypto', 'stocks'] }} />)
    expect(screen.getByText('#CRYPTO')).toBeInTheDocument()
    expect(screen.getByText('#STOCKS')).toBeInTheDocument()
  })

  it('falls back to text parsing for ticker and hashtag badges', () => {
    render(<TweetCard t={{ ...baseTweet, text: 'Watching $aapl and #btc now' }} />)
    expect(screen.getByText('$AAPL')).toBeInTheDocument()
    expect(screen.getByText('#BTC')).toBeInTheDocument()
  })

  it('shows chart badge when has_chart flag is true', () => {
    render(<TweetCard t={{ ...baseTweet, has_chart: true }} />)
    expect(screen.getByLabelText('Chart tweet')).toBeInTheDocument()
  })

  it('does not show chart badge for photo media when has_chart is false', () => {
    render(
      <TweetCard
        t={{
          ...baseTweet,
          has_chart: false,
          media: [{ url: 'https://example.com/chart.jpg', type: 'photo' }],
          media_types: ['photo'],
        }}
      />
    )

    expect(screen.queryByLabelText('Chart tweet')).not.toBeInTheDocument()
  })

  it('renders sentiment badge when sentiment fields are available', () => {
    render(
      <TweetCard
        t={{
          ...baseTweet,
          sentiment_label: 'BULLISH',
          sentiment_emoji: '🐂',
          sentiment_score: 0.97,
        }}
      />
    )

    expect(screen.getByLabelText('Tweet sentiment')).toBeInTheDocument()
    expect(screen.getByText(/bullish/i)).toBeInTheDocument()
  })

  it('renders separate quoted sentiment badge in quote header', () => {
    const quoteText =
      'Bullish update\n\n> [@user](https://twitter.com/user):\n> Bearish prior thesis'

    render(
      <TweetCard
        t={{
          ...baseTweet,
          text: quoteText,
          sentiment_label: 'BULLISH',
          sentiment_emoji: '🐂',
          quoted_sentiment_label: 'BEARISH',
          quoted_sentiment_emoji: '🐻',
        }}
      />
    )

    expect(screen.getByLabelText('Tweet sentiment')).toBeInTheDocument()
    expect(screen.getByLabelText('Quoted tweet sentiment')).toBeInTheDocument()
  })

  it('does not show chart badge for text-only tweets', () => {
    render(<TweetCard t={baseTweet} />)
    expect(screen.queryByLabelText('Chart tweet')).not.toBeInTheDocument()
  })

  it('renders asset financial information when available', () => {
    render(
      <TweetCard
        t={{
          ...baseTweet,
          assets: [
            {
              symbol: 'AAPL',
              kind: 'EQUITY',
              name: 'Apple Inc.',
              sector: 'Information Technology',
              company_profile: {
                exchange: 'NASDAQ Global Select',
                country: 'United States',
                currency: 'USD',
                market_cap_category: 'Mega Cap',
              },
              financials: {
                price: 185.12,
                change_percent: 1.73,
                source: 'coingecko',
              },
            },
          ],
        }}
      />
    )

    expect(screen.getByText('$AAPL')).toBeInTheDocument()
    expect(screen.getByText('Apple Inc.')).toBeInTheDocument()
    expect(screen.getByText('Stock')).toBeInTheDocument()
    expect(screen.getByText(/^\$185[.,]12$/)).toBeInTheDocument()
    expect(screen.getByText('+1.73%')).toBeInTheDocument()
    expect(screen.queryByText('Information Technology')).not.toBeInTheDocument()
    expect(
      screen.queryByText('NASDAQ Global Select | United States | USD | Mega Cap')
    ).not.toBeInTheDocument()
    expect(screen.queryByText('Source: COINGECKO')).not.toBeInTheDocument()
  })

  it('calls ticker filter callback when financial ticker is clicked', () => {
    const onTickerSelect = vi.fn()

    render(
      <TweetCard
        t={{
          ...baseTweet,
          assets: [{ symbol: 'SOL', kind: 'crypto', financials: { price: 150, change_percent: 2.4 } }],
        }}
        onTickerSelect={onTickerSelect}
      />
    )

    fireEvent.click(screen.getByRole('button', { name: 'Filter by $SOL' }))
    expect(onTickerSelect).toHaveBeenCalledWith('SOL')
  })

  it('links financial price to the source website when available', () => {
    render(
      <TweetCard
        t={{
          ...baseTweet,
          assets: [
            {
              symbol: 'AAPL',
              kind: 'EQUITY',
              financials: {
                price: 185.12,
                change_percent: 1.73,
                website: 'https://finance.yahoo.com/quote/AAPL',
              },
            },
          ],
        }}
      />
    )

    const priceLink = screen.getByRole('link', { name: /^\$185[.,]12$/ })
    expect(priceLink).toHaveAttribute('href', 'https://finance.yahoo.com/quote/AAPL')
  })

  it('renders media images when present', () => {
    const tweetWithMedia: Tweet = {
      ...baseTweet,
      media: [
        { url: 'https://example.com/img1.jpg', type: 'photo' },
        { url: 'https://example.com/img2.jpg', type: 'photo' },
      ],
    }
    render(<TweetCard t={tweetWithMedia} />)
    const images = screen.getAllByRole('img')
    // First image is the avatar, the next two are media
    const mediaImgs = images.filter((img) =>
      (img as HTMLImageElement).src.includes('img')
    )
    expect(mediaImgs).toHaveLength(2)
  })

  it('opens image preview dialog when inline media is clicked', () => {
    const tweetWithMedia: Tweet = {
      ...baseTweet,
      media: [{ url: 'https://example.com/img1.jpg', type: 'photo' }],
    }

    render(<TweetCard t={tweetWithMedia} />)

    fireEvent.click(screen.getByAltText('photo'))
    const dialog = screen.getByRole('dialog', { name: 'Image preview' })
    expect(dialog).toBeInTheDocument()
    const previewImage = dialog.querySelector('img') as HTMLImageElement
    expect(previewImage?.src).toContain('img1.jpg')
  })

  it('opens image preview dialog when quoted media is clicked', () => {
    const quoteText = '> [@opensea](https://twitter.com/opensea):\n> Quoted image.'

    render(
      <TweetCard
        t={{
          ...baseTweet,
          text: quoteText,
          media: [
            { url: 'https://example.com/inline.jpg', type: 'photo' },
            { url: 'https://example.com/quoted.jpg', type: 'photo' },
          ],
        }}
      />
    )

    fireEvent.click(screen.getByAltText('Quoted media'))
    expect(screen.getByRole('dialog', { name: 'Image preview' })).toBeInTheDocument()
  })

  it('does not render media section when media array is empty', () => {
    const { container } = render(<TweetCard t={baseTweet} />)
    // Only avatar image should be present
    const images = container.querySelectorAll('img')
    expect(images).toHaveLength(1)
  })
})
