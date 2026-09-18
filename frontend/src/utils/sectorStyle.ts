import type { SectorTrend } from '../types'

/**
 * Fixed per-sector emoji + badge colour, so the same sector reads as the
 * same colour everywhere (tweet cards, sector widgets) — a recognizable cue
 * rather than a computed one. Keyed by normalized (trimmed, lowercased)
 * sector name; covers the GICS-style names `ticker-classifier`/Yahoo emit
 * plus a couple of variants seen in the wild ("Financials" vs "Financial
 * Services", "Information Technology" vs "Technology").
 */
const SECTOR_STYLES: Record<string, { emoji: string; className: string }> = {
  technology: {
    emoji: '💻',
    className: 'bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-300',
  },
  'information technology': {
    emoji: '💻',
    className: 'bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-300',
  },
  'financial services': {
    emoji: '🏦',
    className: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900/40 dark:text-indigo-300',
  },
  financials: {
    emoji: '🏦',
    className: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900/40 dark:text-indigo-300',
  },
  healthcare: {
    emoji: '🏥',
    className: 'bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-300',
  },
  'health care': {
    emoji: '🏥',
    className: 'bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-300',
  },
  'consumer cyclical': {
    emoji: '🛍️',
    className: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300',
  },
  'consumer discretionary': {
    emoji: '🛍️',
    className: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300',
  },
  'consumer defensive': {
    emoji: '🛒',
    className: 'bg-lime-100 text-lime-800 dark:bg-lime-900/40 dark:text-lime-300',
  },
  'consumer staples': {
    emoji: '🛒',
    className: 'bg-lime-100 text-lime-800 dark:bg-lime-900/40 dark:text-lime-300',
  },
  energy: {
    emoji: '🛢️',
    className: 'bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-300',
  },
  industrials: {
    emoji: '🏗️',
    className: 'bg-slate-200 text-slate-700 dark:bg-slate-700/60 dark:text-slate-300',
  },
  'basic materials': {
    emoji: '⛏️',
    className: 'bg-stone-200 text-stone-800 dark:bg-stone-800/60 dark:text-stone-300',
  },
  materials: {
    emoji: '⛏️',
    className: 'bg-stone-200 text-stone-800 dark:bg-stone-800/60 dark:text-stone-300',
  },
  'real estate': {
    emoji: '🏠',
    className: 'bg-teal-100 text-teal-800 dark:bg-teal-900/40 dark:text-teal-300',
  },
  utilities: {
    emoji: '💡',
    className: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300',
  },
  'communication services': {
    emoji: '📡',
    className: 'bg-violet-100 text-violet-800 dark:bg-violet-900/40 dark:text-violet-300',
  },
  telecommunications: {
    emoji: '📡',
    className: 'bg-violet-100 text-violet-800 dark:bg-violet-900/40 dark:text-violet-300',
  },
}

const DEFAULT_SECTOR_STYLE = {
  emoji: '📊',
  className: 'bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300',
}

/** Emoji + Tailwind badge classes for a sector name; falls back to a neutral chart icon for anything unrecognized. */
export function getSectorStyle(sector: string | null | undefined): { emoji: string; className: string } {
  const normalized = (sector ?? '').trim().toLowerCase()
  if (!normalized) return DEFAULT_SECTOR_STYLE
  return SECTOR_STYLES[normalized] ?? DEFAULT_SECTOR_STYLE
}

const TREND_META: Record<SectorTrend, { emoji: string; label: string; className: string }> = {
  hot: {
    emoji: '🔥',
    label: 'Hot',
    className: 'bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-300',
  },
  rising: {
    emoji: '📈',
    label: 'Rising',
    className: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300',
  },
  cooling: {
    emoji: '📉',
    label: 'Cooling down',
    className: 'bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-300',
  },
  rare: {
    emoji: '🌱',
    label: 'Rarely mentioned',
    className: 'bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400',
  },
  steady: {
    emoji: '➖',
    label: 'Steady',
    className: 'bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300',
  },
}

/** Emoji + label + Tailwind badge classes for a sector/industry momentum trend (issue #146). Defaults to "steady" for an unknown/missing value. */
export function getTrendMeta(trend: string | null | undefined): { emoji: string; label: string; className: string } {
  return TREND_META[trend as SectorTrend] ?? TREND_META.steady
}
