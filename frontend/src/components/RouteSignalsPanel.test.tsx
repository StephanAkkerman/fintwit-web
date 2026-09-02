import { fireEvent, render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { RouteSignalsPanel } from './RouteSignalsPanel'

vi.mock('./SentimentShiftWidget', () => ({ SentimentShiftWidget: () => <div data-testid="sentiment-shift" /> }))
vi.mock('./VolumeBaselineWidget', () => ({ VolumeBaselineWidget: () => <div data-testid="volume-baseline" /> }))
vi.mock('./HiddenGemWidget', () => ({ HiddenGemWidget: () => <div data-testid="hidden-gem" /> }))

describe('RouteSignalsPanel', () => {
  it('is collapsed by default', () => {
    render(<RouteSignalsPanel assetKind="EQUITY" />)
    expect(screen.getByRole('button', { name: /more signals/i })).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByTestId('sentiment-shift')).not.toBeInTheDocument()
    expect(screen.queryByTestId('volume-baseline')).not.toBeInTheDocument()
    expect(screen.queryByTestId('hidden-gem')).not.toBeInTheDocument()
  })

  it('reveals the widgets when expanded', () => {
    render(<RouteSignalsPanel assetKind="EQUITY" />)
    fireEvent.click(screen.getByRole('button', { name: /more signals/i }))

    expect(screen.getByRole('button', { name: /more signals/i })).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByTestId('sentiment-shift')).toBeInTheDocument()
    expect(screen.getByTestId('volume-baseline')).toBeInTheDocument()
    expect(screen.getByTestId('hidden-gem')).toBeInTheDocument()
  })

  it('collapses again on a second click', () => {
    render(<RouteSignalsPanel assetKind="CRYPTO" />)
    const toggle = screen.getByRole('button', { name: /more signals/i })
    fireEvent.click(toggle)
    fireEvent.click(toggle)

    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByTestId('hidden-gem')).not.toBeInTheDocument()
  })
})
