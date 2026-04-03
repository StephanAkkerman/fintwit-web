import { useState, useEffect } from 'react';
import type { TreemapResponse } from '../types';

export function useTreemap() {
  const [data, setData] = useState<TreemapResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchTreemap() {
      try {
        const response = await fetch('/api/treemap');
        if (!response.ok) {
          throw new Error('Failed to fetch treemap data');
        }
        const json = await response.json();
        setData(json);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'An error occurred');
      } finally {
        setLoading(false);
      }
    }

    fetchTreemap();
    // Optional: Refresh data every 5 minutes
    const intervalId = setInterval(fetchTreemap, 5 * 60 * 1000);

    return () => clearInterval(intervalId);
  }, []);

  return { data, loading, error };
}
