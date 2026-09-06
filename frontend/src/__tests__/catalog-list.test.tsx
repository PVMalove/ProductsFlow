import '@testing-library/jest-dom';
import { render, screen } from '@testing-library/react';
import CatalogList from '@/components/catalog/catalog-list';
import { useCursorInfiniteQuery } from '@/hooks/useCursorInfiniteQuery';

jest.mock('react-intersection-observer', () => ({
  useInView: () => ({ ref: jest.fn(), inView: false }),
}));

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

jest.mock('@/hooks/useCursorInfiniteQuery', () => ({
  useCursorInfiniteQuery: jest.fn(),
}));

describe('CatalogList', () => {
  it('renders loading state', () => {
    (useCursorInfiniteQuery as jest.Mock).mockReturnValue({
      data: undefined,
      status: 'pending',
      hasNextPage: false,
      isFetchingNextPage: false,
    });

    render(<CatalogList />);
    expect(screen.getByLabelText(/Loading.../i)).toBeInTheDocument();
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
    });

    render(<CatalogList />);
    expect(screen.getByText('Test Product')).toBeInTheDocument();
    expect(screen.getByText('Test Desc')).toBeInTheDocument();
    expect(screen.getByText('$100.00')).toBeInTheDocument();
  });
});
