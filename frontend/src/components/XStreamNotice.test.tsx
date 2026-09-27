import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import XStreamNotice from './XStreamNotice'
import type { XStreamState } from '../types'

const status = (state: XStreamState, detail: string | null = null) => ({
  state,
  source: null,
  detail,
})

describe('XStreamNotice', () => {
  it('explains how to connect X when the stream is disabled', () => {
    render(<XStreamNotice status={status('disabled')} />)
    expect(screen.getByText('X timeline not connected')).toBeInTheDocument()
    expect(screen.getByText('X_AUTH_TOKEN')).toBeInTheDocument()
  })

  it('flags an expired session with the HTTP detail', () => {
    render(<XStreamNotice status={status('auth_failed', 'X answered HTTP 401')} />)
    expect(screen.getByText('X session expired')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('X answered HTTP 401')
  })

  it.each(['ok', 'connecting', 'error'] as XStreamState[])('renders nothing when %s', (state) => {
    const { container } = render(<XStreamNotice status={status(state)} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders nothing before the status has loaded', () => {
    const { container } = render(<XStreamNotice status={null} />)
    expect(container).toBeEmptyDOMElement()
  })
})
