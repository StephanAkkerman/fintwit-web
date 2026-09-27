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

  it('renders a subscribers-only icon for exclusive tweets', () => {
    render(
      <TweetCard
        t={{
          ...baseTweet,
          is_subscriber_only: true,
        }}
      />
    )

    expect(screen.getByLabelText('Subscribers-only post')).toBeInTheDocument()
  })

  it('renders tweet text', () => {
    render(<TweetCard t={baseTweet} />)
    expect(screen.getByText('Hello world')).toBeInTheDocument()
  })

  it('preserves line breaks and blank lines in tweet text', () => {
    const { container } = render(
      <TweetCard
        t={{
          ...baseTweet,
          text: 'Line one\nLine two\n\nLine four',
        }}
      />
    )

    const paragraphs = Array.from(container.querySelectorAll('p'))
    expect(paragraphs.length).toBeGreaterThanOrEqual(2)
    expect(paragraphs[0].textContent).toBe('Line one\nLine two')
    expect(paragraphs[1].textContent).toBe('Line four')
    expect(paragraphs[0].className).toContain('whitespace-pre-wrap')
    expect(paragraphs[1].className).toContain('whitespace-pre-wrap')
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

  it('does not treat plain leading > text as a quoted tweet embed', () => {
    const plainText = 'main text\n> second text'

    const { container } = render(
      <TweetCard
        t={{
          ...baseTweet,
          text: plainText,
        }}
      />
    )

    expect(screen.getByText('main text')).toBeInTheDocument()
    expect(screen.getByText('second text')).toBeInTheDocument()
    expect(container.querySelector('blockquote')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Quoted tweet author')).not.toBeInTheDocument()
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

  it('renders repost attribution with original author identity', () => {
    const { container } = render(
      <TweetCard
        t={{
          ...baseTweet,
          user_name: 'Repost Account',
          user_screen_name: 'repostacct',
          user_img: 'https://example.com/reposter.jpg',
          title: 'Repost Account retweeted Original Analyst',
          text: 'Original post body',
          quoted_tweet: {
            id: '9001',
            text: 'Original post body',
            user_name: 'Original Analyst',
            user_screen_name: 'originalanalyst',
            user_img: 'https://example.com/original.jpg',
            url: 'https://x.com/originalanalyst/status/9001',
            media: [],
            tickers: [],
            hashtags: [],
            title: 'Original Analyst tweeted',
            media_types: [],
            created_at: '2026-04-01T12:00:00Z',
            likes: 0,
            retweets: 0,
            replies: 0,
            views: 0,
          },
        }}
      />
    )

    expect(screen.getByText('Original Analyst')).toBeInTheDocument()
    expect(screen.getByText('@originalanalyst')).toBeInTheDocument()
    expect(screen.getByText('Reposted by Repost Account')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /open/i })).toHaveAttribute(
      'href',
      'https://x.com/originalanalyst/status/9001'
    )

    const headerImage = container.querySelector('header img') as HTMLImageElement | null
    expect(headerImage?.src).toContain('original.jpg')
    expect(container.querySelector('blockquote')).not.toBeInTheDocument()
  })

  it('renders subscribers-only icon from reposted original tweet metadata', () => {
    render(
      <TweetCard
        t={{
          ...baseTweet,
          user_name: 'Repost Account',
          user_screen_name: 'repostacct',
          title: 'Repost Account retweeted Original Analyst',
          quoted_tweet: {
            id: '9002',
            text: 'Original subscribers-only post',
            user_name: 'Original Analyst',
            user_screen_name: 'originalanalyst',
            user_img: 'https://example.com/original.jpg',
            url: 'https://x.com/originalanalyst/status/9002',
            media: [],
            tickers: [],
            hashtags: [],
            title: 'Original Analyst tweeted',
            media_types: [],
            created_at: '2026-04-01T12:00:00Z',
            likes: 0,
            retweets: 0,
            replies: 0,
            views: 0,
            is_subscriber_only: true,
          },
        }}
      />
    )

    expect(screen.getByLabelText('Subscribers-only post')).toBeInTheDocument()
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

  it('shows chart-extracted symbol badge when chart_extraction is present', () => {
    render(
      <TweetCard
        t={{
          ...baseTweet,
          has_chart: true,
          chart_extraction: {
            symbol: 'SPY',
            exchange: 'NYSE',
            timeframe: '1D',
            price: 682.98,
            session: 'regular',
          },
        }}
      />
    )

    expect(screen.getByLabelText('Chart-extracted symbol')).toHaveTextContent('SPY · 1D · $682.98')
  })

  it('does not show chart-extracted symbol badge when chart_extraction is absent', () => {
    render(<TweetCard t={{ ...baseTweet, has_chart: true, chart_extraction: null }} />)
    expect(screen.queryByLabelText('Chart-extracted symbol')).not.toBeInTheDocument()
  })

  it('shows image text badge when image_text is present', () => {
    render(<TweetCard t={{ ...baseTweet, image_text: 'Sold $SPY 680C for a nice gain' }} />)
    const badge = screen.getByLabelText('Image text')
    expect(badge).toHaveTextContent('Image text')
    expect(badge).toHaveAttribute('title', 'Extracted from the image via OCR: Sold $SPY 680C for a nice gain')
  })

  it('does not show image text badge when image_text is absent', () => {
    render(<TweetCard t={{ ...baseTweet, image_text: null }} />)
    expect(screen.queryByLabelText('Image text')).not.toBeInTheDocument()
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

  it('shows a per-ticker sentiment chip on every asset card when the tweet has a ticker sentiment split', () => {
    render(
      <TweetCard
        t={{
          ...baseTweet,
          text: 'Long $NVDA here, short $INTC into earnings',
          sentiment_score: 0.6,
          ticker_sentiment: { INTC: -0.85 },
          assets: [
            { symbol: 'NVDA', kind: 'EQUITY', financials: { price: 128.4, change_percent: 2.3 } },
            { symbol: 'INTC', kind: 'EQUITY', financials: { price: 22.1, change_percent: -1.1 } },
          ],
        }}
      />
    )

    // NVDA has no override, so it reads the post's overall (bullish) score.
    expect(screen.getByLabelText('Sentiment for $NVDA: Bullish')).toBeInTheDocument()
    // INTC has its own override, and it disagrees with the overall reading.
    expect(screen.getByLabelText('Sentiment for $INTC: Bearish')).toBeInTheDocument()
  })

  it('renders a sparkline in the asset card when financials include one', () => {
    const { container } = render(
      <TweetCard
        t={{
          ...baseTweet,
          assets: [
            {
              symbol: 'NVDA',
              kind: 'EQUITY',
              financials: {
                price: 128.4,
                change_percent: 2.3,
                sparkline: [125.0, 126.5, 128.4],
              },
            },
          ],
        }}
      />
    )

    expect(container.querySelector('svg polyline')).not.toBeNull()
  })

  it('does not render a sparkline when financials have no sparkline data', () => {
    const { container } = render(
      <TweetCard
        t={{
          ...baseTweet,
          assets: [
            { symbol: 'NVDA', kind: 'EQUITY', financials: { price: 128.4, change_percent: 2.3 } },
          ],
        }}
      />
    )

    expect(container.querySelector('svg polyline')).toBeNull()
  })

  it('does not show per-ticker sentiment chips when the tweet has no ticker sentiment split', () => {
    render(
      <TweetCard
        t={{
          ...baseTweet,
          sentiment_score: 0.6,
          assets: [{ symbol: 'NVDA', kind: 'EQUITY', financials: { price: 128.4, change_percent: 2.3 } }],
        }}
      />
    )

    expect(screen.queryByLabelText(/^Sentiment for \$/)).not.toBeInTheDocument()
  })

  it('replaces the footer sentiment badge with a Mixed indicator when tickers diverge', () => {
    render(
      <TweetCard
        t={{
          ...baseTweet,
          sentiment_label: 'BULLISH',
          sentiment_emoji: '🐂',
          sentiment_score: 0.6,
          ticker_sentiment: { INTC: -0.85 },
          assets: [
            { symbol: 'NVDA', kind: 'EQUITY', financials: { price: 128.4, change_percent: 2.3 } },
            { symbol: 'INTC', kind: 'EQUITY', financials: { price: 22.1, change_percent: -1.1 } },
          ],
        }}
      />
    )

    const mixedBadge = screen.getByLabelText('Tweet sentiment: mixed by ticker')
    expect(mixedBadge).toBeInTheDocument()
    expect(mixedBadge).toHaveAttribute('title', 'INTC: Bearish')
    expect(screen.queryByLabelText('Tweet sentiment')).not.toBeInTheDocument()
  })

  it('does not show Mixed or per-ticker chips when ticker_sentiment differs in score but not in label', () => {
    render(
      <TweetCard
        t={{
          ...baseTweet,
          sentiment_label: 'BULLISH',
          sentiment_emoji: '🐂',
          sentiment_score: 0.455,
          ticker_sentiment: { NVDA: 0.91 }, // higher score, but still BULLISH — not a real split
          assets: [{ symbol: 'NVDA', kind: 'EQUITY', financials: { price: 128.4, change_percent: 2.3 } }],
        }}
      />
    )

    expect(screen.getByLabelText('Tweet sentiment')).toBeInTheDocument()
    expect(screen.queryByLabelText('Tweet sentiment: mixed by ticker')).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/^Sentiment for \$/)).not.toBeInTheDocument()
  })

  it('renders subscribers-only icon for quoted tweet embeds', () => {
    const quoteText = '> [@writer](https://x.com/writer/status/800):\n> Subscribers-only update'

    render(
      <TweetCard
        t={{
          ...baseTweet,
          text: quoteText,
          quoted_tweet: {
            id: '800',
            text: 'Subscribers-only update',
            user_name: 'Writer',
            user_screen_name: 'writer',
            user_img: 'https://example.com/writer.jpg',
            url: 'https://x.com/writer/status/800',
            media: [],
            tickers: [],
            hashtags: [],
            title: 'Writer tweeted',
            media_types: [],
            created_at: '2026-04-10T10:00:00Z',
            likes: 0,
            retweets: 0,
            replies: 0,
            views: 0,
            is_subscriber_only: true,
          },
        }}
      />
    )

    expect(screen.getByLabelText('Quoted subscribers-only post')).toBeInTheDocument()
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
    expect(screen.getByText('Information Technology')).toBeInTheDocument()
    expect(
      screen.queryByText('NASDAQ Global Select | United States | USD | Mega Cap')
    ).not.toBeInTheDocument()
    expect(screen.queryByText('Source: COINGECKO')).not.toBeInTheDocument()
  })

  it('renders the fundamentals strip for an asset by default', () => {
    render(
      <TweetCard
        t={{
          ...baseTweet,
          assets: [
            {
              symbol: 'NVDA',
              kind: 'EQUITY',
              name: 'NVIDIA Corp',
              sector: 'Information Technology',
              industry: 'Semiconductors',
              fundamentals: {
                market_cap: 3_400_000_000_000,
                forward_pe: 31.24,
                trailing_pe: 45.8,
                avg_volume: 215_000_000,
                currency: 'USD',
              },
              financials: { price: 140.5, change_percent: 2.1 },
            },
          ],
        }}
      />
    )

    expect(screen.getByText('$3.40T')).toBeInTheDocument()
    expect(screen.getByText('Fwd P/E')).toBeInTheDocument()
    expect(screen.getByText('31.2')).toBeInTheDocument()
    expect(screen.getByText('215.0M')).toBeInTheDocument()
    // The specific industry wins over the broad sector.
    expect(screen.getByText('Semiconductors')).toBeInTheDocument()
    expect(screen.queryByText('Information Technology')).not.toBeInTheDocument()
  })

  it('omits the fundamentals strip when an asset has none', () => {
    render(
      <TweetCard
        t={{
          ...baseTweet,
          assets: [
            { symbol: 'ES', kind: 'FUTURE', financials: { price: 5800, change_percent: 0.4 } },
          ],
        }}
      />
    )

    expect(screen.queryByTestId('asset-fundamentals')).not.toBeInTheDocument()
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

  it('calls user filter callback when author name is clicked', () => {
    const onUserSelect = vi.fn()

    render(
      <TweetCard
        t={baseTweet}
        onUserSelect={onUserSelect}
      />
    )

    fireEvent.click(screen.getAllByRole('button', { name: 'Filter by user @testuser' })[1])
    expect(onUserSelect).toHaveBeenCalledWith('testuser')
  })

  it('calls user filter callback when author avatar is clicked', () => {
    const onUserSelect = vi.fn()

    render(
      <TweetCard
        t={baseTweet}
        onUserSelect={onUserSelect}
      />
    )

    fireEvent.click(screen.getAllByRole('button', { name: 'Filter by user @testuser' })[0])
    expect(onUserSelect).toHaveBeenCalledWith('testuser')
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

  it('shows after-hours price and change when session is after-hours', () => {
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
                change_percent: 1.22,
                session: 'after-hours',
                extended_price: 184.80,
                extended_change_percent: -0.17,
                website: 'https://finance.yahoo.com/quote/AAPL',
              },
            },
          ],
        }}
      />
    )

    expect(screen.getByText('🌙')).toBeInTheDocument()
    expect(screen.getByText('After Hours')).toBeInTheDocument()
    expect(screen.getByText(/\$184[.,]80/)).toBeInTheDocument()
  })

  it('shows pre-market price and change when session is pre-market', () => {
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
                change_percent: 1.22,
                session: 'pre-market',
                extended_price: 186.40,
                extended_change_percent: 0.69,
                website: 'https://finance.yahoo.com/quote/AAPL',
              },
            },
          ],
        }}
      />
    )

    expect(screen.getByText('🌅')).toBeInTheDocument()
    expect(screen.getByText('Pre-Market')).toBeInTheDocument()
    expect(screen.getByText(/\$186[.,]40/)).toBeInTheDocument()
  })

  it('renders tradingview technical analysis when available', () => {
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
                technical_analysis: {
                  source: 'tradingview_ta',
                  four_h: {
                    interval: 'four_h',
                    recommendation: 'Buy',
                    buy: 10,
                    neutral: 8,
                    sell: 4,
                    summary: 'Buy\n10📈 8⌛️ 4📉',
                  },
                  one_d: {
                    interval: 'one_d',
                    recommendation: 'Strong Buy',
                    buy: 13,
                    neutral: 7,
                    sell: 2,
                    summary: 'Strong Buy\n13📈 7⌛️ 2📉',
                  },
                },
              },
            },
          ],
        }}
      />
    )

    expect(screen.getByText('4H')).toBeInTheDocument()
    expect(screen.getByText('1D')).toBeInTheDocument()
    expect(screen.getByText('Buy')).toBeInTheDocument()
    expect(screen.getByText('Strong Buy')).toBeInTheDocument()
    expect(screen.getByText('10 buy · 8 neutral · 4 sell')).toBeInTheDocument()
    expect(screen.getByText('13 buy · 7 neutral · 2 sell')).toBeInTheDocument()
    // Recommendations are color-coded green for buy verdicts.
    expect(screen.getByText('Buy').className).toContain('emerald')
    expect(screen.getByText('Strong Buy').className).toContain('emerald')
  })

  it('renders the signa signal when available on an asset', () => {
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
                signa: {
                  source: 'signa',
                  symbol: 'AAPL',
                  signal: 'Bearish',
                  score: 41,
                  confidence: 0.66,
                  timeframe: '1D',
                },
              },
            },
          ],
        }}
      />
    )

    expect(screen.getByText('Signa')).toBeInTheDocument()
    const verdict = screen.getByText('Bearish')
    expect(verdict).toBeInTheDocument()
    expect(verdict.className).toContain('rose')
    expect(screen.getByText(/41/)).toBeInTheDocument()
    expect(screen.getByText(/66%/)).toBeInTheDocument()
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

  it('shows a held badge for an asset currently in the portfolio', () => {
    render(
      <TweetCard
        t={{
          ...baseTweet,
          assets: [{ symbol: 'AAPL', kind: 'EQUITY', financials: { price: 185.12, change_percent: 1.73 } }],
        }}
        portfolioLookup={(symbol) => (symbol === 'AAPL' ? 'active' : null)}
      />
    )

    expect(screen.getByLabelText('Currently in your portfolio')).toBeInTheDocument()
    expect(screen.getByText('💼 Held')).toBeInTheDocument()
  })

  it('shows a recently-held badge for an asset closed out within the last 30 days', () => {
    render(
      <TweetCard
        t={{
          ...baseTweet,
          assets: [{ symbol: 'TSLA', kind: 'EQUITY', financials: { price: 250, change_percent: -0.5 } }],
        }}
        portfolioLookup={(symbol) => (symbol === 'TSLA' ? 'recent' : null)}
      />
    )

    expect(screen.getByLabelText('Recently in your portfolio')).toBeInTheDocument()
    expect(screen.getByText('🕓 Recently Held')).toBeInTheDocument()
  })

  it('does not show a portfolio badge when the ticker is not in the lookup', () => {
    render(
      <TweetCard
        t={{
          ...baseTweet,
          assets: [{ symbol: 'MSFT', kind: 'EQUITY', financials: { price: 420, change_percent: 0.2 } }],
        }}
        portfolioLookup={() => null}
      />
    )

    expect(screen.queryByLabelText('Currently in your portfolio')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Recently in your portfolio')).not.toBeInTheDocument()
  })

  it('does not show a portfolio badge when no portfolioLookup is provided', () => {
    render(
      <TweetCard
        t={{
          ...baseTweet,
          assets: [{ symbol: 'MSFT', kind: 'EQUITY', financials: { price: 420, change_percent: 0.2 } }],
        }}
      />
    )

    expect(screen.queryByLabelText('Currently in your portfolio')).not.toBeInTheDocument()
  })

  it('does not render media section when media array is empty', () => {
    const { container } = render(<TweetCard t={baseTweet} />)
    // Only avatar image should be present
    const images = container.querySelectorAll('img')
    expect(images).toHaveLength(1)
  })
})
