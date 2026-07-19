import { useCallback, useEffect, useRef, useState, type RefObject } from 'react';
import { PaginatedResponse } from '../types';

interface UseInfiniteScrollOptions<T> {
  fetchFn: (offset: number, limit: number) => Promise<PaginatedResponse<T>>;
  pageSize?: number;
  enabled?: boolean;
  rootRef?: RefObject<HTMLElement | null>;
}

export function useInfiniteScroll<T>({ fetchFn, pageSize = 20, enabled = true, rootRef }: UseInfiniteScrollOptions<T>) {
  const [items, setItems] = useState<T[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const observerRef = useRef<IntersectionObserver | null>(null);
  const sentinelRef = useRef<HTMLDivElement | null>(null);

  const loadMore = useCallback(async () => {
    if (isLoading || !hasMore || !enabled) return;
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetchFn(items.length, pageSize);
      setItems((prev) => [...prev, ...response.items]);
      setTotal(response.total);
      setHasMore(items.length + response.items.length < response.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load more items');
      setHasMore(false);
    } finally {
      setIsLoading(false);
    }
  }, [fetchFn, items.length, pageSize, isLoading, hasMore, enabled]);

  useEffect(() => {
    if (!enabled) return;
    const sentinel = sentinelRef.current;
    if (!sentinel) return;

    observerRef.current = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) {
          void loadMore();
        }
      },
      { root: rootRef?.current ?? null, rootMargin: '200px' }
    );
    observerRef.current.observe(sentinel);

    return () => {
      observerRef.current?.disconnect();
    };
  }, [loadMore, enabled]);

  const reset = useCallback(() => {
    setItems([]);
    setTotal(0);
    setHasMore(true);
    setError(null);
  }, []);

  return {
    items,
    total,
    isLoading,
    hasMore,
    error,
    sentinelRef,
    loadMore,
    reset,
    setItems,
  };
}
