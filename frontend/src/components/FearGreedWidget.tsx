import { useEffect, useState } from 'react';

type FearGreedData = {
  value: number;
  change_percent: number;
  classification: string;
};

export default function FearGreedWidget() {
  const [data, setData] = useState<FearGreedData | null>(null);
  const [error, setError] = useState<boolean>(false);

  useEffect(() => {
    fetch('/api/fear-greed')
      .then((res) => {
        if (!res.ok) throw new Error('Network response was not ok');
        return res.json();
      })
      .then((json) => setData(json))
      .catch((err) => {
        console.error('Failed to fetch Fear & Greed index', err);
        setError(true);
      });
  }, []);

  if (error) return null;
  if (!data) return (
    <div className="rounded-2xl shadow p-4 bg-white dark:bg-zinc-900 animate-pulse flex items-center justify-between h-[72px]">
      <div className="h-4 bg-zinc-200 dark:bg-zinc-800 rounded w-1/3"></div>
      <div className="h-6 bg-zinc-200 dark:bg-zinc-800 rounded w-1/4"></div>
    </div>
  );

  const getEmoji = (val: number) => {
    if (val <= 25) return '😨';
    if (val <= 45) return '😟';
    if (val <= 55) return '😐';
    if (val <= 75) return '🙂';
    return '🤑';
  };

  const getChangeColor = (change: number) => {
    if (change > 0) return 'text-green-500';
    if (change < 0) return 'text-red-500';
    return 'text-zinc-500';
  };

  return (
    <section className="rounded-2xl shadow p-4 bg-white dark:bg-zinc-900 flex items-center justify-between border border-transparent dark:border-zinc-800 transition-all hover:border-zinc-200 dark:hover:border-zinc-700">
      <div className="flex flex-col">
        <h2 className="text-sm font-semibold text-zinc-500 dark:text-zinc-400 uppercase tracking-wider mb-1">
          Crypto Fear & Greed
        </h2>
        <div className="flex items-center gap-2">
          <span className="text-2xl font-bold">{data.value}</span>
          <span className="text-xl" role="img" aria-label={data.classification}>
            {getEmoji(data.value)}
          </span>
        </div>
      </div>
      <div className="flex flex-col items-end">
        <span className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
          {data.classification}
        </span>
        <span className={`text-xs font-semibold ${getChangeColor(data.change_percent)}`}>
          {data.change_percent > 0 ? '+' : ''}{data.change_percent}% since yesterday
        </span>
      </div>
    </section>
  );
}
