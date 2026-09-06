export const CATALOG_SORT_OPTIONS = [
  'newest',
  'price_asc',
  'price_desc',
] as const;

export type CatalogSort = (typeof CATALOG_SORT_OPTIONS)[number];

export interface CatalogFilters {
  category: string | null;
  minPrice: number | null;
  maxPrice: number | null;
  sort: CatalogSort;
}

export const DEFAULT_CATALOG_FILTERS: CatalogFilters = {
  category: null,
  minPrice: null,
  maxPrice: null,
  sort: 'newest',
};

type CatalogSearchParams = Record<string, string | string[] | undefined>;

function firstValue(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

function parsePrice(value: string | undefined): number | null {
  if (!value?.trim()) return null;
  const price = Number(value);
  return Number.isFinite(price) && price >= 0 ? price : null;
}

export function isCatalogSort(value: string | undefined): value is CatalogSort {
  return CATALOG_SORT_OPTIONS.some((option) => option === value);
}

export function parseCatalogFilters(params: CatalogSearchParams): CatalogFilters {
  const category = firstValue(params.category)?.trim() || null;
  const sort = firstValue(params.sort);

  return {
    category,
    minPrice: parsePrice(firstValue(params.min_price)),
    maxPrice: parsePrice(firstValue(params.max_price)),
    sort: isCatalogSort(sort) ? sort : DEFAULT_CATALOG_FILTERS.sort,
  };
}
