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

  it('colours the forward P/E by valuation band', () => {
    const withPE = (forward_pe: number) => ({
      ...equity,
      fundamentals: { ...equity.fundamentals, forward_pe },
    })

    const { rerender } = render(<AssetFundamentals asset={withPE(11)} />)
    expect(screen.getByText('11.0').className).toContain('text-emerald-600')

    rerender(<AssetFundamentals asset={withPE(22)} />)
    expect(screen.getByText('22.0').className).toContain('text-zinc-500')

    rerender(<AssetFundamentals asset={withPE(48)} />)
    expect(screen.getByText('48.0').className).toContain('text-rose-600')
  })

  it('colours the trailing P/E fallback on the same scale', () => {
    render(
      <AssetFundamentals
        asset={{
          ...equity,
          fundamentals: { ...equity.fundamentals, forward_pe: null, trailing_pe: 9.4 },
        }}
      />
    )

    expect(screen.getByText('P/E (TTM)')).toBeInTheDocument()
    expect(screen.getByText('9.4').className).toContain('text-emerald-600')
  })

  it('leaves metrics with no good/bad reading uncoloured', () => {
    render(<AssetFundamentals asset={equity} />)

    for (const value of ['$3.40T', '215.0M']) {
      const className = screen.getByText(value).className
      expect(className).not.toContain('text-emerald-600')
      expect(className).not.toContain('text-rose-600')
      expect(className).not.toContain('text-zinc-500')
    }
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

  it('renders NAV for a fund-like asset', () => {
    render(
      <AssetFundamentals
        asset={{
          symbol: 'SPY',
          kind: 'ETF',
          name: 'SPDR S&P 500 ETF Trust',
          fundamentals: { market_cap: 500_000_000_000, nav: 645.12, currency: 'USD' },
        }}
      />
    )

    expect(screen.getByText('NAV')).toBeInTheDocument()
    expect(screen.getByText('$645.12')).toBeInTheDocument()
    expect(screen.getByText('NAV').getAttribute('title')).toContain('Net Asset Value')
  })

  it('omits NAV for an ordinary stock that has none', () => {
    render(<AssetFundamentals asset={equity} />)
    expect(screen.queryByText('NAV')).not.toBeInTheDocument()
  })

  it("renders today's volume next to the average for comparison", () => {
    render(
      <AssetFundamentals
        asset={{
          ...equity,
          fundamentals: { ...equity.fundamentals, day_volume: 320_000_000 },
        }}
      />
    )

    expect(screen.getByText('Volume')).toBeInTheDocument()
    expect(screen.getByText('320.0M')).toBeInTheDocument()
    expect(screen.getByText('Avg vol')).toBeInTheDocument()
    expect(screen.getByText('215.0M')).toBeInTheDocument()
    expect(screen.getByText('Volume').getAttribute('title')).toContain(
      'Compare it against the average'
    )
  })

  it('omits volume when Yahoo reports no session volume yet', () => {
    render(<AssetFundamentals asset={equity} />)
    expect(screen.queryByText('Volume')).not.toBeInTheDocument()
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
