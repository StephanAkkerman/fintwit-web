import { useState } from 'react';
import { useMarketMovers } from '../hooks/useMarketMovers';
import { TickerData } from '../types';

export default function MarketMoversWidget() {
  const { data, loading, error } = useMarketMovers();
  const [activeTab, setActiveTab] = useState<'trending' | 'gainers' | 'losers'>('trending');

  if (loading) {
    return (
      <div className="p-4 bg-zinc-100 dark:bg-zinc-900 rounded-lg shadow animate-pulse w-full max-w-sm ml-auto">
        <div className="h-6 bg-zinc-300 dark:bg-zinc-700 w-1/3 mb-4 rounded"></div>
        <div className="h-4 bg-zinc-300 dark:bg-zinc-700 w-full mb-2 rounded"></div>
        <div className="h-4 bg-zinc-300 dark:bg-zinc-700 w-full mb-2 rounded"></div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="p-4 bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400 rounded-lg w-full max-w-sm ml-auto">
        <p>Error loading market movers.</p>
      </div>
    );
  }

  const tabs = [
    { id: 'trending', label: 'Trending', icon: '🔥' },
    { id: 'gainers', label: 'Gainers', icon: '📈' },
    { id: 'losers', label: 'Losers', icon: '📉' }
  ] as const;

  const currentList = data[activeTab] || [];

  return (
    <div className="bg-white dark:bg-zinc-900 rounded-lg shadow-sm border border-zinc-200 dark:border-zinc-800 overflow-hidden w-full max-w-sm sticky top-[4.5rem]">
      <div className="flex border-b border-zinc-200 dark:border-zinc-800">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex-1 py-3 text-sm font-medium flex flex-col items-center justify-center gap-1 transition-colors ${
              activeTab === tab.id
                ? 'bg-zinc-50 dark:bg-black text-blue-600 dark:text-blue-400 border-b-2 border-blue-600 dark:border-blue-400'
                : 'text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200 hover:bg-zinc-50 dark:hover:bg-zinc-800/50'
            }`}
          >
            <span className="text-lg">{tab.icon}</span>
            <span className="text-xs uppercase tracking-wider">{tab.label}</span>
          </button>
        ))}
      </div>

      <div className="p-4 h-[400px] overflow-y-auto custom-scrollbar">
        {currentList.length === 0 ? (
          <p className="text-zinc-500 dark:text-zinc-400 text-sm text-center py-4">No data available.</p>
        ) : (
          <div className="space-y-4">
            {currentList.map((item: TickerData, idx: number) => (
              <div key={`${item.symbol}-${idx}`} className="flex items-center justify-between group">
                <div className="flex flex-col min-w-0 pr-4">
                  <div className="font-bold text-zinc-900 dark:text-zinc-100 truncate">{item.symbol}</div>
                  {item.name && <div className="text-xs text-zinc-500 truncate" title={item.name}>{item.name}</div>}
                </div>
                <div className="text-right whitespace-nowrap">
                  {item.price !== undefined && item.price !== null ? (
                    <div className="font-semibold text-sm">${item.price.toFixed(2)}</div>
                  ) : null}
                  {item.change_percent !== undefined && item.change_percent !== null ? (
                    <div className={`text-xs font-bold px-2 py-0.5 rounded ${
                      item.change_percent > 0 ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' :
                      item.change_percent < 0 ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400' :
                      'bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-400'
                    }`}>
                      {item.change_percent > 0 ? '+' : ''}{item.change_percent.toFixed(2)}%
                    </div>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
