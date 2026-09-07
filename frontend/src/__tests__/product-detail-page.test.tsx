import '@testing-library/jest-dom';
import { render, screen } from '@testing-library/react';

import ProductDetailPage from '@/app/catalog/[id]/page';
import { getProduct } from '@/lib/api/products';

jest.mock('@/components/catalog/product-image', () => ({
  ProductImage: ({ alt }: { alt: string }) => <img alt={alt} />,
}));

jest.mock('@/lib/api/products', () => ({
  getProduct: jest.fn(),
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
  });

  it('renders product details returned by the product endpoint', async () => {
    (getProduct as jest.Mock).mockResolvedValue(product);

    render(
      await ProductDetailPage({ params: Promise.resolve({ id: product.id }) }),
    );

    expect(screen.getByRole('heading', { name: product.name })).toBeInTheDocument();
    expect(screen.getByText(product.description)).toBeInTheDocument();
    expect(screen.getByText('$125.00')).toBeInTheDocument();
  });

  it('shows the universal unavailable state for a product endpoint 404', async () => {
    (getProduct as jest.Mock).mockRejectedValue({ response: { status: 404 } });

    render(
      await ProductDetailPage({ params: Promise.resolve({ id: 'missing-product' }) }),
    );

    expect(
      screen.getByText('Товар не существует или снят с публикации'),
    ).toBeInTheDocument();
  });
});
