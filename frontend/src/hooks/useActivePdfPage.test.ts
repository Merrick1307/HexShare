import assert from 'node:assert/strict';
import test from 'node:test';

import { selectMostVisiblePage, type PageRect } from './useActivePdfPage';

const viewport = { top: 0, right: 1000, bottom: 600, left: 0 };

test('selects a tall page even when it cannot reach sixty percent visibility', () => {
  const pages: PageRect[] = [
    { pageNumber: 1, rect: { top: -1000, right: 1000, bottom: 300, left: 0 } },
    { pageNumber: 2, rect: { top: 324, right: 1000, bottom: 1624, left: 0 } },
  ];

  assert.equal(selectMostVisiblePage(viewport, pages), 1);

  pages[0].rect = { top: -1250, right: 1000, bottom: 50, left: 0 };
  pages[1].rect = { top: 74, right: 1000, bottom: 1374, left: 0 };
  assert.equal(selectMostVisiblePage(viewport, pages), 2);
});

test('selects the page with the largest visible area', () => {
  const pages: PageRect[] = [
    { pageNumber: 3, rect: { top: -500, right: 1000, bottom: 200, left: 0 } },
    { pageNumber: 4, rect: { top: 224, right: 1000, bottom: 1524, left: 0 } },
  ];

  assert.equal(selectMostVisiblePage(viewport, pages), 4);
});

test('returns null when no page is visible', () => {
  const pages: PageRect[] = [
    { pageNumber: 1, rect: { top: -1400, right: 1000, bottom: -100, left: 0 } },
    { pageNumber: 2, rect: { top: 700, right: 1000, bottom: 2000, left: 0 } },
  ];

  assert.equal(selectMostVisiblePage(viewport, pages), null);
});
