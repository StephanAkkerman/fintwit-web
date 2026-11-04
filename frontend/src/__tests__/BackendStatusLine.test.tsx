import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import BackendStatusLine from '../components/BackendStatusLine'
import type { BackendStatus } from '../types'

const HEALTHY: BackendStatus = {
  started_at: '2026-11-04T16:23:08+00:00',
  unexpected_restarts_24h: 0,
  last_unexpected_restart: null,
  peak_memory_mb: 2150,
}

describe('BackendStatusLine', () => {
  it('stays quiet about restarts while there are none', () => {
    render(<BackendStatusLine status={HEALTHY} />)

    expect(screen.getByText(/Running since/)).toBeInTheDocument()
    expect(screen.getByText(/peak memory 2\.1 GB/)).toBeInTheDocument()
    expect(screen.queryByText(/unexpected restart/)).not.toBeInTheDocument()
  })

  it('calls out unexpected restarts', () => {
    render(
      <BackendStatusLine
        status={{
          ...HEALTHY,
          unexpected_restarts_24h: 4,
          last_unexpected_restart: '2026-11-04T16:22:06+00:00',
          peak_memory_mb: 6758,
        }}
      />,
    )

    expect(screen.getByText(/4 unexpected restarts in 24h/)).toBeInTheDocument()
    expect(screen.getByText(/peak memory 6\.6 GB/)).toBeInTheDocument()
  })

  it('uses the singular for one restart', () => {
    render(<BackendStatusLine status={{ ...HEALTHY, unexpected_restarts_24h: 1 }} />)

    expect(screen.getByText(/1 unexpected restart in 24h/)).toBeInTheDocument()
  })

  it('leaves out memory on hosts that cannot report it', () => {
    render(<BackendStatusLine status={{ ...HEALTHY, peak_memory_mb: null }} />)

    expect(screen.queryByText(/peak memory/)).not.toBeInTheDocument()
  })

  it('shows small peaks in MB', () => {
    render(<BackendStatusLine status={{ ...HEALTHY, peak_memory_mb: 512.4 }} />)

    expect(screen.getByText(/peak memory 512 MB/)).toBeInTheDocument()
  })

  it('renders nothing without a status', () => {
    const { container } = render(<BackendStatusLine status={null} />)

    expect(container).toBeEmptyDOMElement()
  })
})
