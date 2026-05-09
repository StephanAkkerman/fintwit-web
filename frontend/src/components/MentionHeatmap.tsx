import { Treemap, ResponsiveContainer } from 'recharts'
import { useMentionHeat } from '../hooks/useMentionHeat'
import type { AssetKind } from '../types'

interface Props {
  assetKind: AssetKind
  minMentions?: number
  onTickerClick?: (ticker: string) => void
}

// CustomCell internal props (Recharts injects x, y, width, height, depth, root + data fields)
interface CellProps {
  x?: number
  y?: number
  width?: number
  height?: number
  ticker?: string
  avg_sentiment_24h?: number
  price_direction?: number | null
  onTickerClick?: (ticker: string) => void
  [key: string]: unknown
}

function sentimentFill(avg: number): string {
  if (avg >= 0.35) return '#059669'   // dark emerald, strong bull
  if (avg >= 0.1)  return '#10b981'   // emerald, mild bull
  if (avg >= -0.1) return '#3f3f46'   // zinc, neutral
  if (avg >= -0.35) return '#d97706'  // amber, mild bear
  return '#e11d48'                     // rose, strong bear
}

function priceBorder(dir: number | null): string {
  if (dir !== null && dir > 0) return '#22c55e'   // green
  if (dir !== null && dir < 0) return '#ef4444'   // red
  return '#52525b'                                  // zinc-600
}

function CustomCell(props: CellProps) {
  const {
    x = 0,
    y = 0,
    width = 0,
    height = 0,
    ticker = '',
    avg_sentiment_24h = 0,
    price_direction = null,
    onTickerClick,
  } = props

  if (width < 24 || height < 18) return null

  return (
    <g>
      <rect
        x={x}
        y={y}
        width={width}
        height={height}
        fill={sentimentFill(avg_sentiment_24h)}
        stroke={priceBorder(price_direction as number | null)}
        strokeWidth={2}
        rx={4}
      />
      <text
        x={x + width / 2}
        y={y + height / 2}
        dominantBaseline="middle"
        textAnchor="middle"
        fontSize={12}
        fill="#f4f4f5"
        onClick={() => onTickerClick?.(ticker)}
        style={{ cursor: 'pointer' }}
      >
        {ticker}
      </text>
    </g>
  )
}

export function MentionHeatmap({ assetKind, minMentions, onTickerClick }: Props) {
  const { data, loading } = useMentionHeat(assetKind, minMentions ?? 50)

  if (loading) {
    return <div className="h-[200px] bg-zinc-900 rounded-2xl animate-pulse" />
  }

  if (data.length === 0) {
    return (
      <div className="h-[200px] bg-zinc-900 rounded-2xl flex items-center justify-center text-zinc-500 text-sm">
        No tickers with enough mentions.{' '}
        <span className="ml-1 text-blue-400 underline cursor-not-allowed">widen window</span>
      </div>
    )
  }

  return (
    <div className="w-full bg-zinc-900 rounded-2xl overflow-hidden">
      <ResponsiveContainer width="100%" height={200}>
        <Treemap
          data={data as unknown as Record<string, unknown>[]}
          dataKey="mentions_24h"
          content={<CustomCell onTickerClick={onTickerClick} />}
        />
      </ResponsiveContainer>
    </div>
  )
}
