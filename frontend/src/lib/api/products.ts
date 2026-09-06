export interface ProductView {
  id: string;
  name: string;
  description: string;
  price: number;
  category: string;
  is_active: boolean;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface PageMeta {
  next_cursor: string | null;
  prev_cursor: string | null;
  has_more: boolean;
  has_prev: boolean;
}

export interface ApiResponse<T> {
  data: T;
  meta: PageMeta;
}

export async function getProducts(cursor?: string | null): Promise<ApiResponse<ProductView[]>> {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8080';
  const url = new URL(`${baseUrl}/api/v1/products`);
  if (cursor) {
    url.searchParams.append('after', cursor);
  }
  
  const res = await fetch(url.toString(), {
    cache: 'no-store'
  });
  
  if (!res.ok) {
    throw new Error('Failed to fetch products');
  }
  
  return res.json();
}
