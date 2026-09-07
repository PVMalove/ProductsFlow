import '@testing-library/jest-dom';
import { fireEvent, render, screen } from '@testing-library/react';

import CatalogList from '@/components/catalog/catalog-list';
import { useCursorInfiniteQuery } from '@/hooks/useCursorInfiniteQuery';
import type { CatalogFilters } from '@/lib/catalog-filters';

const mockPush = jest.fn();
let mockInView = false;

jest.mock('react-intersection-observer', () => ({
  useInView: () => ({ ref: jest.fn(), inView: mockInView }),
}));

jest.mock('next/navigation', () => ({
  usePathname: () => '/catalog',
  useRouter: () => ({ push: mockPush }),
}));

jest.mock('@/hooks/useCursorInfiniteQuery', () => ({
  useCursorInfiniteQuery: jest.fn(),
}));

const filters: CatalogFilters = {
  query: null,
  category: null,
  minPrice: null,
  maxPrice: null,
  sort: 'newest',
};

describe('CatalogList', () => {
  beforeEach(() => {
    mockPush.mockClear();
    mockInView = false;
  });

  it('renders loading state', () => {
    (useCursorInfiniteQuery as jest.Mock).mockReturnValue({
      data: undefined,
      status: 'pending',
      hasNextPage: false,
      isFetchingNextPage: false,
      fetchNextPage: jest.fn(),
    });

    render(<CatalogList filters={filters} />);

    expect(screen.getByLabelText(/Loading.../i)).toBeInTheDocument();
    expect(useCursorInfiniteQuery).toHaveBeenCalledWith(filters);
  });

  it('renders products', () => {
    (useCursorInfiniteQuery as jest.Mock).mockReturnValue({
      data: {
        pages: [
          {
            data: [
              {
                id: '1',
                name: 'Test Product',
                description: 'Test Desc',
                price: 100,
                category: 'Test Category',
                user_id: 'user1',
                is_active: true,
              },
            ],
            meta: { next_cursor: null },
          },
        ],
      },
      status: 'success',
      hasNextPage: false,
      isFetchingNextPage: false,
      fetchNextPage: jest.fn(),
    });

    render(<CatalogList filters={filters} />);

    expect(screen.getByText('Test Product')).toBeInTheDocument();
    expect(screen.getByText('Test Desc')).toBeInTheDocument();
    expect(screen.getByText('$100.00')).toBeInTheDocument();
  });

  it('writes filters to the catalog URL while preserving category', () => {
    (useCursorInfiniteQuery as jest.Mock).mockReturnValue({
      data: { pages: [] },
      status: 'success',
      hasNextPage: false,
      isFetchingNextPage: false,
      fetchNextPage: jest.fn(),
    });

    render(<CatalogList filters={{ ...filters, category: 'Tools' }} />);
    fireEvent.change(screen.getByLabelText('Min Price'), {
      target: { value: '25' },
    });
    fireEvent.change(screen.getByLabelText('Sort By'), {
      target: { value: 'price_asc' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Apply' }));

    expect(mockPush).toHaveBeenCalledWith(
      '/catalog?category=Tools&min_price=25&sort=price_asc',
    );
  });

  it('requests the next page when the scroll sentinel becomes visible', () => {
    const fetchNextPage = jest.fn();
    mockInView = true;
    (useCursorInfiniteQuery as jest.Mock).mockReturnValue({
      data: { pages: [{ data: [], meta: { next_cursor: 'next-page' } }] },
      status: 'success',
      hasNextPage: true,
      isFetchingNextPage: false,
      fetchNextPage,
    });

    render(<CatalogList filters={filters} />);

    expect(fetchNextPage).toHaveBeenCalledTimes(1);
  });
});
