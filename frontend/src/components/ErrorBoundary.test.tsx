import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ErrorBoundary from './ErrorBoundary'

function Boom({ message = 'kaboom' }: { message?: string }): JSX.Element {
  throw new Error(message)
}

// React logs the caught error and component stack; that noise is expected here.
beforeEach(() => vi.spyOn(console, 'error').mockImplementation(() => {}))
afterEach(() => vi.restoreAllMocks())

describe('ErrorBoundary', () => {
  it('renders children when nothing throws', () => {
    render(
      <ErrorBoundary label="Widget">
        <p>all good</p>
      </ErrorBoundary>
    )

    expect(screen.getByText('all good')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('shows a named fallback carrying the error message', () => {
    render(
      <ErrorBoundary label="Portfolio value">
        <Boom message="Cannot read properties of undefined (reading 'market_value')" />
      </ErrorBoundary>
    )

    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByText(/portfolio value failed to render/i)).toBeInTheDocument()
    expect(screen.getByText(/reading 'market_value'/)).toBeInTheDocument()
  })

  it('keeps sibling widgets alive when one throws', () => {
    render(
      <>
        <ErrorBoundary label="Broken widget">
          <Boom />
        </ErrorBoundary>
        <ErrorBoundary label="Healthy widget">
          <p>still here</p>
        </ErrorBoundary>
      </>
    )

    expect(screen.getByText(/broken widget failed to render/i)).toBeInTheDocument()
    // The whole point: the neighbour renders normally.
    expect(screen.getByText('still here')).toBeInTheDocument()
  })

  it('retries on demand', () => {
    let shouldThrow = true
    function Flaky() {
      if (shouldThrow) throw new Error('not yet')
      return <p>recovered</p>
    }

    render(
      <ErrorBoundary label="Flaky widget">
        <Flaky />
      </ErrorBoundary>
    )

    expect(screen.getByRole('alert')).toBeInTheDocument()

    shouldThrow = false
    fireEvent.click(screen.getByRole('button', { name: /try again/i }))

    expect(screen.getByText('recovered')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('uses a compact fallback for list items', () => {
    render(
      <ErrorBoundary label="This tweet" compact>
        <Boom />
      </ErrorBoundary>
    )

    expect(screen.getByText(/this tweet could not be displayed/i)).toBeInTheDocument()
    // No heading or retry button in the compact form.
    expect(screen.queryByRole('button')).toBeNull()
  })

  it('logs the failure with its label for debugging', () => {
    render(
      <ErrorBoundary label="Asset context">
        <Boom message="bad payload" />
      </ErrorBoundary>
    )

    expect(console.error).toHaveBeenCalledWith(
      '[Asset context] render failed',
      expect.objectContaining({ message: 'bad payload' }),
      expect.anything()
    )
  })
})
