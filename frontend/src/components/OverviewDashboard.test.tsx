import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { OverviewDashboard } from './OverviewDashboard'

vi.mock('./MacroStrip', () => ({ MacroStrip: () => <div data-testid="macro-strip" /> }))
vi.mock('./ActivityPulseWidget', () => ({ ActivityPulseWidget: () => <div data-testid="activity-pulse" /> }))
vi.mock('./AssetFilterTabs', () => ({
  AssetFilterTabs: ({ active }: { active: string }) => <div data-testid="filter-tabs" data-active={active} />
}))
vi.mock('./MentionHeatmap', () => ({
  MentionHeatmap: () => <div data-testid="mention-heatmap" />,
  MENTION_WINDOWS: [24, 48, 168] as const,
}))
vi.mock('./SentimentShiftWidget', () => ({ SentimentShiftWidget: () => <div data-testid="sentiment-shift" /> }))
vi.mock('./VolumeBaselineWidget', () => ({ VolumeBaselineWidget: () => <div data-testid="volume-baseline" /> }))
vi.mock('./HiddenGemWidget', () => ({ HiddenGemWidget: () => <div data-testid="hidden-gem" /> }))
vi.mock('./SectorMentionsWidget', () => ({ SectorMentionsWidget: () => <div data-testid="sector-mentions" /> }))

describe('OverviewDashboard', () => {
  it('renders all child components', () => {
    render(<OverviewDashboard />)
    expect(screen.getByTestId('macro-strip')).toBeInTheDocument()
    expect(screen.getByTestId('activity-pulse')).toBeInTheDocument()
    expect(screen.getByTestId('filter-tabs')).toBeInTheDocument()
    expect(screen.getByTestId('mention-heatmap')).toBeInTheDocument()
    expect(screen.getByTestId('sentiment-shift')).toBeInTheDocument()
    expect(screen.getByTestId('volume-baseline')).toBeInTheDocument()
    expect(screen.getByTestId('hidden-gem')).toBeInTheDocument()
    expect(screen.getByTestId('sector-mentions')).toBeInTheDocument()
  })

  it('passes assetKind="all" to AssetFilterTabs initially', () => {
    render(<OverviewDashboard />)
    expect(screen.getByTestId('filter-tabs')).toHaveAttribute('data-active', 'all')
  })
})
