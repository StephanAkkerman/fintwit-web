import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import AssetFundamentals from '../components/AssetFundamentals'
import type { Asset } from '../types'

const equity: Asset = {
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
}

describe('AssetFundamentals', () => {
  it('renders market cap, forward P/E, average volume and industry', () => {
    render(<AssetFundamentals asset={equity} />)

    expect(screen.getByText('Mkt cap')).toBeInTheDocument()
    expect(screen.getByText('$3.40T')).toBeInTheDocument()
    expect(screen.getByText('Fwd P/E')).toBeInTheDocument()
    expect(screen.getByText('31.2')).toBeInTheDocument()
    expect(screen.getByText('Avg vol')).toBeInTheDocument()
    expect(screen.getByText('215.0M')).toBeInTheDocument()
    expect(screen.getByText('Semiconductors')).toBeInTheDocument()
  })

  it('explains each metric through a tooltip', () => {
    render(<AssetFundamentals asset={equity} />)

    expect(screen.getByText('Fwd P/E').getAttribute('title')).toContain(
      'forecast earnings per share'
    )
    expect(screen.getByText('Mkt cap').getAttribute('title')).toContain('shares outstanding')
    expect(screen.getByText('Avg vol').getAttribute('title')).toContain('last 3 months')
    // Both classifications survive in the tooltip even though only the
    // specific one is rendered.
    expect(screen.getByText('Semiconductors')).toHaveAttribute(
      'title',
      'Information Technology · Semiconductors'
    )
  })

  it('falls back to trailing P/E when Yahoo reports no forward estimate', () => {
    render(
      <AssetFundamentals
        asset={{ ...equity, fundamentals: { ...equity.fundamentals, forward_pe: null } }}
      />
    )

    expect(screen.queryByText('Fwd P/E')).not.toBeInTheDocument()
    expect(screen.getByText('P/E (TTM)')).toBeInTheDocument()
    expect(screen.getByText('45.8')).toBeInTheDocument()
  })

  it('omits ratios Yahoo does not report rather than showing zero', () => {
    render(
      <AssetFundamentals
        asset={{
          ...equity,
          fundamentals: { market_cap: 3_400_000_000_000, forward_pe: 0, trailing_pe: null },
        }}
      />
    )

    expect(screen.queryByText('Fwd P/E')).not.toBeInTheDocument()
    expect(screen.queryByText('P/E (TTM)')).not.toBeInTheDocument()
    expect(screen.queryByText('Avg vol')).not.toBeInTheDocument()
    expect(screen.getByText('$3.40T')).toBeInTheDocument()
  })

  it('falls back to the flat market cap on classifier rows cached before fundamentals existed', () => {
    render(
      <AssetFundamentals
        asset={{ symbol: 'AAPL', kind: 'EQUITY', market_cap: 4_029_017_227_264 }}
      />
    )

    expect(screen.getByText('$4.03T')).toBeInTheDocument()
  })

  it('renders a crypto market cap on its own', () => {
    render(
      <AssetFundamentals
        asset={{
          symbol: 'BTC',
          kind: 'CRYPTO',
          name: 'Bitcoin',
          fundamentals: { market_cap: 1_300_000_000_000, currency: 'USD' },
        }}
      />
    )

    expect(screen.getByText('$1.30T')).toBeInTheDocument()
    expect(screen.queryByText('Fwd P/E')).not.toBeInTheDocument()
  })

  it('uses the reported currency instead of assuming dollars', () => {
    render(
      <AssetFundamentals
        asset={{
          symbol: 'ASML',
          kind: 'EQUITY',
          fundamentals: { market_cap: 280_000_000_000, currency: 'EUR' },
        }}
      />
    )

    expect(screen.getByText('€280.00B')).toBeInTheDocument()
  })

  it('renders nothing for an asset with no fundamentals or classification', () => {
    const { container } = render(<AssetFundamentals asset={{ symbol: 'ES', kind: 'FUTURE' }} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders the sector alone when no industry is known', () => {
    render(
      <AssetFundamentals
        asset={{ symbol: 'XLF', kind: 'ETF', sector: 'Financials', industry: '   ' }}
      />
    )

    expect(screen.getByText('Financials')).toBeInTheDocument()
  })
})
