import { useMemo } from 'react'
import { useTrendingNfts } from '../hooks/useTrendingNfts'

function fmtFloorPrice(value: number | null, currency: string | null): string {
  if (value == null) {
    return 'N/A'
  }

  const formatted = value.toLocaleString(undefined, {
    minimumFractionDigits: value < 1 ? 3 : 2,
    maximumFractionDigits: value < 1 ? 3 : 2,
  })

  return currency ? `${formatted} ${currency}` : formatted
}

export default function NftTrendingWidget() {
  const { data, loading, error } = useTrendingNfts(10)
  const nfts = useMemo(() => data.slice(0, 8), [data])

  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-500">Trending NFTs</h2>
        <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[11px] font-semibold text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
          CoinGecko
        </span>
      </div>

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, idx) => (
            <div key={idx} className="h-12 animate-pulse rounded-lg bg-zinc-100 dark:bg-zinc-800" />
          ))}
        </div>
      ) : error ? (
        <p className="text-sm text-red-500">Could not load trending NFTs.</p>
      ) : nfts.length === 0 ? (
        <p className="text-sm text-zinc-500">No trending NFT collections available right now.</p>
      ) : (
        <div className="space-y-2">
          {nfts.map((nft) => {
            const change = nft.floor_change_24h
            const changeClass =
              typeof change === 'number'
                ? change > 0
                  ? 'text-emerald-500'
                  : change < 0
                    ? 'text-rose-500'
                    : 'text-zinc-500'
                : 'text-zinc-500'

            return (
              <article
                key={`${nft.id ?? nft.name}`}
                className="rounded-lg border border-zinc-200 bg-zinc-50 p-2.5 dark:border-zinc-800 dark:bg-zinc-900/60"
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="flex min-w-0 items-center gap-2">
                    {nft.thumb && (
                      <img
                        src={nft.thumb}
                        alt={`${nft.name} logo`}
                        className="h-8 w-8 rounded-lg object-cover"
                      />
                    )}
                    <div className="min-w-0">
                      {nft.website ? (
                        <a
                          href={nft.website}
                          target="_blank"
                          rel="noreferrer"
                          className="truncate text-sm font-semibold text-zinc-900 hover:underline dark:text-zinc-100"
                        >
                          {nft.name}
                        </a>
                      ) : (
                        <p className="truncate text-sm font-semibold text-zinc-900 dark:text-zinc-100">{nft.name}</p>
                      )}
                      {nft.symbol && (
                        <p className="text-[11px] uppercase tracking-wide text-zinc-500">{nft.symbol}</p>
                      )}
                    </div>
                  </div>
                  <div className="text-right text-xs">
                    <p className="font-semibold text-zinc-800 dark:text-zinc-200">
                      {fmtFloorPrice(nft.floor_price, nft.floor_currency)}
                    </p>
                    <p className={`font-semibold ${changeClass}`}>
                      {typeof change === 'number' ? `${change > 0 ? '+' : ''}${change.toFixed(2)}%` : 'N/A'}
                    </p>
                  </div>
                </div>
              </article>
            )
          })}
        </div>
      )}
    </div>
  )
}
