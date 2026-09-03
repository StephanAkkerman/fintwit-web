import { useState } from 'react'
import type { AssetKind } from '../types'
import { SentimentShiftWidget } from './SentimentShiftWidget'
import { VolumeBaselineWidget } from './VolumeBaselineWidget'
import { HiddenGemWidget } from './HiddenGemWidget'

interface Props {
  assetKind: AssetKind
  windowHours?: number
  userFilter?: string | null
  subscriberOnly?: boolean
}

/** Sentiment shift / volume baseline / hidden gem widgets, collapsed by default so they add signal without pushing route content down. */
export function RouteSignalsPanel({ assetKind, windowHours = 24, userFilter = null, subscriberOnly = false }: Props) {
  const [open, setOpen] = useState(false)

  return (
    <div className="rounded-2xl border border-zinc-800 bg-zinc-900">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 p-3 text-left"
      >
        <span className="w-3 shrink-0 text-center text-[10px] text-zinc-500">{open ? '▾' : '▸'}</span>
        <h2 className="text-[13px] font-semibold text-zinc-100">More signals</h2>
        <span className="ml-auto text-[10px] text-zinc-500 font-mono">
          sentiment shift · mention volume · hidden gems
        </span>
      </button>
      {open && (
        <div className="grid grid-cols-1 gap-3 p-3 pt-0 md:grid-cols-3">
          <SentimentShiftWidget assetKind={assetKind} windowHours={windowHours} userFilter={userFilter} subscriberOnly={subscriberOnly} />
          <VolumeBaselineWidget assetKind={assetKind} windowHours={windowHours} userFilter={userFilter} subscriberOnly={subscriberOnly} />
          <HiddenGemWidget assetKind={assetKind} windowHours={windowHours} userFilter={userFilter} subscriberOnly={subscriberOnly} />
        </div>
      )}
    </div>
  )
}
