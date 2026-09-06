export interface ProductView {
  id: string;
  name: string;
  description: string;
  price: number;
  category: string;
  user_id: string;
  is_active: boolean;
}

import { apiClient } from '../apiClient';
import { ApiResponse } from './types';

export async function getProducts(
  cursor?: string | null,
  category?: string | null,
  min_price?: number | null,
  max_price?: number | null
): Promise<ApiResponse<ProductView[]>> {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8080';
  const url = new URL(`${baseUrl}/api/v1/products`);
  if (cursor) {
    url.searchParams.append('after', cursor);
  }
  if (category) {
    url.searchParams.append('category', category);
  }
  if (min_price !== undefined && min_price !== null) {
    url.searchParams.append('min_price', min_price.toString());
  }
  if (max_price !== undefined && max_price !== null) {
    url.searchParams.append('max_price', max_price.toString());
  }
  
  const res = await fetch(url.toString(), {
    cache: 'no-store'
  });
  
  if (!res.ok) {
    throw new Error('Failed to fetch products');
  }
  
  return res.json();
}

export async function getProduct(id: string): Promise<ProductView> {
  const res = await apiClient.get<ApiResponse<ProductView>>(`/v1/products/${id}`);
  return res.data.data;
}

export async function patchProduct(id: string, data: Partial<ProductView>): Promise<ProductView> {
  const res = await apiClient.patch<ApiResponse<ProductView>>(`/v1/products/${id}`, data);
  return res.data.data;
}

export async function uploadProductImage(id: string, file: File): Promise<{ image_url: string }> {
  const formData = new FormData();
  formData.append('file', file);
  const res = await apiClient.post<ApiResponse<{ image_url: string }>>(`/v1/products/${id}/image`, formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
  return res.data.data;
}

export async function getProductImage(id: string): Promise<{ image_url: string }> {
  const res = await apiClient.get<ApiResponse<{ image_url: string }>>(`/v1/products/${id}/image`);
  return res.data.data;
}
