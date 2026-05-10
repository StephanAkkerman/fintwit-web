import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { HiddenGemWidget } from './HiddenGemWidget'
import type { HiddenGemItem } from '../types'

vi.mock('../hooks/useHiddenGems', () => ({
  useHiddenGems: vi.fn(),
}))

import { useHiddenGems } from '../hooks/useHiddenGems'
const mockUseHiddenGems = vi.mocked(useHiddenGems)

const makeNewItem = (ticker: string): HiddenGemItem => ({
  ticker,
  mentions_24h: 5,
  gem_subtype: 'new',
  days_since_last: null,
  first_seen: '2026-05-09T00:00:00Z',
  last_seen: null,
  asset_kind: 'EQUITY',
})

const makeResurfacingItem = (ticker: string, days: number): HiddenGemItem => ({
  ticker,
  mentions_24h: 3,
  gem_subtype: 'resurfacing',
  days_since_last: days,
  first_seen: '2026-01-01T00:00:00Z',
  last_seen: '2026-04-25T00:00:00Z',
  asset_kind: 'CRYPTO',
})

const makeSample = (n: number): HiddenGemItem[] =>
  Array.from({ length: n }, (_, i) => makeNewItem(`TKR${i}`))

beforeEach(() => {
  vi.clearAllMocks()
})

describe('HiddenGemWidget', () => {
  it('shows loading skeleton when loading is true', () => {
    mockUseHiddenGems.mockReturnValue({ data: [], loading: true, error: false })
    render(<HiddenGemWidget assetKind="all" />)
    const skeleton = document.querySelector('.animate-pulse')
    expect(skeleton).not.toBeNull()
  })

  it('shows error message when error is true', () => {
    mockUseHiddenGems.mockReturnValue({ data: [], loading: false, error: true })
    render(<HiddenGemWidget assetKind="all" />)
    expect(screen.getByText(/Failed to load hidden gems/i)).toBeTruthy()
  })

  it('shows empty state when data is empty and loading is false', () => {
    mockUseHiddenGems.mockReturnValue({ data: [], loading: false, error: false })
    render(<HiddenGemWidget assetKind="all" />)
    expect(screen.getByText(/No hidden gems found/i)).toBeTruthy()
  })

  it('renders a new item with "✦ new" badge and "first time" label', () => {
    const items = [makeNewItem('AAPL')]
    mockUseHiddenGems.mockReturnValue({ data: items, loading: false, error: false })
    render(<HiddenGemWidget assetKind="EQUITY" />)

    expect(screen.getByText('Hidden gems')).toBeTruthy()
    expect(screen.getByText('$AAPL')).toBeTruthy()
    expect(screen.getByText('✦ new')).toBeTruthy()
    expect(screen.getByText('first time')).toBeTruthy()
  })

  it('renders a resurfacing item with "↩ resurface" badge and "{N}d ago" label', () => {
    const items = [makeResurfacingItem('BTC', 14)]
    mockUseHiddenGems.mockReturnValue({ data: items, loading: false, error: false })
    render(<HiddenGemWidget assetKind="CRYPTO" />)

    expect(screen.getByText('$BTC')).toBeTruthy()
    expect(screen.getByText('↩ resurface')).toBeTruthy()
    expect(screen.getByText('14d ago')).toBeTruthy()
  })

  it('truncates to 10 rows and shows "+N more" when data has >10 items', () => {
    const items = makeSample(13)
    mockUseHiddenGems.mockReturnValue({ data: items, loading: false, error: false })
    render(<HiddenGemWidget assetKind="all" />)

    expect(screen.getByText('$TKR0')).toBeTruthy()
    expect(screen.getByText('$TKR9')).toBeTruthy()
    expect(screen.queryByText('$TKR10')).toBeNull()
    expect(screen.getByText('+3 more')).toBeTruthy()
  })
})
