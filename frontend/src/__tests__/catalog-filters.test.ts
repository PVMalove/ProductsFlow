import {
  DEFAULT_CATALOG_FILTERS,
  parseCatalogFilters,
} from '@/lib/catalog-filters';

describe('parseCatalogFilters', () => {
  it('uses catalog defaults for missing parameters', () => {
    expect(parseCatalogFilters({})).toEqual(DEFAULT_CATALOG_FILTERS);
  });

  it('parses supported filters', () => {
    expect(
      parseCatalogFilters({
        q: ' drill ',
        category: ' Tools ',
        min_price: '10.5',
        max_price: '99',
        sort: 'price_desc',
      }),
    ).toEqual({
      query: 'drill',
      category: 'Tools',
      minPrice: 10.5,
      maxPrice: 99,
      sort: 'price_desc',
    });
  });

  it('rejects invalid prices and sort values locally', () => {
    expect(
      parseCatalogFilters({
        min_price: '-1',
        max_price: 'not-a-number',
        sort: 'unsupported',
      }),
    ).toEqual(DEFAULT_CATALOG_FILTERS);
  });
});
