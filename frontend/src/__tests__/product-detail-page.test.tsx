import '@testing-library/jest-dom';
import { render, screen } from '@testing-library/react';

import ProductDetailPage from '@/app/catalog/[id]/page';
import { getProduct } from '@/lib/api/products';

const mockUseParams = jest.fn();

jest.mock('@/components/catalog/product-image', () => ({
  ProductImage: ({ alt }: { alt: string }) => <div aria-label={alt} />,
}));

jest.mock('@/lib/api/products', () => ({
  getProduct: jest.fn(),
}));

jest.mock('next/navigation', () => ({
  useParams: () => mockUseParams(),
}));

const product = {
  id: 'product-1',
  name: 'Test product',
  description: 'Product description',
  price: 125,
  category: 'Tools',
  user_id: 'user-1',
  is_active: true,
};

describe('ProductDetailPage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUseParams.mockReturnValue({ id: product.id });
  });

  it('loads and renders product details using the route parameter in the browser', async () => {
    (getProduct as jest.Mock).mockResolvedValue(product);

    render(<ProductDetailPage />);

    expect(await screen.findByRole('heading', { name: product.name })).toBeInTheDocument();
    expect(screen.getByText(product.description)).toBeInTheDocument();
    expect(screen.getByText('$125.00')).toBeInTheDocument();
    expect(getProduct).toHaveBeenCalledWith(product.id);
  });

  it('shows the universal unavailable state for a product endpoint 404', async () => {
    (getProduct as jest.Mock).mockRejectedValue({ response: { status: 404 } });
    mockUseParams.mockReturnValue({ id: 'missing-product' });

    render(<ProductDetailPage />);

    expect(
      await screen.findByText('Товар не существует или снят с публикации'),
    ).toBeInTheDocument();
  });
});
