import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { VolumeBaselineWidget } from './VolumeBaselineWidget'
import type { VolumeBaselineItem } from '../types'

vi.mock('../hooks/useVolumeBaseline', () => ({
  useVolumeBaseline: vi.fn(),
}))

import { useVolumeBaseline } from '../hooks/useVolumeBaseline'
const mockUseVolumeBaseline = vi.mocked(useVolumeBaseline)

const makeSample = (n: number): VolumeBaselineItem[] =>
  Array.from({ length: n }, (_, i) => ({
    ticker: `TKR${i}`,
    mentions_24h: 10 + i,
    baseline_7d_avg: 1 + i,
    volume_multiplier: 9.4 + i,
    asset_kind: 'EQUITY',
  }))

beforeEach(() => {
  vi.clearAllMocks()
})

describe('VolumeBaselineWidget', () => {
  it('shows loading skeleton when loading is true', () => {
    mockUseVolumeBaseline.mockReturnValue({ data: [], loading: true, error: false })
    render(<VolumeBaselineWidget assetKind="all" />)
    const skeleton = document.querySelector('.animate-pulse')
    expect(skeleton).not.toBeNull()
  })

  it('shows error message when error is true', () => {
    mockUseVolumeBaseline.mockReturnValue({ data: [], loading: false, error: true })
    render(<VolumeBaselineWidget assetKind="all" />)
    expect(screen.getByText(/Failed to load volume data/i)).toBeTruthy()
  })

  it('shows empty state when data is empty and loading is false', () => {
    mockUseVolumeBaseline.mockReturnValue({ data: [], loading: false, error: false })
    render(<VolumeBaselineWidget assetKind="all" />)
    expect(screen.getByText(/No volume spikes detected/i)).toBeTruthy()
  })

  it('renders ticker and multiplier label for each row', () => {
    const items = makeSample(3)
    mockUseVolumeBaseline.mockReturnValue({ data: items, loading: false, error: false })
    render(<VolumeBaselineWidget assetKind="EQUITY" />)

    // Header (title changed to "Unusually loud")
    expect(screen.getByText('Unusually loud')).toBeTruthy()

    // Tickers now rendered with $ prefix
    expect(screen.getByText('$TKR0')).toBeTruthy()
    expect(screen.getByText('$TKR1')).toBeTruthy()
    expect(screen.getByText('$TKR2')).toBeTruthy()

    // Multiplier labels: 9.4×, 10.4×, 11.4×
    expect(screen.getByText('9.4×')).toBeTruthy()
    expect(screen.getByText('10.4×')).toBeTruthy()
    expect(screen.getByText('11.4×')).toBeTruthy()
  })

  it('truncates to 10 rows and shows "+N more" when data has >10 items', () => {
    const items = makeSample(13)
    mockUseVolumeBaseline.mockReturnValue({ data: items, loading: false, error: false })
    render(<VolumeBaselineWidget assetKind="all" />)

    // Only first 10 tickers should be visible
    expect(screen.getByText('$TKR0')).toBeTruthy()
    expect(screen.getByText('$TKR9')).toBeTruthy()
    expect(screen.queryByText('$TKR10')).toBeNull()

    // "+3 more" truncation label
    expect(screen.getByText('+3 more')).toBeTruthy()
  })
})
