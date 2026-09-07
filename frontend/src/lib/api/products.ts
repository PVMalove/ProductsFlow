import type { CatalogFilters } from '../catalog-filters';
import { buildApiBaseUrl } from '../api-url';
import { apiClient } from '../apiClient';
import { FetchResponseError } from './fetch-response-error';
import type { ApiResponse } from './types';

export interface ProductView {
  id: string;
  name: string;
  description: string;
  price: number;
  category: string;
  user_id: string;
  is_active: boolean;
}

interface GetProductsParams extends CatalogFilters {
  cursor?: string | null;
}

export async function getProducts({
  cursor,
  q,
  category,
  minPrice,
  maxPrice,
  sort,
}: GetProductsParams): Promise<ApiResponse<ProductView[]>> {
  const baseUrl = buildApiBaseUrl(
    process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8080',
  );
  const url = new URL(`${baseUrl}/products/search`);

  if (cursor) url.searchParams.set('after', cursor);
  if (q) url.searchParams.set('q', q);
  if (category) url.searchParams.set('category', category);
  if (minPrice !== null) url.searchParams.set('min_price', minPrice.toString());
  if (maxPrice !== null) url.searchParams.set('max_price', maxPrice.toString());
  url.searchParams.set('sort', sort);

  const res = await fetch(url.toString(), {
    cache: 'no-store',
  });

  if (!res.ok) {
    throw new FetchResponseError('Failed to fetch products', res.status);
  }

  return res.json();
}

export async function getProduct(id: string): Promise<ProductView> {
  const res = await apiClient.get<ApiResponse<ProductView>>(`/products/${id}`);
  return res.data.data;
}

export async function patchProduct(id: string, data: Partial<ProductView>): Promise<ProductView> {
  const res = await apiClient.patch<ApiResponse<ProductView>>(`/products/${id}`, data);
  return res.data.data;
}

export async function uploadProductImage(id: string, file: File): Promise<{ image_url: string }> {
  const formData = new FormData();
  formData.append('file', file);
  const res = await apiClient.post<ApiResponse<{ image_url: string }>>(`/products/${id}/image`, formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
  return res.data.data;
}

export async function getProductImage(id: string): Promise<{ image_url: string }> {
  const res = await apiClient.get<ApiResponse<{ image_url: string }>>(`/products/${id}/image`);
  return res.data.data;
}
