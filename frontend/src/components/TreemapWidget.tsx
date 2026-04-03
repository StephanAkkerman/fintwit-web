import React from 'react';
import { useTreemap } from '../hooks/useTreemap';

export default function TreemapWidget() {
  const { data, loading, error } = useTreemap();

  if (loading) {
    return (
      <div className="p-4 rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 animate-pulse h-32 flex items-center justify-center">
        <span className="text-zinc-500">Loading Treemap...</span>
      </div>
    );
  }

  if (error || !data || !data.data) {
    return null;
  }

  // Display top 12 coins by market cap
  const topCoins = data.data.slice(0, 12);

  return (
    <div className="p-4 rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 shadow-sm">
      <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="lucide lucide-grid-2x2 text-blue-500"><rect width="18" height="18" x="3" y="3" rx="2"/><path d="M3 12h18"/><path d="M12 3v18"/></svg>
        Crypto Market Overview
      </h2>
      <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 gap-2">
        {topCoins.map((coin) => {
          const isPositive = coin.ch >= 0;
          const bgColor = isPositive
            ? 'bg-emerald-500/10 dark:bg-emerald-500/20 text-emerald-700 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800'
            : 'bg-rose-500/10 dark:bg-rose-500/20 text-rose-700 dark:text-rose-400 border-rose-200 dark:border-rose-800';

          return (
            <div
              key={coin.s}
              className={`p-2 rounded-lg border ${bgColor} flex flex-col justify-between h-full`}
            >
              <div className="font-bold text-sm tracking-tight">{coin.s}</div>
              <div className="mt-1 flex flex-col">
                <span className="text-xs font-medium text-zinc-900 dark:text-zinc-100">
                  ${coin.p < 1 ? coin.p.toFixed(4) : coin.p.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </span>
                <span className="text-[10px] font-semibold mt-0.5">
                  {isPositive ? '+' : ''}{coin.ch.toFixed(2)}%
                </span>
              </div>
            </div>
          );
        })}
      </div>
      <div className="mt-3 text-xs text-zinc-500 text-right">
        Data provided by Coin360
      </div>
    </div>
  );
}
