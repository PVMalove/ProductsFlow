import { serializeCatalogFilters } from '../catalog-filters';
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

export async function getProducts(params: GetProductsParams): Promise<ApiResponse<ProductView[]>> {
  const baseUrl = buildApiBaseUrl(
    process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8080',
  );
  const url = new URL(`${baseUrl}/products/search`);

  const searchParams = serializeCatalogFilters(params);
  if (params.cursor) searchParams.set('after', params.cursor);
  if (params.sort) searchParams.set('sort', params.sort); // override default sorting if omitted by serializer
  
  url.search = searchParams.toString();

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

export async function getProductImage(id: string): Promise<{ image_url: string } | null> {
  const res = await apiClient.get<ApiResponse<{ image_url: string }>>(`/products/${id}/image`);
  return res.data.data;
}
