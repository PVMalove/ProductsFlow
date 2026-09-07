import '@testing-library/jest-dom';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import { ProductImage } from '@/components/catalog/product-image';
import { getProductImage } from '@/lib/api/products';

jest.mock('@/lib/api/products', () => ({
  getProductImage: jest.fn(),
}));

describe('ProductImage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('shows the local fallback when the product has no image record', async () => {
    (getProductImage as jest.Mock).mockResolvedValue(null);

    render(<ProductImage productId="product-1" alt="Test product" />);

    await waitFor(() => expect(getProductImage).toHaveBeenCalledWith('product-1'));
    expect(screen.getByRole('img', { name: 'Test product' }).getAttribute('src')).toMatch(
      /\/product-placeholder\.svg$/,
    );
  });

  it('shows the local fallback when the image endpoint returns 404', async () => {
    (getProductImage as jest.Mock).mockRejectedValue({ response: { status: 404 } });

    render(<ProductImage productId="product-1" alt="Test product" />);

    await waitFor(() => expect(getProductImage).toHaveBeenCalledWith('product-1'));
    expect(screen.getByRole('img', { name: 'Test product' }).getAttribute('src')).toMatch(
      /\/product-placeholder\.svg$/,
    );
  });

  it('uses the relative Gateway media path and falls back when the image cannot load', async () => {
    (getProductImage as jest.Mock).mockResolvedValue({
      image_url:
        'http://minio:9000/product-images/products/product-1/image?X-Amz-Signature=test',
    });

    render(<ProductImage productId="product-1" alt="Test product" />);

    const image = screen.getByRole('img', { name: 'Test product' });
    await waitFor(() =>
      expect(image).toHaveAttribute(
        'src',
        '/media/product-images/products/product-1/image?X-Amz-Signature=test',
      ),
    );

    fireEvent.error(image);

    expect(image.getAttribute('src')).toMatch(/\/product-placeholder\.svg$/);
  });
});
