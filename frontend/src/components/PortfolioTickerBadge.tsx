import type { PortfolioTickerStatus } from '../hooks/usePortfolioTickers'

const EMOJI: Record<PortfolioTickerStatus, string> = {
  active: '💼',
  recent: '🕓',
}

const TITLE: Record<PortfolioTickerStatus, string> = {
  active: 'Currently in your portfolio',
  recent: 'Recently in your portfolio',
}

interface Props {
  status: PortfolioTickerStatus | null
}

/** Compact emoji flag for tickers held (💼) or recently held (🕓) in the portfolio, for tight analytics-row layouts. */
export function PortfolioTickerBadge({ status }: Props) {
  if (!status) return null
  return (
    <span aria-label={TITLE[status]} title={TITLE[status]} className="shrink-0 text-[10px] leading-none">
      {EMOJI[status]}
    </span>
  )
}
