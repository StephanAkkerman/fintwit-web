const UP_COLOR = '#34d399' // emerald-400
const DOWN_COLOR = '#fb7185' // rose-400

export function Sparkline({
  data,
  width = 48,
  height = 18,
}: {
  data: number[]
  width?: number
  height?: number
}) {
  if (data.length < 2) return null
  const min = Math.min(...data)
  const max = Math.max(...data)
  const range = max - min || 1
  // Color reflects the sparkline's own start-to-end movement, not some other
  // metric shown alongside it (e.g. the day's change_pct, a different
  // timeframe) - otherwise the line's color can contradict the direction it
  // visibly draws.
  const up = data[data.length - 1] >= data[0]
  const color = up ? UP_COLOR : DOWN_COLOR
  const pts = data
    .map((v, i) => {
      const x = (i / (data.length - 1)) * width
      const y = height - ((v - min) / range) * (height - 2) - 1
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
  const lastPt = pts.split(' ').at(-1)?.split(',') ?? [String(width), '1']
  return (
    <svg width={width} height={height} className="shrink-0 block">
      <polyline
        points={pts}
        fill="none"
        stroke={color}
        strokeWidth={1.5}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      <circle cx={lastPt[0]} cy={lastPt[1]} r="1.8" fill={color} />
    </svg>
  )
}
