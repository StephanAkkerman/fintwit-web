import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import NftTrendingWidget from '../components/NftTrendingWidget'

let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  fetchMock = vi.fn(() =>
    Promise.resolve(
      {
        ok: true,
        json: async () => [
          {
            id: 'doodles-official',
            name: 'Doodles',
            symbol: 'DOODLES',
            thumb: 'https://example.com/doodles.png',
            floor_price: 1.23,
            floor_currency: 'ETH',
            floor_change_24h: 2.34,
            website: 'https://www.coingecko.com/en/nft/doodles-official',
          },
        ],
      } as Response
    )
  )
  vi.stubGlobal('fetch', fetchMock)
})

describe('NftTrendingWidget', () => {
  it('renders heading and fetched nft rows', async () => {
    render(<NftTrendingWidget />)

    expect(screen.getByText(/trending nfts/i)).toBeInTheDocument()

    await waitFor(() => {
      expect(screen.getByRole('link', { name: /doodles/i })).toBeInTheDocument()
    })

    expect(screen.getByText(/1[.,]23 ETH/i)).toBeInTheDocument()
    expect(screen.getByText(/\+2\.34%/i)).toBeInTheDocument()
  })
})
