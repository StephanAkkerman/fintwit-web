import { useState, useEffect } from 'react';
import { MarketMoversResponse } from '../types';

export function useMarketMovers() {
  const [data, setData] = useState<MarketMoversResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    async function fetchMovers() {
      try {
        const res = await fetch('/api/market-movers');
        if (!res.ok) throw new Error('Failed to fetch market movers');
        const json = await res.json();
        if (mounted) {
          setData(json);
          setError(null);
        }
      } catch (err: any) {
        if (mounted) {
          setError(err.message);
        }
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
    }

    fetchMovers();
    const interval = setInterval(fetchMovers, 60000); // Poll every minute

    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  return { data, loading, error };
}
