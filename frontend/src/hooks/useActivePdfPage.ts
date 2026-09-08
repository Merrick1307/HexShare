import { type RefObject, useEffect } from 'react';

type Rect = Pick<DOMRectReadOnly, 'bottom' | 'left' | 'right' | 'top'>;
const ACTIVE_PAGE_THRESHOLDS = Array.from({ length: 101 }, (_, index) => index / 100);

export interface PageRect {
  pageNumber: number;
  rect: Rect;
}

export function selectMostVisiblePage(viewport: Rect, pages: PageRect[]): number | null {
  const viewportCenterY = (viewport.top + viewport.bottom) / 2;
  let selectedPage: number | null = null;
  let selectedVisibleArea = 0;
  let selectedCenterDistance = Number.POSITIVE_INFINITY;

  for (const page of pages) {
    const visibleWidth = Math.max(
      0,
      Math.min(page.rect.right, viewport.right) - Math.max(page.rect.left, viewport.left),
    );
    const visibleHeight = Math.max(
      0,
      Math.min(page.rect.bottom, viewport.bottom) - Math.max(page.rect.top, viewport.top),
    );
    const visibleArea = visibleWidth * visibleHeight;
    if (visibleArea === 0) continue;

    const pageCenterY = (page.rect.top + page.rect.bottom) / 2;
    const centerDistance = Math.abs(pageCenterY - viewportCenterY);
    if (
      visibleArea > selectedVisibleArea ||
      (visibleArea === selectedVisibleArea && centerDistance < selectedCenterDistance)
    ) {
      selectedPage = page.pageNumber;
      selectedVisibleArea = visibleArea;
      selectedCenterDistance = centerDistance;
    }
  }

  return selectedPage;
}

interface UseActivePdfPageOptions {
  enabled: boolean;
  layoutKey: unknown;
  pageRefs: RefObject<Record<number, HTMLDivElement | null>>;
  scrollContainerRef: RefObject<HTMLDivElement | null>;
  onActivePageChange: (pageNumber: number) => void;
}

export function useActivePdfPage({
  enabled,
  layoutKey,
  pageRefs,
  scrollContainerRef,
  onActivePageChange,
}: UseActivePdfPageOptions) {
  useEffect(() => {
    if (!enabled) return;

    const scrollContainer = scrollContainerRef.current;
    if (!scrollContainer) return;

    const visiblePages = new Map<number, HTMLDivElement>();
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const element = entry.target as HTMLDivElement;
          const pageNumber = Number(element.dataset.pageNumber);
          if (!Number.isFinite(pageNumber)) continue;

          if (entry.isIntersecting && entry.intersectionRatio > 0) {
            visiblePages.set(pageNumber, element);
          } else {
            visiblePages.delete(pageNumber);
          }
        }

        const pages = Array.from(visiblePages, ([pageNumber, element]) => ({
          pageNumber,
          rect: element.getBoundingClientRect(),
        }));
        const nextPage = selectMostVisiblePage(scrollContainer.getBoundingClientRect(), pages);
        if (nextPage !== null) onActivePageChange(nextPage);
      },
      { root: scrollContainer, threshold: ACTIVE_PAGE_THRESHOLDS },
    );

    Object.values(pageRefs.current).forEach((element) => {
      if (element) observer.observe(element);
    });

    return () => {
      observer.disconnect();
      visiblePages.clear();
    };
  }, [enabled, layoutKey, onActivePageChange, pageRefs, scrollContainerRef]);
}
